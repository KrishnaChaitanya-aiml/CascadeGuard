from typing import Any

import httpx
from shapely.geometry import shape

from backend.cache import get, set_value
from backend.config import CACHE_TTL_SECONDS, NOMINATIM_USER_AGENT

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

COUNTRY_BBOXES = {
    "NPL": [80.05, 26.35, 88.20, 30.45],
    "IND": [68.10, 6.55, 97.40, 35.70],
    "BGD": [88.00, 20.70, 92.70, 26.70],
    "PAK": [60.80, 23.60, 77.90, 37.10],
    "LKA": [79.50, 5.90, 81.90, 9.90],
    "PHL": [116.90, 4.60, 126.60, 21.20],
    "JPN": [122.90, 24.00, 153.90, 45.80],
    "MEX": [-118.40, 14.40, -86.70, 32.70],
    "USA": [-125.00, 24.40, -66.50, 49.40],
    "TUR": [25.60, 35.80, 44.80, 42.20],
}


def get_country_geometry(country: str | None, iso3: str | None) -> dict | None:
    key = f"country-geom:{iso3 or country}"
    cached = get(key)
    if cached is not None:
        return cached

    query = iso3 or country
    if not query:
        return None

    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "polygon_geojson": 1,
                "limit": 1,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=25,
        )
        response.raise_for_status()
        results = response.json()
        if results:
            geojson = results[0].get("geojson")
            if geojson:
                return set_value(key, geojson, CACHE_TTL_SECONDS)
    except Exception:
        pass

    if iso3 in COUNTRY_BBOXES:
        west, south, east, north = COUNTRY_BBOXES[iso3]
        return {
            "type": "Polygon",
            "coordinates": [[
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]],
            "_fallback_bbox": True,
        }

    return None


def bounds_from_geometry(geometry: dict | None):
    if not geometry:
        return None
    minx, miny, maxx, maxy = shape(geometry).bounds
    return [minx, miny, maxx, maxy]


def geocode_place(query: str) -> dict | None:
    key = f"geocode:{query.strip().lower()}"
    cached = get(key)
    if cached is not None:
        return cached

    query = query.strip()
    if not query:
        return None

    # Prefer Open-Meteo geocoding for the primary place lookup. It is
    # explicitly designed for global place-name search and avoids
    # putting repeated load on the public Nominatim instance.
    try:
        response = httpx.get(
            OPEN_METEO_GEOCODING_URL,
            params={"name": query, "count": 5, "language": "en", "format": "json"},
            timeout=20,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if results:
            item = results[0]
            result = {
                "display_name": ", ".join([x for x in [item.get("name"), item.get("admin1"), item.get("country")] if x]),
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
                "type": item.get("feature_code"),
                "class": "geocoding",
                "address": {
                    "city": item.get("name"),
                    "state": item.get("admin1"),
                    "country": item.get("country"),
                    "country_code": item.get("country_code"),
                    "ISO3166-1-alpha3": None,
                },
                "timezone": item.get("timezone"),
                "population": item.get("population"),
                "boundingbox": None,
                "provider": "Open-Meteo Geocoding",
            }
            # A small ISO3 lookup for common cases is sufficient for current
            # downstream enrichment providers. Unknown ISO3 stays None.
            iso2 = str(item.get("country_code") or "").upper()
            iso3_map = {
                "NP": "NPL", "IN": "IND", "BD": "BGD", "PK": "PAK",
                "LK": "LKA", "PH": "PHL", "JP": "JPN", "MX": "MEX",
                "US": "USA", "TR": "TUR", "CN": "CHN", "ID": "IDN",
                "AU": "AUS", "GB": "GBR", "FR": "FRA", "DE": "DEU",
                "IT": "ITA", "ES": "ESP", "BR": "BRA", "CA": "CAN",
            }
            result["address"]["ISO3166-1-alpha3"] = iso3_map.get(iso2)
            return set_value(key, result, CACHE_TTL_SECONDS)
    except Exception:
        pass

    # Deliberate fallback to Nominatim for richer administrative details.
    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=25,
        )
        response.raise_for_status()
        results = response.json()
        if results:
            item = results[0]
            result = {
                "display_name": item.get("display_name") or query,
                "latitude": float(item["lat"]),
                "longitude": float(item["lon"]),
                "type": item.get("type"),
                "class": item.get("class"),
                "address": item.get("address") or {},
                "boundingbox": item.get("boundingbox"),
                "provider": "Nominatim",
            }
            return set_value(key, result, CACHE_TTL_SECONDS)
    except Exception:
        pass

    return None

