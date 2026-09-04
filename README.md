# CascadeGuard

CascadeGuard is an evidence-grounded autonomous disaster-risk investigation system. A user describes the problem in plain language — for example, “Find all major cascading risks in Kathmandu, Nepal and tell me where intervention matters most.” The system resolves the location and relevant disaster events automatically, gathers live evidence, generates multiple candidate cascades, ranks them, and returns a decision-support intervention with explicit uncertainty.

## User workflow

`Plain-language prompt → intent/location resolution → relevant GDACS event discovery → city investigation area → live evidence → cascade hypotheses → deterministic scoring + Featherless/Qwen explanation → ranked risks → intervention → uncertainty`

## What the user enters

The user does **not** need to enter a GDACS event ID or choose a hazard. CascadeGuard can infer the requested hazard scope from the prompt. With a multi-hazard request, it searches the requested location for recent relevant GDACS events across the supported core hazards and investigates the matched events together.

## Core data sources

- **GDACS** — disaster event, alert level, reported impacts and event geometry when available. The published API exposes event retrieval and event-list endpoints.
- **OpenStreetMap / Overpass** — mapped bridges, hospitals, roads, schools, shelters and airports around representative investigation zones. Public Overpass instances should be queried sparingly, with caching/rate limiting and no parallel overload.
- **Open-Meteo Historical Weather** — precipitation, wind and related historical weather variables. Historical data is model/reanalysis based rather than a field measurement at every point.
- **Open-Meteo Flood API** — river discharge context at roughly 5 km model resolution for flood investigations.
- **WorldPop** — modeled population exposure enrichment for an investigation geometry.
- **USGS** — earthquake corroboration/context via its FDSN event service.
- **NOAA IBTrACS** — tropical-cyclone track/context for cyclone investigations.
- **NASA FIRMS** — optional active-fire observations for wildfire investigations; a free MAP_KEY is required and the service has usage limits.
- **Nominatim** — end-user-triggered location geocoding with caching and an identifying User-Agent. The public service has a strict usage policy and a maximum of 1 request/second.

## Why this is an agentic workflow

The model is not treated as the source of truth. External services provide observations; the backend constructs the evidence package, generates bounded cascade hypotheses, calculates numeric decision-support scores, and asks Featherless-hosted Qwen to refine the explanation. The interface shows safe operational trace events, not model chain-of-thought.

## Frontend

The dashboard is designed for a single desktop viewport: the user enters one natural-language request, sees the resolved location and matched events, watches safe agent activity live, views the investigation area on a map, reviews ranked cascades, checks the main intervention point, and opens the evidence inspector without leaving the page.

## Setup

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

Create `.env` from `.env.example` and set:

```text
FEATHERLESS_API_KEY=YOUR_KEY
```

The distributable project intentionally contains no `.env` file or API keys.
Featherless failures are surfaced in the live trace and the backend retains
only deterministic, evidence-linked scoring; it never fabricates a source or
observation.

Optional providers:

```text
FIRMS_MAP_KEY=YOUR_KEY
RELIEFWEB_APPNAME=YOUR_APP_NAME
```

Run:

```powershell
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/`.

## Main API

- `GET /health`
- `GET /api/events?event_type=FL`
- `GET /api/events/{event_type}/{event_id}`
- `GET /api/investigate/{event_type}/{event_id}`
- `POST /api/investigate/prompt`
- `POST /api/investigate/prompt/stream`

The streaming endpoint is used by the frontend for live operational updates.

## Safety and limitations

CascadeGuard is decision support, not an emergency command system. A mapped asset is not assumed to be damaged or operational. Weather observations are not treated as causal proof. Conflicting cumulative GDACS observations are preserved rather than summed. Priority/confidence/impact values are decision-support heuristics, not calibrated probabilities.

If a prompt does not contain a reliably resolvable place and supported hazard,
or if no relevant GDACS event can be found, the workflow stops with a
clarification/unavailable message instead of guessing.

Public OSM services have resource and usage policies. Cache and rate-limit requests. Nominatim's public service is intended for moderate end-user-triggered use and requires an identifying User-Agent.
