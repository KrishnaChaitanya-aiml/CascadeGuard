from backend.tools.gdacs import get_disaster_event_by_id, get_disaster_events
from backend.tools.osm import get_affected_infrastructure, get_infrastructure_batch
from backend.tools.weather import get_precipitation, get_weather_batch, get_flood_discharge_batch
from backend.tools.usgs import get_earthquake_context
from backend.tools.worldpop import get_population_for_geometry

TOOLS = {
    "get_disaster_event_by_id": get_disaster_event_by_id,
    "get_disaster_events": get_disaster_events,
    "get_affected_infrastructure": get_affected_infrastructure,
    "get_infrastructure_batch": get_infrastructure_batch,
    "get_precipitation": get_precipitation,
    "get_weather_batch": get_weather_batch,
    "get_flood_discharge_batch": get_flood_discharge_batch,
    "get_earthquake_context": get_earthquake_context,
    "get_population_for_geometry": get_population_for_geometry,
}
