from backend.tools.gdacs import (
    get_disaster_event_by_id,
    get_disaster_events,
    normalize_event,
    normalize_event_list,
)


def get_disaster_event(event_id: str, event_type: str = "FL"):
    data = get_disaster_event_by_id(event_type, str(event_id))
    return normalize_event(data, event_type.upper(), str(event_id))


def get_available_events(event_type: str = "FL"):
    data = get_disaster_events(event_type.upper())
    return normalize_event_list(data, event_type.upper())


def get_available_flood_events():
    return get_available_events("FL")


def get_flood_event(event_id: str):
    return get_disaster_event(event_id, "FL")
