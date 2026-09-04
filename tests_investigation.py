import backend.agent as agent
from backend.aoi import build_aoi


def fake_osm(points, radius_km=15):
    return [{
        "source":"OpenStreetMap",
        "observations":[
            {"osm_id":1,"osm_type":"way","category":"bridge","name":"Test Bridge","distance_km":2.4,"latitude":27.30,"longitude":85.39,"tags":{"bridge":"yes","highway":"secondary"}},
            {"osm_id":2,"osm_type":"node","category":"hospital","name":"Test Hospital","distance_km":4.1,"latitude":27.31,"longitude":85.40,"tags":{"amenity":"hospital"}},
        ]
    }]

def fake_weather(points, date):
    return {"source":"Open-Meteo","observations":[{"latitude":points[0][0],"longitude":points[0][1],"date":date,"precipitation_mm":6.4,"wind_speed_10m_max_kmh":20.0,"wind_gusts_10m_max_kmh":31.0}]}

def fake_flood(points, start_date, end_date):
    return {"source":"Open-Meteo Flood API","observations":[{"latitude":points[0][0],"longitude":points[0][1],"date":start_date,"river_discharge_m3s":250.0}]}

def fake_population(iso3, geometry):
    return {"source":"WorldPop","status":"available","observations":[{"population_estimate":120000}]}

def fake_llm(*args, **kwargs):
    raise RuntimeError("mock llm failure")

a=agent.get_infrastructure_batch
w=agent.get_weather_batch
f=agent.get_flood_discharge_batch
p=agent.get_population_for_geometry
l=agent.chat_completion
agent.get_infrastructure_batch=fake_osm
agent.get_weather_batch=fake_weather
agent.get_flood_discharge_batch=fake_flood
agent.get_population_for_geometry=fake_population
agent.chat_completion=fake_llm

try:
    event={
        "event_id":1104124,"event_type":"FL","name":"Flood in Nepal","country":"Nepal","iso3":"NPL",
        "alert_level":"Red","alert_score":3,"event_source":"GLOFAS","event_time":"2026-08-26T01:00:00","event_end":"2026-09-01T14:00:00",
        "latitude":27.2953,"longitude":85.3649,"geometry":{"type":"Point","coordinates":[85.3649,27.2953]},
        "impact_metrics":[{"id":"m1","description":"77 [bridges] Bridge destroyed in Bagmati Province, Nepal","value":"77","country":"Nepal","region":"Bagmati Province","onset_date":"2026-08-26T01:00:00"}],
    }
    aoi=build_aoi(event,scope='event_buffer',buffer_km=25,max_zones=4)
    result=agent.run_agent(event,aoi)
    assert result['status']=='completed'
    assert len(result['cascades'])>=2
    assert result['evidence_summary']['evidence_count']>=4
    assert result['top_cascade_id']==result['cascades'][0]['id']
    print('Investigation smoke test passed')
finally:
    agent.get_infrastructure_batch=a
    agent.get_weather_batch=w
    agent.get_flood_discharge_batch=f
    agent.get_population_for_geometry=p
    agent.chat_completion=l
