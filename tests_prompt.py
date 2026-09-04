import backend.prompt_service as ps
import backend.agent as agent
from backend import event_service


def fake_event(event_id, code):
    return {
        "event_id": event_id,
        "event_type": code,
        "name": f"Test {code}",
        "country": "Nepal",
        "iso3": "NPL",
        "alert_level": "Red",
        "event_time": "2026-08-26T01:00:00",
        "event_end": "2026-09-01T14:00:00",
        "latitude": 27.3,
        "longitude": 85.35,
        "geometry": {"type": "Point", "coordinates": [85.35, 27.3]},
        "impact_metrics": [],
    }


def fake_agent(event, aoi, emit=None):
    if emit:
        emit({"type": "mock_analysis", "message": f"Mock analysis for {event['event_type']}."})
    return {
        "status": "completed",
        "summary": "Mock summary",
        "aoi": aoi,
        "source_status": [{"source": "Mock", "status": "available", "detail": "ok"}],
        "evidence_summary": {"evidence_count": 1, "evidence": [{"id": "e1", "source": "GDACS", "evidence_type": "disaster_event", "claim": "mock"}]},
        "cascades": [{
            "id": "C1", "title": "Transport isolation", "mechanism": "hazard → access risk",
            "nodes": [], "confidence": 0.8, "impact_score": 80, "priority_score": 85,
            "intervention": {"action": "Verify critical corridor", "reason": "High leverage"},
            "uncertainty": [], "evidence_ids": ["e1"],
        }],
        "top_cascade_id": "C1",
        "investigation_trace": [], "validation": {"supported": True, "reason": "ok"},
        "impact_conflicts": [], "limitations": [],
    }


old_chat = ps.chat_completion
old_geo = ps.geocode_place
old_events = ps.get_disaster_events
old_event = event_service.get_disaster_event
old_ps_event = ps.get_disaster_event if hasattr(ps, 'get_disaster_event') else None
old_agent = agent.run_agent

try:
    ps.chat_completion = lambda *a, **k: {"choices": [{"message": {"content": '{"location_query":"Kathmandu, Nepal","hazards":["FL","EQ"],"intent":"multi_hazard_city_scan","time_window_days":14}'}}]}
    ps.geocode_place = lambda q: {"display_name":"Kathmandu, Nepal","latitude":27.7172,"longitude":85.324,"address":{"country":"Nepal","country_code":"NP","ISO3166-1-alpha3":"NPL"}}
    ps.get_disaster_events = lambda code: {"features":[{"geometry":{"type":"Point","coordinates":[85.3649,27.2953]},"properties":{"eventid":1104124 if code=="FL" else 1541922,"country":"Nepal","name":"Test event","alertlevel":"Red","iscurrent":"true","fromdate":"2026-08-26T01:00:00","todate":"2026-09-01T14:00:00","datemodified":"2026-09-04T11:00:00"}}]}
    event_service.get_disaster_event = lambda eid, code: fake_event(eid, code)
    ps.get_disaster_event = lambda eid, code: fake_event(eid, code)
    agent.run_agent = fake_agent

    result = ps.run_prompt_investigation("Find all major cascading risks in Kathmandu, Nepal")
    assert result["mode"] == "city_scan"
    assert len(result["selected_events"]) == 2
    assert len(result["cascades"]) == 2
    assert result["top_cascade_id"] == result["cascades"][0]["id"]
    print("Prompt workflow test passed")
finally:
    ps.chat_completion = old_chat
    ps.geocode_place = old_geo
    ps.get_disaster_events = old_events
    event_service.get_disaster_event = old_event
    if old_ps_event is not None:
        ps.get_disaster_event = old_ps_event
    agent.run_agent = old_agent
