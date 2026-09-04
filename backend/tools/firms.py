import csv
import io

import httpx

from backend.config import FIRMS_MAP_KEY

FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def get_active_fire(event_bounds: list[float], date: str, source: str = "VIIRS_NOAA20_NRT"):
    if not FIRMS_MAP_KEY:
        return {
            "source": "NASA FIRMS",
            "evidence_type": "active_fire_observation",
            "status": "unavailable",
            "error": "FIRMS_MAP_KEY is not configured.",
            "observations": [],
            "limitations": ["NASA FIRMS requires a free MAP_KEY for API access."],
        }

    west, south, east, north = event_bounds
    area = f"{west},{south},{east},{north}"
    url = f"{FIRMS_URL}/{FIRMS_MAP_KEY}/{source}/{area}/1/{date}"
    response = httpx.get(url, timeout=45)
    response.raise_for_status()

    text = response.text
    rows = csv.DictReader(io.StringIO(text))
    observations = []
    for row in rows:
        try:
            observations.append(
                {
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                    "acq_date": row.get("acq_date"),
                    "acq_time": row.get("acq_time"),
                    "confidence": row.get("confidence"),
                    "frp": float(row["frp"]) if row.get("frp") else None,
                    "satellite": row.get("satellite"),
                }
            )
        except (KeyError, ValueError):
            continue

    return {
        "source": "NASA FIRMS",
        "evidence_type": "active_fire_observation",
        "status": "available",
        "observations": observations[:500],
        "limitations": [
            "Active-fire detections are satellite observations and do not equal complete fire perimeters.",
            "API access requires a FIRMS MAP_KEY.",
        ],
    }
