from backend.aoi import build_aoi
from backend.agent import _fallback_candidates
from backend.evidence import build_evidence_summary, group_impact_conflicts


def main():
    event = {
        "event_id": 1,
        "event_type": "FL",
        "name": "Test Flood",
        "country": "Nepal",
        "iso3": "NPL",
        "alert_level": "Red",
        "alert_score": 3,
        "event_source": "TEST",
        "event_time": "2026-08-26T01:00:00",
        "event_end": "2026-08-27T01:00:00",
        "latitude": 27.2953,
        "longitude": 85.3649,
        "impact_metrics": [{
            "id": "m1",
            "description": "77 [bridges] Bridge destroyed in Bagmati Province, Nepal",
            "value": "77",
            "country": "Nepal",
            "region": "Bagmati Province",
            "onset_date": "2026-08-26T01:00:00",
        }, {
            "id": "m2",
            "description": "900 [people] Out of contact in Bagmati Province, Nepal",
            "value": "900",
            "country": "Nepal",
            "region": "Bagmati Province",
            "onset_date": "2026-08-26T01:00:00",
        }, {
            "id": "m3",
            "description": "1200 [people] Out of contact in Bagmati Province, Nepal",
            "value": "1200",
            "country": "Nepal",
            "region": "Bagmati Province",
            "onset_date": "2026-08-26T01:00:00",
        }],
        "geometry": {"type": "Point", "coordinates": [85.3649, 27.2953]},
    }
    aoi = build_aoi(event, scope="event_buffer", buffer_km=25, max_zones=4)
    evidence = build_evidence_summary(event, [{
        "source": "Open-Meteo",
        "observations": [{"date": "2026-08-26", "precipitation_mm": 6.4}],
    }, {
        "source": "OpenStreetMap",
        "observations": [{"category": "bridge", "name": "Demo Bridge", "distance_km": 4.2}],
    }], aoi)
    assert evidence["evidence_count"] >= 4
    assert len(group_impact_conflicts(evidence)) == 1
    cascades = _fallback_candidates(event, evidence, aoi)
    assert cascades and cascades[0].priority_score >= cascades[-1].priority_score
    print("Smoke test passed")


if __name__ == "__main__":
    main()
