import json
from datetime import datetime
from typing import Any

from backend.evidence import build_evidence_summary, group_impact_conflicts, source_counts, validate_claim
from backend.llm import chat_completion, parse_json_content
from backend.models import CascadeCandidate, CascadeNode
from backend.tools.osm import get_infrastructure_batch
from backend.tools.weather import get_flood_discharge_batch, get_weather_batch
from backend.tools.usgs import get_earthquake_context
from backend.tools.worldpop import get_population_for_geometry
from backend.tools.firms import get_active_fire
from backend.tools.ibtracs import get_cyclone_track


def _date(value: str | None):
    return (value or datetime.utcnow().strftime("%Y-%m-%d"))[:10]


def _hazard(event_type: str):
    return {
        "FL": "flood",
        "EQ": "earthquake",
        "TC": "cyclone",
        "DR": "drought",
        "WF": "wildfire",
    }.get(event_type.upper(), event_type.lower())


def _collect_tools(event: dict, aoi: dict, trace: list[dict], emit=None):
    points = [(z["latitude"], z["longitude"]) for z in aoi.get("zones", [])]
    event_type = event.get("event_type", "FL").upper()
    event_date = _date(event.get("event_time"))
    event_end = _date(event.get("event_end") or event.get("event_time"))
    results: list[dict[str, Any]] = []
    statuses = []

    def record_source(name, runner):
        item = {"type": "tool_call", "tool": name, "message": f"Collecting {name} evidence."}
        trace.append(item)
        if emit:
            emit(item)
        try:
            result = runner()
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
            statuses.append({"source": name, "status": "available", "detail": _detail(result)})
            item = {"type": "tool_result", "tool": name, "message": f"{name} returned evidence."}
            trace.append(item)
            if emit:
                emit(item)
        except Exception as exc:
            result = {"source": name, "status": "unavailable", "error": str(exc), "observations": []}
            results.append(result)
            statuses.append({"source": name, "status": "unavailable", "detail": str(exc)})
            item = {"type": "tool_error", "tool": name, "message": f"{name} unavailable: {exc}"}
            trace.append(item)
            if emit:
                emit(item)

    record_source("OpenStreetMap", lambda: get_infrastructure_batch(points, radius_km=max(z.get("radius_km", 15) for z in aoi.get("zones", []))))

    record_source("Open-Meteo", lambda: get_weather_batch(points, event_date))

    if event_type == "FL":
        record_source("Open-Meteo Flood API", lambda: get_flood_discharge_batch(points, event_date, event_end))

    if event_type == "EQ":
        lat = event.get("latitude")
        lon = event.get("longitude")
        if lat is not None and lon is not None:
            record_source("USGS", lambda: get_earthquake_context(float(lat), float(lon), event_date, event_end, 150))

    if event_type == "TC":
        lat = event.get("latitude")
        lon = event.get("longitude")
        if lat is not None and lon is not None:
            record_source("NOAA IBTrACS", lambda: get_cyclone_track(float(lat), float(lon), event_date, 500))

    if event_type in {"WF", "WILDFIRE"}:
        bounds = aoi.get("bounds")
        if bounds:
            record_source("NASA FIRMS", lambda: get_active_fire(bounds, event_date))

    item = {"type": "evidence_merge", "message": f"Merged {len(results)} source result packets into the evidence layer."}
    trace.append(item)
    if emit:
        emit(item)

    # Population is one AOI-level query. Use it as optional corroboration.
    geometry = aoi.get("geometry")
    if geometry and event.get("iso3") and aoi.get("scope") != "country":
        record_source("WorldPop", lambda: get_population_for_geometry(event.get("iso3"), geometry))

    return results, statuses


def _detail(result):
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict):
        return "Malformed response"
    if result.get("status") == "unavailable":
        return result.get("error")
    if "count" in result:
        return f"{result['count']} mapped assets"
    return f"{len(result.get('observations', []))} observations"


def _evidence_claims(evidence_summary: dict, evidence_ids: list[str]) -> list[str]:
    wanted = set(evidence_ids)
    return [
        item.get("claim", "")
        for item in evidence_summary.get("evidence", [])
        if item.get("id") in wanted and item.get("claim")
    ][:5]


def _asset_anchors(evidence_summary: dict) -> list[dict]:
    anchors = []
    for item in evidence_summary.get("evidence", []):
        observation = item.get("observation") or {}
        if observation.get("category") not in {"hospital", "bridge", "road", "shelter", "airport"}:
            continue
        if observation.get("latitude") is None or observation.get("longitude") is None:
            continue
        anchors.append(
            {
                "category": observation.get("category"),
                "name": observation.get("name") or f"mapped {observation.get('category')}",
                "latitude": float(observation["latitude"]),
                "longitude": float(observation["longitude"]),
                "distance_km": observation.get("distance_km"),
            }
        )
    return anchors


def _intervention_for(
    title: str,
    event: dict,
    aoi: dict,
    evidence_summary: dict,
    evidence_ids: list[str],
) -> dict:
    """Build a specific, evidence-linked action without asserting unobserved damage."""
    anchors = _asset_anchors(evidence_summary)
    hospital = next((x for x in anchors if x["category"] == "hospital"), None)
    corridor = next((x for x in anchors if x["category"] in {"bridge", "road"}), None)
    event_coordinates = ""
    if event.get("latitude") is not None and event.get("longitude") is not None:
        event_coordinates = f"event coordinate {float(event['latitude']):.5f}, {float(event['longitude']):.5f}"
    where = aoi.get("label") or event.get("country") or "the investigation area"
    if event_coordinates:
        where = f"{where} · {event_coordinates}"
    target = "the most connected corridor or critical service in this area"
    action = "Verify the most connected corridor or critical service before committing resources."
    why = "The evidence supports a targeted verification step, but does not prove live damage or service failure."
    lower_title = title.lower()

    if "river" in lower_title:
        target = "the downstream river/discharge hotspot and nearby exposed assets"
        action = "Prioritize monitoring of the downstream discharge hotspot and verify nearby exposed infrastructure."
        why = "Observed modeled discharge provides environmental context for downstream exposure; it does not by itself prove damage."
    elif "medical" in lower_title or "hospital" in lower_title:
        target = "mapped hospitals and the roads connecting them to the investigation area"
        action = "Verify hospital access routes and establish an alternate access plan where route conditions are confirmed."
        why = "Mapped critical facilities and transport observations indicate where access verification has the highest operational value."
    elif "evacuation" in lower_title:
        target = "mapped evacuation corridors and shelters in the investigation area"
        action = "Verify evacuation corridor status and shelter access before directing movement."
        why = "The cascade depends on route availability, which is not directly observed by the current sources."
    elif "smoke" in lower_title:
        target = "population-facing health services downwind of the active-fire evidence"
        action = "Verify smoke exposure and health-service capacity before prioritizing protective measures."
        why = "Active-fire or weather evidence can indicate exposure context, but does not establish local smoke concentration."
    elif "power" in lower_title or "communications" in lower_title:
        target = "utility-dependent critical facilities in the investigation area"
        action = "Verify utility and communications status at critical facilities, then route around confirmed outages."
        why = "Utility failure is a hypothesis here; direct outage verification is the necessary next step."
    elif "supply" in lower_title:
        target = "the mapped road and bridge network serving the investigation area"
        action = "Verify the supply corridor at the most connected mapped bridges and road segments."
        why = "Transport observations identify a practical verification point without claiming that mapped assets are damaged."

    if corridor and hospital and any(word in lower_title for word in ("transport", "medical", "emergency", "access")):
        corridor_label = f"{corridor['name']} ({corridor['latitude']:.5f}, {corridor['longitude']:.5f})"
        hospital_label = f"{hospital['name']} ({hospital['latitude']:.5f}, {hospital['longitude']:.5f})"
        where = (
            f"{corridor_label} ↔ {hospital_label}; both are mapped inside {aoi.get('label') or 'the investigation area'}. "
            "The collected data does not prove that they are directly connected."
        )
        target = f"the route between {corridor_label} and {hospital_label}"
        action = (
            f"Government should field-verify {corridor_label} and its access route to {hospital_label}. "
            "If blockage is confirmed, activate an alternate hospital access route."
        )
        why = (
            "The named road/bridge and hospital are observed mapped assets in the investigation area; "
            "blockage and route connectivity remain unverified."
        )

    return {
        "action": action,
        "where": where,
        "target": target,
        "why": why,
        "evidence_ids": list(dict.fromkeys(evidence_ids[:8])),
        "supporting_evidence": _evidence_claims(evidence_summary, evidence_ids),
        "location_basis": "Mapped asset coordinates and/or the GDACS event coordinate; route blockage is not inferred.",
    }


def _candidate_templates(event_type: str):
    hazard = _hazard(event_type)
    if event_type == "FL":
        return [
            ("C1", "Transport isolation", "flood → bridge/road disruption → isolation → response access"),
            ("C2", "Medical access bottleneck", "flood → transport disruption → hospital access risk → medical response pressure"),
            ("C3", "Supply corridor disruption", "flood → transport disruption → supply access risk → humanitarian pressure"),
            ("C4", "River escalation", "flood conditions → elevated river discharge → additional downstream exposure"),
            ("C5", "Water and sanitation pressure", "flood → water-system exposure → service disruption → health pressure"),
            ("C6", "Shelter access bottleneck", "flood → transport disruption → shelter accessibility risk → displaced-population pressure"),
        ]
    if event_type == "EQ":
        return [
            ("C1", "Emergency access bottleneck", "earthquake → transport disruption risk → emergency facility access risk"),
            ("C2", "Critical service disruption", "earthquake → critical infrastructure exposure → service disruption risk"),
            ("C3", "Secondary seismic activity", "earthquake → nearby significant seismic events → compounded exposure"),
            ("C4", "Population access disruption", "earthquake → connectivity disruption → population isolation risk"),
            ("C5", "Water or power dependency", "earthquake → utility infrastructure exposure → water/power service risk"),
            ("C6", "Debris and corridor blockage", "earthquake → debris/building failure → road capacity risk → response delay"),
        ]
    if event_type == "TC":
        return [
            ("C1", "Flooded access corridors", "cyclone → rainfall/flooding pressure → transport disruption → isolation"),
            ("C2", "Emergency access bottleneck", "cyclone → transport disruption → hospital/service access risk"),
            ("C3", "Supply corridor disruption", "cyclone → weather/transport disruption → supply risk"),
            ("C4", "Wind-related infrastructure pressure", "cyclone → high winds → infrastructure exposure → service risk"),
            ("C5", "Power and communications pressure", "cyclone → wind/flood exposure → power/communications disruption risk"),
            ("C6", "Evacuation bottleneck", "cyclone → hazardous conditions → limited safe routes → evacuation pressure"),
        ]
    if event_type in {"WF", "WILDFIRE"}:
        return [
            ("C1", "Evacuation corridor bottleneck", "wildfire → road closure risk → reduced evacuation capacity"),
            ("C2", "Smoke and health pressure", "wildfire → smoke exposure → health-service demand risk"),
            ("C3", "Critical infrastructure exposure", "wildfire → infrastructure exposure → service disruption risk"),
            ("C4", "Power and communications pressure", "wildfire → utility exposure → power/communications disruption risk"),
            ("C5", "Population isolation", "wildfire → corridor disruption → population access risk"),
            ("C6", "Supply disruption", "wildfire → road/network disruption → supply access risk"),
        ]
    return [
        ("C1", "Transport disruption", f"{hazard} → transport disruption → access risk"),
        ("C2", "Critical service access", f"{hazard} → infrastructure exposure → critical service risk"),
        ("C3", "Population isolation", f"{hazard} → connectivity disruption → population access risk"),
    ]


def _evidence_text(evidence_summary: dict):
    lines = []
    for item in evidence_summary.get("evidence", []):
        lines.append(f"[{item.get('id')}] {item.get('source')} / {item.get('evidence_type')}: {item.get('claim')}")
    return "\n".join(lines[:140])


def _fallback_candidates(event: dict, evidence_summary: dict, aoi: dict):
    event_type = event.get("event_type", "FL").upper()
    evidence = evidence_summary.get("evidence", [])
    evidence_ids = [item["id"] for item in evidence]
    source_set = {item.get("source") for item in evidence}
    has_bridge_damage = any(item.get("metric_type") == "bridges_destroyed" for item in evidence)
    has_hospital = any((item.get("observation") or {}).get("category") == "hospital" for item in evidence)
    has_weather = "Open-Meteo" in source_set
    has_discharge = "Open-Meteo Flood API" in source_set
    has_eq = "USGS" in source_set
    population_estimate = 0.0
    for item in evidence:
        if item.get("source") == "WorldPop":
            value = (item.get("observation") or {}).get("population_estimate")
            if isinstance(value, (int, float)):
                population_estimate = max(population_estimate, float(value))
    candidates = []

    for cid, title, mechanism in _candidate_templates(event_type):
        nodes = [CascadeNode(label=_hazard(event_type).title(), role="hazard", status="confirmed", evidence_ids=[f"gdacs-event-{event.get('event_id')}"])]
        score = 45.0
        confidence = 0.45
        uncertainties = ["The relationship between mapped infrastructure and live operational status is not directly observed."]
        if has_bridge_damage:
            nodes.append(CascadeNode(label="Reported bridge destruction", role="failure", status="confirmed", evidence_ids=[item["id"] for item in evidence if item.get("metric_type") == "bridges_destroyed"]))
            score += 20
            confidence += 0.18
        elif has_hospital:
            nodes.append(CascadeNode(label="Critical infrastructure exposure", role="exposure", status="confirmed", evidence_ids=[item["id"] for item in evidence if (item.get("observation") or {}).get("category") in {"hospital", "airport"}][:4]))
            score += 8
            confidence += 0.08
        else:
            nodes.append(CascadeNode(label="Infrastructure exposure", role="exposure", status="confirmed", evidence_ids=evidence_ids[:3]))

        if title == "River escalation" and has_discharge:
            score += 15
            confidence += 0.12
            nodes.append(CascadeNode(label="River discharge observation", role="consequence", status="confirmed", evidence_ids=[i["id"] for i in evidence if i.get("source") == "Open-Meteo Flood API"][:4]))
        elif title == "Medical access bottleneck" and has_hospital:
            score += 18
            confidence += 0.10
            nodes.append(CascadeNode(label="Hospital access risk", role="service", status="inference", evidence_ids=[i["id"] for i in evidence if (i.get("observation") or {}).get("category") == "hospital"][:4]))
        elif title == "Secondary seismic activity" and has_eq:
            score += 18
            confidence += 0.15
            nodes.append(CascadeNode(label="Nearby seismic activity", role="consequence", status="confirmed", evidence_ids=[i["id"] for i in evidence if i.get("source") == "USGS"][:4]))
        elif title == "Water and sanitation pressure":
            score += 10 if any((i.get("observation") or {}).get("category") in {"hospital", "shelter"} for i in evidence) else 4
            confidence += 0.03
            nodes.append(CascadeNode(label="Critical service exposure", role="service", status="inference", evidence_ids=[i["id"] for i in evidence if (i.get("observation") or {}).get("category") in {"hospital", "shelter"}][:4]))
            uncertainties.append("Water-system condition is not directly observed by the current core tools.")
        elif title == "Shelter access bottleneck":
            score += 8 if any((i.get("observation") or {}).get("category") == "shelter" for i in evidence) else 3
            nodes.append(CascadeNode(label="Mapped shelter exposure", role="service", status="confirmed" if any((i.get("observation") or {}).get("category") == "shelter" for i in evidence) else "unknown", evidence_ids=[i["id"] for i in evidence if (i.get("observation") or {}).get("category") == "shelter"][:4]))
        elif title == "Water or power dependency":
            score += 5
            uncertainties.append("Power and water network condition is not directly observed by the current core tools.")
            nodes.append(CascadeNode(label="Utility dependency hypothesis", role="service", status="inference", evidence_ids=[]))
        elif title == "Debris and corridor blockage":
            score += 5
            uncertainties.append("Current road/debris condition requires direct verification.")
            nodes.append(CascadeNode(label="Corridor blockage hypothesis", role="failure", status="inference", evidence_ids=[]))
        elif title == "Power and communications pressure":
            score += 6 if has_weather else 2
            uncertainties.append("Power and communications outages are not directly observed by the core tools.")
            nodes.append(CascadeNode(label="Utility disruption hypothesis", role="consequence", status="inference", evidence_ids=[i["id"] for i in evidence if i.get("source") in {"Open-Meteo", "NASA FIRMS"}][:4]))
        elif title == "Evacuation bottleneck":
            score += 5
            uncertainties.append("Actual evacuation route availability is not directly observed.")
            nodes.append(CascadeNode(label="Evacuation route risk", role="service", status="inference", evidence_ids=[]))
        elif title == "Evacuation corridor bottleneck":
            score += 5
            uncertainties.append("Actual road closures are not directly observed by the core tools.")
            nodes.append(CascadeNode(label="Evacuation route risk", role="service", status="inference", evidence_ids=[]))
        elif title == "Smoke and health pressure":
            score += 4
            uncertainties.append("Smoke concentration and health-system load are not directly observed.")
            nodes.append(CascadeNode(label="Smoke exposure hypothesis", role="exposure", status="inference", evidence_ids=[]))
        elif title == "Critical infrastructure exposure":
            score += 6
            nodes.append(CascadeNode(label="Critical infrastructure exposure", role="exposure", status="confirmed", evidence_ids=[i["id"] for i in evidence if (i.get("observation") or {}).get("category") in {"hospital", "airport", "shelter"}][:4]))
        elif title == "Population isolation":
            score += 5
            nodes.append(CascadeNode(label="Population access risk", role="exposure", status="inference", evidence_ids=[]))
        elif title == "Supply disruption":
            score += 4
            nodes.append(CascadeNode(label="Supply access risk", role="service", status="inference", evidence_ids=[]))
        elif title == "Wind-related infrastructure pressure" and has_weather:
            score += 12
            confidence += 0.08
            nodes.append(CascadeNode(label="Wind / gust observations", role="consequence", status="confirmed", evidence_ids=[i["id"] for i in evidence if i.get("source") == "Open-Meteo"][:4]))
        elif has_weather and event_type in {"FL", "TC"}:
            score += 8
            confidence += 0.05
            nodes.append(CascadeNode(label="Environmental context", role="consequence", status="confirmed", evidence_ids=[i["id"] for i in evidence if i.get("source") == "Open-Meteo"][:4]))

        if "WorldPop" in source_set:
            score += 5
            confidence += 0.03
        if population_estimate >= 100000:
            score += 6
        elif population_estimate >= 25000:
            score += 3
        if len(source_set) >= 3:
            score += 5
            confidence += 0.04

        confidence = min(confidence, 0.96)
        priority = min(98, score)
        candidate_evidence_ids = list(dict.fromkeys(evidence_ids[:12]))
        intervention = _intervention_for(
            title,
            event,
            aoi,
            evidence_summary,
            candidate_evidence_ids,
        )
        candidates.append(
            CascadeCandidate(
                id=cid,
                title=title,
                mechanism=mechanism,
                nodes=nodes,
                confidence=confidence,
                impact_score=min(95, priority + (8 if has_hospital else 0)),
                priority_score=priority,
                intervention=intervention,
                uncertainty=uncertainties,
                evidence_ids=candidate_evidence_ids,
            )
        )

    candidates.sort(key=lambda c: c.priority_score, reverse=True)
    return candidates[:6]


def _llm_rank(event: dict, evidence_summary: dict, candidates: list[CascadeCandidate]):
    compact_candidates = [
        {
            "id": c.id,
            "title": c.title,
            "mechanism": c.mechanism,
            "priority_score": c.priority_score,
            "confidence": c.confidence,
            "impact_score": c.impact_score,
            "evidence_ids": c.evidence_ids,
        }
        for c in candidates
    ]

    prompt = f"""
You are the senior analyst inside CascadeGuard.

Refine the explanations for the candidate cascading-risk hypotheses using ONLY the supplied evidence.
Do not invent facts, numbers, damage, causal relationships, or locations.
Do not change or recalculate the numeric priority/confidence/impact scores.
Do not sum conflicting GDACS cumulative observations.
OSM presence does not equal damage or operational status.
Weather observations do not prove causation.

Return JSON only with this shape:
{{
  "summary": "one concise paragraph",
  "cascades": [
    {{
      "id": "C1",
      "title": "...",
      "mechanism": "...",
       "intervention": {{"action": "...", "where": "...", "why": "...", "evidence_ids": []}},
      "uncertainty": ["..."]
    }}
  ]
}}

DISASTER:
{json.dumps(event, indent=2)}

CANDIDATES:
{json.dumps(compact_candidates, indent=2)}

EVIDENCE:
{_evidence_text(evidence_summary)}
"""

    try:
        response = chat_completion(
            [
                {"role": "system", "content": "Return only valid JSON. Evidence-grounded decision support."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1700,
            temperature=0.0,
        )
        return parse_json_content(response)
    except Exception:
        return None


def run_agent(event: dict, aoi: dict | None = None, emit=None):
    if not aoi:
        raise ValueError("AOI is required for investigation")

    trace = []

    def record(item):
        trace.append(item)
        if emit:
            emit(item)

    record({"type": "event_loaded", "message": f"Loaded {event.get('event_type')} event {event.get('event_id')} from GDACS."})
    record({"type": "aoi_created", "message": f"Built {aoi.get('scope')} investigation area with {len(aoi.get('zones', []))} candidate zones."})

    tool_results, statuses = _collect_tools(event, aoi, trace, emit=emit)
    evidence_summary = build_evidence_summary(event, tool_results, aoi)
    conflicts = group_impact_conflicts(evidence_summary)
    if conflicts:
        record({"type": "evidence_conflict", "message": f"Found {len(conflicts)} conflicting reported-impact groups; values will not be summed."})

    candidates = _fallback_candidates(event, evidence_summary, aoi)
    record({"type": "hypothesis_generation", "message": f"Generated {len(candidates)} candidate cascade hypotheses."})

    ranked = _llm_rank(event, evidence_summary, candidates)
    if ranked and isinstance(ranked.get("cascades"), list):
        by_id = {c.id: c for c in candidates}
        for item in ranked.get("cascades", []):
            base = by_id.get(str(item.get("id")))
            if not base:
                continue
            base.title = item.get("title") or base.title
            base.mechanism = item.get("mechanism") or base.mechanism
            llm_intervention = item.get("intervention") or {}
            if isinstance(llm_intervention, dict):
                base.intervention = {
                    **base.intervention,
                    # Keep the deterministic action, location and asset
                    # anchors intact. Featherless can refine the cascade
                    # narrative, but must not invent a road, route, forecast
                    # or coordinate.
                    "evidence_ids": base.evidence_ids,
                }
            base.uncertainty = item.get("uncertainty") or base.uncertainty
        summary = ranked.get("summary") or "Cascade analysis completed from the collected evidence."
    else:
        summary = "Cascade analysis completed using constrained evidence-based hypothesis scoring."
        record({"type": "llm_fallback", "message": "Featherless refinement was unavailable; deterministic evidence scoring was retained."})

    # Numeric ranking stays deterministic and evidence-derived.
    candidates.sort(key=lambda c: c.priority_score, reverse=True)
    top_id = candidates[0].id if candidates else None

    for cascade in candidates:
        cascade.evidence_ids = list(dict.fromkeys(cascade.evidence_ids))
        cascade.intervention = {
            **cascade.intervention,
            "evidence_ids": cascade.evidence_ids,
            "supporting_evidence": _evidence_claims(evidence_summary, cascade.evidence_ids),
        }

    validation = validate_claim(summary, evidence_summary)
    record({"type": "validation", "message": validation["reason"]})
    record({"type": "ranked", "message": f"Ranked {len(candidates)} cascade candidates; highest priority is {top_id or 'none'}."})

    limitations = [
        "Cascade scores are decision-support rankings, not calibrated probabilities.",
        "Mapped infrastructure does not prove current operational status or damage.",
        "Conflicting cumulative GDACS impact observations are preserved rather than summed.",
    ]
    if conflicts:
        limitations.append(f"GDACS contains {len(conflicts)} conflicting reported-impact groups in this event response.")

    top_intervention = candidates[0].intervention if candidates else {}
    overall_intervention = {
        "action": top_intervention.get("action"),
        "where": top_intervention.get("where"),
        "why": top_intervention.get("why"),
        "evidence_ids": top_intervention.get("evidence_ids", []),
        "supporting_evidence": top_intervention.get("supporting_evidence", []),
        "location_basis": top_intervention.get(
            "location_basis",
            "Mapped coordinates are shown; route connectivity and blockage require field verification.",
        ),
        "cascade_id": top_id,
    }

    return {
        "status": "completed",
        "summary": summary,
        "aoi": aoi,
        "source_status": statuses,
        "evidence_summary": evidence_summary,
        "cascades": [c.model_dump() for c in candidates],
        "top_cascade_id": top_id,
        "overall_intervention": overall_intervention,
        "investigation_trace": trace,
        "validation": validation,
        "impact_conflicts": conflicts,
        "source_counts": source_counts(evidence_summary),
        "confidence": candidates[0].confidence if candidates else 0,
        "limitations": limitations,
    }
