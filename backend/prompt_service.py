import re
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Callable

from backend.llm import chat_completion, parse_json_content
from backend.evidence import source_counts
from backend.tools.gdacs import get_disaster_events
from backend.tools.geography import geocode_place

SUPPORTED_HAZARDS = {
    "FL": "Flood",
    "EQ": "Earthquake",
    "TC": "Cyclone",
    "WF": "Wildfire",
}

ALL_HAZARDS = list(SUPPORTED_HAZARDS.keys())


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(max(0.0, 1.0 - a)))


def _emit(callback: Callable[[dict], None] | None, event_type: str, message: str, **extra):
    if callback:
        payload = {"type": event_type, "message": message}
        payload.update(extra)
        callback(payload)


def _heuristic_intent(prompt: str) -> dict:
    text = prompt.lower()
    hazard_map = {
        "FL": ["flood", "flooding", "river flood", "waterlogging"],
        "EQ": ["earthquake", "quake", "seismic"],
        "TC": ["cyclone", "typhoon", "hurricane", "tropical storm"],
        "WF": ["wildfire", "forest fire", "bushfire", "fire risk"],
    }
    found = []
    for code, words in hazard_map.items():
        if any(re.search(rf"\b{re.escape(word)}\b", text) for word in words):
            found.append(code)

    # A compact fallback for common place-introducing phrasing. Keep this
    # deliberately narrow: using the entire prompt as a geocoding query can
    # turn an unrelated request into a plausible-looking location.
    location = None
    match = re.search(
        r"\b(?:in|around|near|at|for)\s+(.+?)(?=\s+(?:and|to|with|where|which|that)\b|[.!?]|$)",
        prompt,
        flags=re.I,
    )
    if match:
        location = match.group(1).strip(" .,!?")

    # A generic request for cascading/disaster risk is intentionally treated
    # as multi-hazard. Everything else without a hazard is a clarification,
    # not permission to guess all hazards.
    generic_risk = any(
        phrase in text
        for phrase in (
            "cascading risk",
            "cascade risk",
            "disaster risk",
            "all major risks",
            "all risks",
        )
    )
    if not found and generic_risk:
        found = ALL_HAZARDS[:]

    return {
        "location_query": location,
        "hazards": found,
        "intent": "multi_hazard_city_scan" if len(found) > 1 else "hazard_investigation",
        "time_window_days": 14,
    }


def resolve_prompt(prompt: str, callback: Callable[[dict], None] | None = None) -> dict:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    explicit_event_id = None
    event_match = re.search(r"\b(?:gdacs\s*)?(?:event\s*(?:id)?\s*)?(\d{6,10})\b", prompt, flags=re.I)
    if event_match:
        explicit_event_id = event_match.group(1)

    _emit(callback, "intent", "Understanding the request and identifying the location, hazard scope and any explicit event ID.")

    heuristic = _heuristic_intent(prompt)
    parsed = None
    try:
        response = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract structured intent for CascadeGuard. Return JSON only. "
                        "Identify the geographic place the user wants investigated, "
                        "hazard codes from FL flood, EQ earthquake, TC cyclone, WF wildfire, "
                        "and whether the request is multi-hazard. Do not invent a place. "
                        "Schema: {location_query:string, hazards:string[], intent:string, time_window_days:number}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.0,
        )
        parsed = parse_json_content(response)
    except Exception:
        parsed = _heuristic_intent(prompt)
        _emit(callback, "fallback", "LLM intent extraction was unavailable; using conservative local parsing.")

    parsed = parsed if isinstance(parsed, dict) else {}
    location_query = str(parsed.get("location_query") or heuristic.get("location_query") or "").strip()
    parsed_hazards = [
        str(x).upper()
        for x in (parsed.get("hazards") or [])
        if str(x).upper() in SUPPORTED_HAZARDS
    ]
    hazards = parsed_hazards or heuristic.get("hazards") or []
    intent = str(parsed.get("intent") or ("multi_hazard_city_scan" if len(hazards) > 1 else "hazard_investigation"))
    try:
        days = int(parsed.get("time_window_days", 14))
    except (TypeError, ValueError):
        days = 14
    days = max(1, min(days, 60))

    if not location_query:
        raise ValueError(
            "I could not identify a location in the prompt. Please include a city, region, or country."
        )
    if not hazards:
        raise ValueError(
            "I could not identify a supported hazard. Please name flood, earthquake, cyclone, "
            "or wildfire—or ask for all cascading disaster risks."
        )

    _emit(callback, "geocode", f"Locating {location_query}.")
    location = geocode_place(location_query)
    if not location:
        raise ValueError(
            f"Could not reliably locate '{location_query}'. Please provide a more specific city, region, or country."
        )

    _emit(
        callback,
        "geocode_result",
        f"Resolved location to {location['display_name']}.",
        location=location,
    )

    return {
        "original_prompt": prompt,
        "explicit_event_id": explicit_event_id,
        "location_query": location_query,
        "location": location,
        "hazards": hazards,
        "intent": intent,
        "time_window_days": days,
    }


def _event_age_days(event: dict) -> float:
    raw = event.get("last_modified") or event.get("event_end") or event.get("event_time")
    if not raw:
        return 999.0
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.utcnow()
        return max(0.0, (now - dt).total_seconds() / 86400.0)
    except ValueError:
        return 999.0


def select_nearby_event(
    event_type: str,
    latitude: float,
    longitude: float,
    country: str | None,
    window_days: int = 14,
    max_distance_km: float = 350.0,
):
    raw = get_disaster_events(event_type)
    events = []
    for event in raw.get("features", []):
        props = event.get("properties") or {}
        geom = event.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if geom.get("type") != "Point" or len(coords) < 2:
            continue
        ev_lat, ev_lon = float(coords[1]), float(coords[0])
        if country and props.get("country") and props.get("country") != country:
            continue
        distance = _distance_km(latitude, longitude, ev_lat, ev_lon)
        age = _event_age_days({"last_modified": props.get("datemodified"), "event_end": props.get("todate"), "event_time": props.get("fromdate")})
        current = str(props.get("iscurrent", "")).lower() == "true"
        # Current/recent events dominate; distance breaks ties.
        if distance > max_distance_km and not current:
            continue
        if age > window_days and not current:
            continue
        relevance = (
            (80.0 if current else 0.0)
            + max(0.0, 35.0 - age * 2.5)
            + max(0.0, 35.0 - distance / 10.0)
            + {"Red": 15.0, "Orange": 8.0, "Green": 2.0}.get(props.get("alertlevel"), 0.0)
        )
        events.append((relevance, distance, props, geom))

    if not events:
        return None

    events.sort(key=lambda x: (-x[0], x[1]))
    _, distance, props, geom = events[0]
    return {
        "event_id": props.get("eventid"),
        "distance_km": round(distance, 1),
        "is_current": str(props.get("iscurrent", "")).lower() == "true",
        "alert_level": props.get("alertlevel"),
        "event_name": props.get("name") or props.get("description"),
    }


def resolve_events_for_location(intent: dict, callback: Callable[[dict], None] | None = None) -> list[dict]:
    location = intent["location"]
    lat = float(location["latitude"])
    lon = float(location["longitude"])
    country = location.get("address", {}).get("country")
    window_days = int(intent.get("time_window_days", 14))
    selected = []

    for code in intent["hazards"]:
        label = SUPPORTED_HAZARDS[code]
        _emit(callback, "discovery", f"Searching GDACS for nearby {label.lower()} events.")
        match = None
        if intent.get("explicit_event_id"):
            try:
                from backend.tools.gdacs import get_disaster_event_by_id
                raw = get_disaster_event_by_id(code, str(intent["explicit_event_id"]))
                props = raw.get("properties") or raw
                match = {
                    "event_id": props.get("eventid", intent["explicit_event_id"]),
                    "distance_km": None,
                    "is_current": str(props.get("iscurrent", "")).lower() == "true",
                    "alert_level": props.get("alertlevel"),
                    "event_name": props.get("name") or props.get("description"),
                }
            except Exception:
                match = None
        if not match:
            match = select_nearby_event(code, lat, lon, country, window_days=window_days)
        if match and match.get("event_id"):
            _emit(
                callback,
                "event_selected",
                f"Selected {label} event {match['event_id']} ({match['distance_km']} km from the requested location).",
                hazard=code,
                event_id=str(match["event_id"]),
            )
            selected.append({"event_type": code, **match})
        else:
            _emit(callback, "no_event", f"No recent {label.lower()} event was located near the requested location.", hazard=code)

    if not selected:
        raise ValueError(
            "No recent GDACS disaster event was found near the requested location for the requested hazards."
        )
    return selected


def _compact_status(statuses: list[dict]) -> list[dict]:
    merged = {}
    for item in statuses:
        name = item.get("source")
        if not name:
            continue
        merged[name] = item
    return list(merged.values())


def _synthesize_multi_hazard(prompt: str, location: dict, analyses: list[dict]) -> dict:
    top_lines = []
    interventions = []
    for analysis in analyses:
        event = analysis.get("event", {})
        inv = analysis.get("investigation", {})
        for cascade in (inv.get("cascades") or [])[:3]:
            top_lines.append(
                f"{event.get('event_type')} event {event.get('event_id')}: "
                f"{cascade.get('title')} | priority {cascade.get('priority_score')} | "
                f"confidence {round((cascade.get('confidence') or 0) * 100)}% | "
                f"{cascade.get('mechanism')}"
            )
            intervention = cascade.get("intervention") or {}
            if intervention.get("action"):
                interventions.append(intervention.get("action"))

    prompt_text = f"""
You are the senior city-risk analyst for CascadeGuard.
Create a compact executive summary from the supplied evidence-backed hazard analyses.
Do not invent facts. Do not change scores. Do not claim a hazard occurred unless an event was selected.
Return JSON only:
{{
  "summary": "2-3 sentence city risk summary",
  "solution": "one concise highest-leverage intervention strategy",
  "why": "one concise reason"
}}

USER REQUEST:
{prompt}

LOCATION:
{location.get('display_name')}

TOP CANDIDATES:
{json.dumps(top_lines, indent=2)}

INTERVENTION OPTIONS:
{json.dumps(interventions[:12], indent=2)}
"""
    response = chat_completion(
        [
            {"role": "system", "content": "Return valid JSON only. Evidence-grounded decision support."},
            {"role": "user", "content": prompt_text},
        ],
        max_tokens=500,
        temperature=0.0,
    )
    return parse_json_content(response)


def run_prompt_investigation(prompt: str, callback: Callable[[dict], None] | None = None) -> dict:
    intent = resolve_prompt(prompt, callback=callback)
    selected = resolve_events_for_location(intent, callback=callback)

    from backend.agent import run_agent
    from backend.aoi import build_location_aoi
    from backend.event_service import get_disaster_event

    location = intent["location"]
    lat = float(location["latitude"])
    lon = float(location["longitude"])
    city_label = location.get("display_name") or intent["location_query"]
    hazards_requested = intent["hazards"]
    max_zones = 6
    aoi = build_location_aoi(lat, lon, city_label, radius_km=25, max_zones=max_zones)

    _emit(callback, "aoi_created", f"Built a 25 km city investigation area with {len(aoi['zones'])} representative zones.")

    analyses = []
    aggregate_status = []
    aggregate_trace = []
    all_cascades = []
    selected_events = []

    for match in selected:
        code = match["event_type"]
        event_id = str(match["event_id"])
        label = SUPPORTED_HAZARDS.get(code, code)
        _emit(callback, "investigation_start", f"Investigating {label.lower()} event {event_id}.", hazard=code, event_id=event_id)
        event = get_disaster_event(event_id, code)
        if not event:
            _emit(callback, "no_event", f"The selected {label.lower()} event could not be loaded.", hazard=code)
            continue

        # Use a city-centered AOI for consistent comparison across hazards.
        event_aoi = dict(aoi)
        event_aoi["label"] = f"{city_label} · {label} investigation area"
        event_aoi["description"] = (
            f"City-centered 25 km investigation area used to compare {label.lower()} cascade candidates."
        )

        result = run_agent(event, event_aoi, emit=callback)
        analyses.append({"event": event, "investigation": result})
        aggregate_status.extend(result.get("source_status") or [])
        aggregate_trace.extend(result.get("investigation_trace") or [])
        for cascade in result.get("cascades") or []:
            clone = dict(cascade)
            clone["id"] = f"{code}-{clone.get('id', '')}"
            clone["hazard"] = label
            clone["event_id"] = event_id
            clone["event_distance_km"] = match.get("distance_km")
            clone["event_latitude"] = event.get("latitude")
            clone["event_longitude"] = event.get("longitude")
            all_cascades.append(clone)

        selected_events.append({
            "event_type": code,
            "hazard": label,
            "event_id": event_id,
            "event_name": event.get("name"),
            "country": event.get("country"),
            "distance_km": match.get("distance_km"),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
            "alert_level": event.get("alert_level"),
            "status": "investigated",
        })
        _emit(callback, "investigation_complete", f"Finished {label.lower()} investigation {event_id}.", hazard=code, event_id=event_id)

    if not analyses:
        raise RuntimeError(
            "The selected live disaster event data could not be loaded, so no reliable investigation was produced."
        )

    all_cascades.sort(key=lambda c: float(c.get("priority_score") or 0), reverse=True)
    all_cascades = all_cascades[:12]

    source_status = _compact_status(aggregate_status)
    summary = "City risk scan completed from the selected real disaster events."
    solution = "Prioritize the highest-ranked cascade intervention and verify the affected corridor or service before action."
    why = "The recommendation is based on the strongest evidence-backed cascade currently available."

    if len(analyses) > 1:
        try:
            synthesis = _synthesize_multi_hazard(prompt, location, analyses)
            summary = synthesis.get("summary") or summary
            solution = synthesis.get("solution") or solution
            why = synthesis.get("why") or why
            _emit(callback, "synthesis", "Compared the strongest cascade candidates across hazards.")
        except Exception:
            _emit(callback, "fallback", "Cross-hazard synthesis was unavailable; ranked cascade results were retained.")

    top = all_cascades[0] if all_cascades else None
    top_intervention = (top or {}).get("intervention") or {}
    trace = [
        {"type": "request", "message": f"Interpreted request: {intent['intent']} for {city_label}."},
        *aggregate_trace,
        {"type": "cross_hazard_rank", "message": f"Ranked {len(all_cascades)} cascade candidates across {len(analyses)} investigated hazards."},
    ]

    return {
        "status": "completed",
        "mode": "city_scan" if len(hazards_requested) > 1 else "incident_scan",
        "prompt": intent["original_prompt"],
        "location": location,
        "aoi": aoi,
        "selected_events": selected_events,
        "requested_hazards": hazards_requested,
        "summary": summary,
        "overall_intervention": {
            "action": top_intervention.get("action") or solution,
            "where": top_intervention.get("where") or aoi.get("label"),
            "why": top_intervention.get("why") or why,
            "evidence_ids": top_intervention.get("evidence_ids", []),
            "supporting_evidence": top_intervention.get("supporting_evidence", []),
            "location_basis": top_intervention.get(
                "location_basis",
                "Mapped coordinates are shown; route connectivity and blockage require field verification.",
            ),
            "cascade_id": top.get("id") if top else None,
        },
        "cascades": all_cascades,
        "top_cascade_id": top.get("id") if top else None,
        "source_status": source_status,
        "source_counts": source_counts(
            {
                "evidence": [
                    item
                    for a in analyses
                    for item in a.get("investigation", {}).get("evidence_summary", {}).get("evidence", [])
                ]
            }
        ),
        "evidence_summary": {
            "evidence_count": sum(
                (a.get("investigation", {}).get("evidence_summary", {}).get("evidence_count", 0) for a in analyses),
            ),
            "evidence": [
                item
                for a in analyses
                for item in a.get("investigation", {}).get("evidence_summary", {}).get("evidence", [])
            ][:120],
        },
        "impact_conflicts": [
            conflict
            for a in analyses
            for conflict in a.get("investigation", {}).get("impact_conflicts", [])
        ],
        "limitations": list(dict.fromkeys([
            "This is decision support, not a calibrated prediction of failure probability.",
            "GDACS event selection is proximity/recentness-based when the user does not supply an event ID.",
            "Mapped infrastructure presence does not prove live damage or operational status.",
            *[x for a in analyses for x in a.get("investigation", {}).get("limitations", [])],
        ]))[:10],
        "investigation_trace": trace,
        "analyses": analyses,
    }
