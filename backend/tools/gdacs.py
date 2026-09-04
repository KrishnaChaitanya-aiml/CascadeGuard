import time
from typing import Any

import httpx

from backend.cache import get, set_value
from backend.config import CACHE_TTL_SECONDS, HTTP_TIMEOUT

GDACS_BASE_URL = "https://www.gdacs.org/gdacsapi/api"
HEADERS = {
    "User-Agent": "CascadeGuard/1.0",
    "Accept": "application/json",
}


def _get_json(url: str, params: dict, retries: int = 3) -> Any:
    last_error = None
    for attempt in range(retries):
        try:
            response = httpx.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, ValueError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GDACS request failed: {last_error}")


def get_disaster_events(event_type: str = "FL") -> dict:
    event_type = event_type.upper()
    key = f"gdacs:list:{event_type}"
    cached = get(key)
    if cached is not None:
        return cached

    data = _get_json(
        f"{GDACS_BASE_URL}/Events/geteventlist/SEARCH",
        {
            "eventlist": event_type,
            "alertlevel": "red;orange;green",
        },
    )
    return set_value(key, data, CACHE_TTL_SECONDS)


def get_disaster_event_by_id(event_type: str, event_id: str) -> dict:
    event_type = event_type.upper()
    key = f"gdacs:event:{event_type}:{event_id}"
    cached = get(key)
    if cached is not None:
        return cached

    data = _get_json(
        f"{GDACS_BASE_URL}/Events/geteventdata",
        {"eventtype": event_type, "eventid": event_id},
    )
    return set_value(key, data, CACHE_TTL_SECONDS)


def get_event_geometry(event_type: str, event_id: str, geometry_url: str | None = None):
    key = f"gdacs:geom:{event_type}:{event_id}"
    cached = get(key)
    if cached is not None:
        return cached

    if not geometry_url:
        geometry_url = (
            f"{GDACS_BASE_URL}/polygons/getgeometry"
            f"?eventtype={event_type}&eventid={event_id}&episodeid=1"
        )

    try:
        data = _get_json(geometry_url, {})
    except Exception:
        return None

    return set_value(key, data, CACHE_TTL_SECONDS)


def _coords_from_geometry(geometry: dict):
    if geometry.get("type") == "Point":
        coords = geometry.get("coordinates") or []
        if len(coords) >= 2:
            return float(coords[1]), float(coords[0])
    return None, None


def normalize_event(data: dict, event_type: str, event_id: str) -> dict:
    if data.get("type") == "Feature":
        properties = data.get("properties") or {}
        geometry = data.get("geometry") or {}
    else:
        properties = data.get("properties") or data
        geometry = data.get("geometry") or {}

    latitude, longitude = _coords_from_geometry(geometry)
    if latitude is None or longitude is None:
        latitude = properties.get("latitude")
        longitude = properties.get("longitude")

    urls = properties.get("url") or {}
    impact_metrics = []
    event_end = properties.get("todate")

    for index, item in enumerate(properties.get("sendai") or []):
        description = (item.get("description") or "").strip()
        value = item.get("sendaivalue")
        onset = item.get("onset_date")
        if not description or value in (None, ""):
            continue
        if onset and event_end and onset > event_end:
            continue
        impact_metrics.append(
            {
                "id": f"gdacs-impact-{index}",
                "description": description,
                "value": value,
                "country": item.get("country"),
                "region": item.get("region"),
                "onset_date": onset,
                "date_inserted": item.get("dateinsert"),
            }
        )

    return {
        "event_id": properties.get("eventid", event_id),
        "event_type": properties.get("eventtype", event_type),
        "episode_id": properties.get("episodeid"),
        "name": properties.get("name") or properties.get("description") or f"{event_type} event",
        "description": properties.get("description"),
        "country": properties.get("country"),
        "iso3": properties.get("iso3"),
        "alert_level": properties.get("alertlevel"),
        "alert_score": properties.get("alertscore"),
        "episode_alert_level": properties.get("episodealertlevel"),
        "episode_alert_score": properties.get("episodealertscore"),
        "event_source": properties.get("source"),
        "event_source_id": properties.get("sourceid"),
        "event_time": properties.get("fromdate"),
        "event_end": properties.get("todate"),
        "last_modified": properties.get("datemodified"),
        "is_current": str(properties.get("iscurrent", "")).lower() == "true",
        "is_temporary": str(properties.get("istemporary", "")).lower() == "true",
        "latitude": latitude,
        "longitude": longitude,
        "geometry": geometry,
        "report_url": urls.get("report") or properties.get("link"),
        "geometry_url": urls.get("geometry"),
        "news_url": urls.get("eventnews"),
        "media_url": urls.get("media"),
        "severity": properties.get("severitydata") or {},
        "affected_countries": properties.get("affectedcountries") or [],
        "impact_metrics": impact_metrics,
        "raw_event": data,
        "source": "GDACS",
    }


def normalize_event_list(data: dict, event_type: str) -> list[dict]:
    events = []
    for feature in data.get("features", []):
        event = normalize_event(feature, event_type, str(feature.get("properties", {}).get("eventid", "")))
        events.append(event)
    return events


def get_flood_events():
    return get_disaster_events("FL")


def get_flood_event_by_id(event_id):
    return get_disaster_event_by_id("FL", str(event_id))


def normalize_flood_events(data):
    return normalize_event_list(data, "FL")
