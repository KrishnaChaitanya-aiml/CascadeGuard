import math
from typing import Iterable

import httpx

from backend.config import OVERPASS_TIMEOUT

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def calculate_distance_km(lat1, lon1, lat2, lon2):
    radius = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _query(points: list[tuple[float, float]], radius_km: float):
    around_parts = []
    radius_m = int(radius_km * 1000)
    for lat, lon in points:
        around_parts.extend(
            [
                f'node["amenity"="hospital"](around:{radius_m},{lat},{lon});',
                f'way["bridge"](around:{radius_m},{lat},{lon});',
                f'way["highway"](around:{radius_m},{lat},{lon});',
                f'node["amenity"="school"](around:{radius_m},{lat},{lon});',
                f'node["amenity"="shelter"](around:{radius_m},{lat},{lon});',
                f'node["aeroway"="aerodrome"](around:{radius_m},{lat},{lon});',
            ]
        )
    query = "[out:json][timeout:45];(\n" + "\n".join(around_parts) + "\n);out center tags;"
    response = httpx.post(
        OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "CascadeGuard/1.0"},
        timeout=OVERPASS_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_affected_infrastructure(
    latitude: float,
    longitude: float,
    radius_km: float = 5,
):
    return get_infrastructure_batch([(latitude, longitude)], radius_km)[0]


def get_infrastructure_batch(
    points: Iterable[tuple[float, float]],
    radius_km: float = 15,
):
    points = list(points)
    if not points:
        return []

    data = _query(points, radius_km)
    observations = []
    seen = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        if lat is None or lon is None:
            continue

        if tags.get("amenity") == "hospital":
            category = "hospital"
        elif tags.get("bridge") == "yes":
            category = "bridge"
        elif tags.get("highway"):
            category = "road"
        elif tags.get("amenity") == "school":
            category = "school"
        elif tags.get("amenity") == "shelter":
            category = "shelter"
        elif tags.get("aeroway") == "aerodrome":
            category = "airport"
        else:
            continue

        key = (element.get("type"), element.get("id"))
        if key in seen:
            continue
        seen.add(key)

        nearest = min(
            calculate_distance_km(lat0, lon0, lat, lon)
            for lat0, lon0 in points
        )

        observations.append(
            {
                "osm_id": element.get("id"),
                "osm_type": element.get("type"),
                "category": category,
                "name": tags.get("name"),
                "distance_km": round(nearest, 2),
                "latitude": lat,
                "longitude": lon,
                "tags": tags,
            }
        )

    observations.sort(key=lambda item: item["distance_km"])

    result = {
        "source": "OpenStreetMap",
        "evidence_type": "infrastructure_observation",
        "query_centers": [{"latitude": p[0], "longitude": p[1]} for p in points],
        "radius_km": radius_km,
        "count": len(observations),
        "observations": observations,
        "limitations": [
            "Mapped presence does not prove damage or operational status.",
            "OSM completeness varies by region and asset type.",
            "Road observations are not a route-availability guarantee.",
        ],
    }

    return [result]
