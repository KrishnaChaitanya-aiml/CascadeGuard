import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.aoi import build_aoi
from backend.agent import run_agent
from backend.event_service import get_available_events, get_disaster_event, get_flood_event
from backend.prompt_service import run_prompt_investigation

app = FastAPI(title="CascadeGuard", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


class InvestigationRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)


@app.get("/")
def home():
    if FRONTEND_FILE.exists():
        return FileResponse(FRONTEND_FILE)
    return {"project": "CascadeGuard", "status": "running"}


@app.get("/health")
def health():
    return {
        "project": "CascadeGuard",
        "status": "running",
        "frontend": FRONTEND_FILE.exists(),
    }


@app.get("/api/events")
def list_events(event_type: str = Query("FL")):
    try:
        events = get_available_events(event_type.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GDACS unavailable: {exc}") from exc
    return {"count": len(events), "event_type": event_type.upper(), "events": events}


@app.get("/api/events/{event_type}/{event_id}")
def api_event(event_type: str, event_id: str):
    try:
        event = get_disaster_event(event_id, event_type.upper())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GDACS unavailable: {exc}") from exc
    if event is None:
        raise HTTPException(status_code=404, detail="Disaster event not found")
    return event


@app.get("/api/investigate/{event_type}/{event_id}")
def investigate_api(
    event_type: str,
    event_id: str,
    scope: str = Query("event_buffer", pattern="^(event_buffer|footprint|country)$"),
    buffer_km: float = Query(25, ge=5, le=100),
    max_zones: int = Query(6, ge=1, le=8),
):
    try:
        event = get_disaster_event(event_id, event_type.upper())
        if event is None:
            raise HTTPException(status_code=404, detail="Disaster event not found")
        aoi = build_aoi(event, scope=scope, buffer_km=buffer_km, max_zones=max_zones)
        result = run_agent(event, aoi)
        return {"event": event, "investigation": result}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Investigation failed: {exc}") from exc


@app.post("/api/investigate/prompt")
def investigate_prompt(request: InvestigationRequest):
    try:
        return run_prompt_investigation(request.prompt)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "needs_clarification",
                "message": str(exc),
                "next_step": "Refine the request with a supported hazard and a specific place.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "status": "investigation_unavailable",
                "message": "The investigation could not complete because a live dependency failed.",
                "detail": str(exc),
            },
        ) from exc


@app.post("/api/investigate/prompt/stream")
def investigate_prompt_stream(request: InvestigationRequest):
    events: queue.Queue = queue.Queue()
    finished = object()

    def emit(item: dict):
        events.put(item)

    def worker():
        try:
            result = run_prompt_investigation(request.prompt, callback=emit)
            events.put({"type": "result", "data": result})
        except ValueError as exc:
            events.put(
                {
                    "type": "error",
                    "code": "needs_clarification",
                    "message": str(exc),
                }
            )
        except Exception as exc:
            events.put(
                {
                    "type": "error",
                    "code": "investigation_unavailable",
                    "message": "A live dependency failed before the investigation could complete.",
                    "detail": str(exc),
                }
            )
        finally:
            events.put(finished)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def stream():
        # Send an immediate event so the browser knows the connection is alive.
        yield "data: " + json.dumps({"type": "started", "message": "CascadeGuard investigation started."}) + "\n\n"
        while True:
            item = events.get()
            if item is finished:
                break
            yield "data: " + json.dumps(item, default=str) + "\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Legacy routes retained for compatibility.
@app.get("/events")
def legacy_events():
    return list_events("FL")


@app.get("/events/{event_id}")
def legacy_event(event_id: str):
    return api_event("FL", event_id)


@app.get("/investigate/{event_type}/{event_id}")
def legacy_generic_investigation(event_type: str, event_id: str):
    return investigate_api(event_type, event_id)


@app.get("/investigate/{event_id}")
def legacy_flood_investigation(event_id: str):
    return investigate_api("FL", event_id)
