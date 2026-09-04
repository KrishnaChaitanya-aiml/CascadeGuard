import csv
import io
import math

import httpx

BASE = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv"


def _basin_for_point(lat: float, lon: float) -> str:
    if lon < -20:
        return "NA" if lat > 0 else "SA"
    if lon >= -20 and lon < 20:
        return "NI" if lat >= 0 else "SI"
    if lon >= 20 and lon < 100:
        return "NI" if lat >= 0 else "SI"
    if lon >= 100 and lon < 160:
        return "WP"
    return "EP" if lat >= 0 else "SP"


def _distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def get_cyclone_track(latitude: float, longitude: float, event_date: str, radius_km: float = 500):
    basin = _basin_for_point(latitude, longitude)
    url = f"{BASE}/ibtracs.{basin}.list.v04r01.csv"
    response = httpx.get(url, timeout=60)
    response.raise_for_status()

    rows = csv.reader(io.StringIO(response.text))
    try:
        header = next(rows)
        next(rows)  # units row
    except StopIteration:
        return {"source": "NOAA IBTrACS", "evidence_type": "cyclone_track", "observations": []}

    index = {name: i for i, name in enumerate(header)}
    observations = []
    for row in rows:
        try:
            date = row[index["ISO_TIME"]]
            if not date.startswith(event_date):
                continue
            lat = float(row[index["LAT"]])
            lon = float(row[index["LON"]])
            distance = _distance_km(latitude, longitude, lat, lon)
            if distance > radius_km:
                continue
            observations.append(
                {
                    "sid": row[index.get("SID", 0)],
                    "name": row[index.get("NAME", 0)],
                    "basin": row[index.get("BASIN", 0)],
                    "iso_time": date,
                    "latitude": lat,
                    "longitude": lon,
                    "distance_km": round(distance, 1),
                    "wind_kt": row[index["WMO_WIND"]] if "WMO_WIND" in index else None,
                    "pressure_mb": row[index["WMO_PRES"]] if "WMO_PRES" in index else None,
                }
            )
        except (KeyError, ValueError, IndexError):
            continue
        if len(observations) >= 200:
            break

    return {
        "source": "NOAA IBTrACS",
        "evidence_type": "cyclone_track",
        "status": "available",
        "basin_queried": basin,
        "observations": observations,
        "limitations": [
            "IBTrACS contains best-track observations and provisional recent tracks; it is not a real-time warning service by itself.",
        ],
    }
