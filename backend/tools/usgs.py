import httpx

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def get_earthquake_context(latitude: float, longitude: float, starttime: str, endtime: str, radius_km: float = 150):
    params = {
        "format": "geojson",
        "latitude": latitude,
        "longitude": longitude,
        "maxradiuskm": radius_km,
        "starttime": starttime[:10],
        "endtime": endtime[:10],
        "minmagnitude": 4.0,
        "orderby": "magnitude",
        "limit": 50,
    }
    response = httpx.get(USGS_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    observations = []
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            continue
        observations.append(
            {
                "usgs_id": feature.get("id"),
                "place": properties.get("place"),
                "magnitude": properties.get("mag"),
                "time_ms": properties.get("time"),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
                "depth_km": coordinates[2] if len(coordinates) > 2 else None,
                "url": properties.get("url"),
            }
        )
    return {
        "source": "USGS",
        "evidence_type": "earthquake_context",
        "observations": observations,
        "limitations": [
            "USGS records earthquakes in the query area; absence of a record does not prove absence of damage.",
        ],
    }
