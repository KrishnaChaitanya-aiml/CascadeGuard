from collections import defaultdict
import re
from typing import Any


def _parse_number(text):
    match = re.search(r"\b[\d,]+(?:\.\d+)?\b", str(text))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def classify_impact(description: str) -> str:
    text = description.lower()
    if "bridge" in text and "destroyed" in text:
        return "bridges_destroyed"
    if "fatalit" in text:
        return "fatalities"
    if "injured" in text:
        return "injured"
    if "rescued" in text:
        return "rescued"
    if "out of contact" in text:
        return "out_of_contact"
    if "evacuated" in text or "displaced" in text:
        return "evacuated"
    return "other"


def build_evidence_summary(event: dict, tool_results: list[dict[str, Any]], aoi: dict | None = None):
    evidence = []

    event_id = event.get("event_id")
    evidence.append(
        {
            "id": f"gdacs-event-{event_id}",
            "source": "GDACS",
            "evidence_type": "disaster_event",
            "claim": f"GDACS reports a {event.get('event_type')} event in {event.get('country') or 'the reported area'}.",
            "location": {"latitude": event.get("latitude"), "longitude": event.get("longitude")},
            "values": {
                "event_id": event_id,
                "alert_level": event.get("alert_level"),
                "alert_score": event.get("alert_score"),
                "event_source": event.get("event_source"),
            },
            "source_url": event.get("report_url"),
        }
    )

    for index, metric in enumerate(event.get("impact_metrics") or []):
        if metric.get("country") and event.get("country") and metric.get("country") != event.get("country"):
            continue
        description = metric.get("description", "")
        evidence.append(
            {
                "id": metric.get("id", f"gdacs-impact-{index}"),
                "source": "GDACS",
                "evidence_type": "reported_impact",
                "claim": description,
                "metric_type": classify_impact(description),
                "value": metric.get("value"),
                "country": metric.get("country"),
                "region": metric.get("region"),
                "timestamp": metric.get("onset_date"),
                "source_url": event.get("report_url"),
            }
        )

    for result_index, result in enumerate(tool_results):
        source = result.get("source")
        for obs_index, observation in enumerate(result.get("observations") or []):
            if source == "OpenStreetMap":
                category = observation.get("category")
                name = observation.get("name")
                label = f"{category.replace('_', ' ')}" if category else "infrastructure"
                claim = f"OpenStreetMap maps a {label}"
                if name:
                    claim += f" ({name})"
                claim += f" about {observation.get('distance_km')} km from an investigation zone."
                evidence.append(
                    {
                        "id": f"osm-{result_index}-{obs_index}",
                        "source": source,
                        "evidence_type": "infrastructure_observation",
                        "claim": claim,
                        "observation": observation,
                    }
                )
            elif source == "Open-Meteo":
                p = observation.get("precipitation_mm")
                wind = observation.get("wind_speed_10m_max_kmh")
                gust = observation.get("wind_gusts_10m_max_kmh")
                parts = []
                if p is not None:
                    parts.append(f"{p} mm precipitation")
                if wind is not None:
                    parts.append(f"{wind} km/h maximum wind")
                if gust is not None:
                    parts.append(f"{gust} km/h maximum gust")
                claim = "Open-Meteo reports " + ", ".join(parts) + f" on {observation.get('date')}."
                evidence.append(
                    {
                        "id": f"weather-{result_index}-{obs_index}",
                        "source": source,
                        "evidence_type": "weather_observation",
                        "claim": claim,
                        "observation": observation,
                    }
                )
            elif source == "Open-Meteo Flood API":
                evidence.append(
                    {
                        "id": f"flood-{result_index}-{obs_index}",
                        "source": source,
                        "evidence_type": "river_discharge_observation",
                        "claim": f"The Open-Meteo Flood API reports river discharge of {observation.get('river_discharge_m3s')} m³/s on {observation.get('date')} at the queried flood-model cell.",
                        "observation": observation,
                    }
                )
            elif source == "WorldPop":
                for population_observation in result.get("observations") or []:
                    estimate = population_observation.get("population_estimate")
                    claim = "WorldPop returned an AOI population exposure estimate."
                    if estimate is not None:
                        claim = f"WorldPop estimates approximately {estimate:,.0f} people in the queried AOI."
                    evidence.append(
                        {
                            "id": f"worldpop-{result_index}-{obs_index}",
                            "source": source,
                            "evidence_type": "population_exposure",
                            "claim": claim,
                            "observation": population_observation,
                        }
                    )
            elif source == "USGS":
                evidence.append(
                    {
                        "id": f"usgs-{result_index}-{obs_index}",
                        "source": source,
                        "evidence_type": "earthquake_context",
                        "claim": f"USGS lists a magnitude {observation.get('magnitude')} earthquake at {observation.get('place')}.",
                        "observation": observation,
                    }
                )

    if aoi:
        evidence.append(
            {
                "id": "system-aoi",
                "source": "CascadeGuard",
                "evidence_type": "investigation_scope",
                "claim": aoi.get("description", "Investigation area defined by CascadeGuard."),
                "value": {
                    "scope": aoi.get("scope"),
                    "zones": len(aoi.get("zones", [])),
                },
            }
        )

    return {"evidence_count": len(evidence), "evidence": evidence}


def group_impact_conflicts(evidence: dict):
    grouped = defaultdict(list)
    for item in evidence.get("evidence", []):
        if item.get("evidence_type") == "reported_impact":
            grouped[item.get("metric_type")].append(item)

    conflicts = []
    for metric_type, items in grouped.items():
        values = {str(item.get("value")) for item in items if item.get("value") not in (None, "")}
        if len(values) > 1:
            conflicts.append(
                {
                    "metric_type": metric_type,
                    "values": sorted(values),
                    "evidence_ids": [item.get("id") for item in items],
                }
            )
    return conflicts


def source_counts(evidence: dict):
    counts = defaultdict(int)
    for item in evidence.get("evidence", []):
        counts[item.get("source", "Unknown")] += 1
    return dict(counts)


def validate_claim(claim: str, evidence: dict) -> dict:
    text = claim.lower()
    evidence_text = " ".join(item.get("claim", "").lower() for item in evidence.get("evidence", []))

    forbidden_without_direct = [
        "damaged", "destroyed", "collapsed", "failed", "impassable", "inaccessible", "broken"
    ]
    for term in forbidden_without_direct:
        if term in text and term not in evidence_text:
            return {"supported": False, "reason": f"Claim uses '{term}' without matching direct evidence."}

    numbers_mm = re.findall(r"(\d+(?:\.\d+)?)\s*mm", text)
    observed_mm = set()
    for item in evidence.get("evidence", []):
        if item.get("source") == "Open-Meteo":
            value = (item.get("observation") or {}).get("precipitation_mm")
            if value is not None:
                observed_mm.add(float(value))
    for value in numbers_mm:
        if float(value) not in observed_mm:
            return {"supported": False, "reason": f"Rainfall value {value} mm is not present in collected weather evidence."}

    return {"supported": True, "reason": "No obvious unsupported direct factual claim detected."}
