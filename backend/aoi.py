from math import ceil

from shapely.geometry import Point, box, shape
from shapely.ops import unary_union

from backend.config import MAX_ZONES
from backend.tools.geography import bounds_from_geometry, get_country_geometry
from backend.tools.gdacs import get_event_geometry


def _point_geometry(lat: float, lon: float):
    return {"type": "Point", "coordinates": [lon, lat]}


def resolve_event_geometry(event: dict):
    geometry = event.get("geometry") or {}
    if geometry.get("type") in {"Polygon", "MultiPolygon"}:
        return geometry

    event_id = str(event.get("event_id"))
    event_type = str(event.get("event_type", "FL")).upper()
    geometry_url = event.get("geometry_url")
    raw = get_event_geometry(event_type, event_id, geometry_url)
    if isinstance(raw, dict):
        if raw.get("type") == "Feature":
            geometry = raw.get("geometry") or {}
            if geometry.get("type") in {"Polygon", "MultiPolygon"}:
                return geometry
        if raw.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"}:
            return raw["geometry"]
        if raw.get("type") in {"Polygon", "MultiPolygon"}:
            return raw
    return geometry


def _grid_centers(polygon, max_zones: int):
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    cols = max(1, min(4, ceil((width / max(height, 0.1)) ** 0.5 * 2)))
    rows = max(1, min(3, ceil(max_zones / cols)))
    centers = []
    for row in range(rows):
        for col in range(cols):
            x = minx + width * (col + 0.5) / cols
            y = miny + height * (row + 0.5) / rows
            p = Point(x, y)
            if polygon.contains(p) or polygon.touches(p):
                centers.append((y, x))
    if not centers:
        rp = polygon.representative_point()
        centers = [(rp.y, rp.x)]
    return centers[:max_zones]


def build_aoi(event: dict, scope: str = "event_buffer", buffer_km: float = 25, max_zones: int = MAX_ZONES):
    scope = scope.lower()
    event_lat = event.get("latitude")
    event_lon = event.get("longitude")
    footprint_geometry = resolve_event_geometry(event)

    if scope == "country":
        country_geometry = get_country_geometry(event.get("country"), event.get("iso3"))
        if country_geometry:
            polygon = shape(country_geometry)
            zones = _grid_centers(polygon, max_zones)
            bounds = list(polygon.bounds)
            return {
                "scope": "country",
                "label": event.get("country") or event.get("iso3") or "country",
                "geometry": country_geometry,
                "bounds": bounds,
                "zones": [{"id": f"Z{i+1}", "latitude": lat, "longitude": lon, "radius_km": 20} for i, (lat, lon) in enumerate(zones)],
                "description": "Country-scale candidate scan using representative zones.",
            }

    if footprint_geometry and footprint_geometry.get("type") in {"Polygon", "MultiPolygon"}:
        polygon = shape(footprint_geometry)
        if scope == "footprint":
            zones = _grid_centers(polygon, max_zones)
            return {
                "scope": "footprint",
                "label": "GDACS hazard footprint",
                "geometry": footprint_geometry,
                "bounds": list(polygon.bounds),
                "zones": [{"id": f"Z{i+1}", "latitude": lat, "longitude": lon, "radius_km": max(8, buffer_km / 2)} for i, (lat, lon) in enumerate(zones)],
                "description": "Hazard-footprint candidate scan.",
            }
        buffered = polygon.buffer(buffer_km / 111.0)
        zones = _grid_centers(buffered, max_zones)
        return {
            "scope": "event_buffer",
            "label": "GDACS footprint + spatial buffer",
            "geometry": {
                "type": "Polygon",
                "coordinates": [list(buffered.exterior.coords)],
            },
            "bounds": list(buffered.bounds),
            "zones": [{"id": f"Z{i+1}", "latitude": lat, "longitude": lon, "radius_km": max(8, buffer_km / 2)} for i, (lat, lon) in enumerate(zones)],
            "description": f"Hazard footprint buffered by approximately {buffer_km} km.",
        }

    if event_lat is None or event_lon is None:
        raise ValueError("Disaster event has no usable coordinates")

    point = Point(float(event_lon), float(event_lat))
    buffer = point.buffer(buffer_km / 111.0)
    return {
        "scope": "event_buffer",
        "label": f"{buffer_km:g} km event-centered buffer",
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(buffer.exterior.coords)],
        },
        "bounds": list(buffer.bounds),
        "zones": [{"id": "Z1", "latitude": float(event_lat), "longitude": float(event_lon), "radius_km": min(20, max(5, buffer_km))}],
        "description": f"A buffer centered on the GDACS event coordinate; the default is {buffer_km:g} km.",
    }


def build_location_aoi(
    latitude: float,
    longitude: float,
    label: str,
    radius_km: float = 25,
    max_zones: int = 6,
):
    point = Point(float(longitude), float(latitude))
    buffer = point.buffer(radius_km / 111.0)
    zones = _grid_centers(buffer, max_zones)
    return {
        "scope": "city_scan",
        "label": f"{label} · {radius_km:g} km city investigation area",
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(buffer.exterior.coords)],
        },
        "bounds": list(buffer.bounds),
        "center": {"latitude": float(latitude), "longitude": float(longitude)},
        "radius_km": radius_km,
        "zones": [
            {
                "id": f"Z{i+1}",
                "latitude": lat,
                "longitude": lon,
                "radius_km": min(12, max(6, radius_km / 3)),
            }
            for i, (lat, lon) in enumerate(zones)
        ],
        "description": (
            f"City-centered investigation area around {label}, "
            f"with {len(zones)} representative zones."
        ),
    }
