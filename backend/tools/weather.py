from typing import Iterable

import httpx

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
FLOOD_API_URL = "https://flood-api.open-meteo.com/v1/flood"


def get_precipitation(latitude: float, longitude: float, date: str):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": date,
        "end_date": date,
        "daily": "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max",
        "timezone": "UTC",
    }
    response = httpx.get(OPEN_METEO_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("wind_speed_10m_max", [])
    gusts = daily.get("wind_gusts_10m_max", [])
    observations = []
    for i, observed_date in enumerate(dates):
        observations.append(
            {
                "date": observed_date,
                "precipitation_mm": precip[i] if i < len(precip) else None,
                "wind_speed_10m_max_kmh": wind[i] if i < len(wind) else None,
                "wind_gusts_10m_max_kmh": gusts[i] if i < len(gusts) else None,
            }
        )
    return {
        "source": "Open-Meteo",
        "evidence_type": "weather_observation",
        "latitude": latitude,
        "longitude": longitude,
        "observations": observations,
        "timezone": data.get("timezone"),
        "limitations": [
            "Weather observations provide context and do not prove disaster causation.",
            "Historical reanalysis is not a direct field measurement at every point.",
        ],
    }


def get_weather_batch(points: Iterable[tuple[float, float]], date: str):
    points = list(points)
    if not points:
        return {"source": "Open-Meteo", "observations": [], "error": "No points"}

    params = {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "start_date": date,
        "end_date": date,
        "daily": "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max",
        "timezone": "UTC",
    }
    response = httpx.get(OPEN_METEO_URL, params=params, timeout=35)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = [data]

    observations = []
    for index, item in enumerate(data):
        daily = item.get("daily", {})
        dates = daily.get("time", [])
        if not dates:
            continue
        observations.append(
            {
                "latitude": points[index][0] if index < len(points) else item.get("latitude"),
                "longitude": points[index][1] if index < len(points) else item.get("longitude"),
                "date": dates[0],
                "precipitation_mm": (daily.get("precipitation_sum") or [None])[0],
                "wind_speed_10m_max_kmh": (daily.get("wind_speed_10m_max") or [None])[0],
                "wind_gusts_10m_max_kmh": (daily.get("wind_gusts_10m_max") or [None])[0],
            }
        )

    return {
        "source": "Open-Meteo",
        "evidence_type": "weather_observation",
        "observations": observations,
        "limitations": [
            "Weather observations provide context and do not prove disaster causation.",
        ],
    }


def get_flood_discharge_batch(points: Iterable[tuple[float, float]], start_date: str, end_date: str):
    points = list(points)
    if not points:
        return {"source": "Open-Meteo Flood API", "observations": []}

    params = {
        "latitude": ",".join(str(p[0]) for p in points),
        "longitude": ",".join(str(p[1]) for p in points),
        "daily": "river_discharge",
        "start_date": start_date,
        "end_date": end_date,
    }
    response = httpx.get(FLOOD_API_URL, params=params, timeout=45)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = [data]

    observations = []
    for index, item in enumerate(data):
        daily = item.get("daily", {})
        dates = daily.get("time", [])
        discharge = daily.get("river_discharge", [])
        for i, date in enumerate(dates):
            observations.append(
                {
                    "latitude": points[index][0] if index < len(points) else item.get("latitude"),
                    "longitude": points[index][1] if index < len(points) else item.get("longitude"),
                    "date": date,
                    "river_discharge_m3s": discharge[i] if i < len(discharge) else None,
                }
            )

    return {
        "source": "Open-Meteo Flood API",
        "evidence_type": "river_discharge_observation",
        "observations": observations,
        "limitations": [
            "The flood model is about 5 km resolution; nearby coordinate changes can select different river cells.",
            "Discharge observations do not by themselves establish infrastructure damage.",
        ],
    }
