import json
import time

import httpx

WORLDPOP_URL = "https://api.worldpop.org/v1/wopr/polytotal"
TASK_URL = "https://api.worldpop.org/v1/tasks"


def _find_numeric(obj, keys=("mean", "median", "estimate")):
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in obj.values():
            found = _find_numeric(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_numeric(value, keys)
            if found is not None:
                return found
    return None


def get_population_for_geometry(iso3: str | None, geometry: dict):
    if not iso3 or not geometry:
        return {
            "source": "WorldPop",
            "evidence_type": "population_exposure",
            "status": "unavailable",
            "error": "Missing ISO3 or geometry",
            "observations": [],
        }

    feature_collection = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {},
            "geometry": geometry,
        }],
    }

    params = {
        "iso3": iso3,
        "ver": "1.2",
        "geojson": json.dumps(feature_collection, separators=(",", ":")),
    }

    try:
        response = httpx.get(WORLDPOP_URL, params=params, timeout=45)
        response.raise_for_status()
        submission = response.json()

        task_id = submission.get("taskid") or submission.get("task_id") or submission.get("id")
        if not task_id:
            return {
                "source": "WorldPop",
                "evidence_type": "population_exposure",
                "status": "available",
                "result": submission,
                "observations": [],
                "limitations": ["WorldPop returned no task identifier; raw response retained."],
            }

        result = None
        for _ in range(4):
            task_response = httpx.get(f"{TASK_URL}/{task_id}", timeout=35)
            task_response.raise_for_status()
            result = task_response.json()
            status = str(result.get("status", "")).lower()
            if status in {"complete", "completed", "success", "finished"} or result.get("data"):
                break
            time.sleep(1.0)

        estimate = _find_numeric(result) if result else None
        observation = {
            "task_id": task_id,
            "population_estimate": estimate,
        }

        return {
            "source": "WorldPop",
            "evidence_type": "population_exposure",
            "status": "available",
            "observations": [observation],
            "result": result,
            "limitations": [
                "WorldPop provides modeled population estimates, not live headcounts.",
                "The estimate represents the queried AOI rather than real-time occupancy.",
            ],
        }
    except Exception as exc:
        return {
            "source": "WorldPop",
            "evidence_type": "population_exposure",
            "status": "unavailable",
            "error": str(exc),
            "observations": [],
            "limitations": ["WorldPop is an optional enrichment source."],
        }
