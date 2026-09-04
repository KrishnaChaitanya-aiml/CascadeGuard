# CascadeGuard Demo

## The demo sentence

> “Find all major cascading risks in Kathmandu, Nepal and tell me where intervention matters most.”

The user enters only that sentence. CascadeGuard resolves the location, discovers relevant recent GDACS events automatically, investigates the city area, and returns ranked cascade risks.

## What the audience should notice

1. **No event ID is required.** The system resolves the relevant event(s).
2. **The map is an investigation area, not a single 5 km point query.**
3. **Multiple cascade hypotheses are ranked**, not just one generated answer.
4. **Evidence and inference are separated.**
5. **The live trace shows system actions** such as locating the city, finding events, querying sources, generating hypotheses, and validating the result.
6. **The intervention panel answers “where should attention go first?”**
7. **Uncertainty is visible instead of hidden.**

## Suggested prompts

- `Find all major cascading risks in Kathmandu, Nepal and tell me where intervention matters most.`
- `Investigate flood-related cascading risks around Kathmandu, Nepal.`
- `Analyze earthquake risks in Tokyo, Japan and rank the most important secondary failures.`
- `Find major cyclone-related cascading risks around Manila, Philippines.`
- `Find wildfire cascading risks around Los Angeles, USA.`

## Safety language for judges

CascadeGuard does not issue dispatch orders, public warnings, or autonomous physical interventions. It produces evidence-backed decision support for human responders.
