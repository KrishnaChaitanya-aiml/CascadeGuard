# CascadeGuard Architecture

```text
                 USER NATURAL-LANGUAGE REQUEST
                              |
                              v
                    PROMPT / INTENT LAYER
                 location + hazard scope + intent
                              |
                              v
                       NOMINATIM GEOCODER
                              |
                              v
                      GDACS EVENT DISCOVERY
             recent/current matching events by hazard
                              |
                              v
                       CITY / AOI ENGINE
          city center + buffer + representative zones
                              |
                              v
                    EVIDENCE COLLECTION
         +----------+----------+-----------+---------+
         |          |          |           |         |
        OSM     Open-Meteo  Flood API   WorldPop  hazard-specific
                                                     USGS/IBTrACS/FIRMS
         |          |          |           |         |
         +----------+----------+-----------+---------+
                              |
                              v
                       EVIDENCE LAYER
                  observations + conflicts
                              |
                              v
                    CASCADE HYPOTHESIS ENGINE
                     bounded hazard templates
                              |
                              v
                    DETERMINISTIC SCORING
              priority + confidence + impact
                              |
                              v
                       FEATHERLESS / QWEN
                 explanation + synthesis only
                              |
                              v
                        CLAIM VALIDATION
                              |
                              v
                       RANKED CASCADES
                              |
                              v
                    HIGH-LEVERAGE INTERVENTION
                              |
                              v
                       SINGLE-WINDOW UI
           map + risks + evidence + intervention + uncertainty
```

## Key design principle

The LLM is **not** allowed to invent the underlying world state. The backend owns event selection, source calls, evidence packaging and numeric ranking. The LLM is used to explain and synthesize the bounded candidate set.

## Live UI

The frontend consumes `POST /api/investigate/prompt/stream` as Server-Sent Events carried over a fetch stream. Events describe safe system actions only; private model reasoning is never sent to the browser.
