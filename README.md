# CascadeGuard

### Autonomous Cascading-Risk Investigation & Intervention System

> **Most systems tell you what happened. CascadeGuard investigates what could fail next — and where to intervene first.**

## Overview

CascadeGuard is an autonomous AI system that investigates how a disaster can propagate through interconnected infrastructure and services.

Instead of requiring users to manually identify disaster events, locations, APIs, or investigation areas, CascadeGuard accepts a natural-language request and autonomously:

**identifies the relevant event → gathers real-world evidence → builds system context → generates multiple cascade hypotheses → verifies them → prioritizes risk → recommends interventions.**

The objective is to turn fragmented disaster information into **evidence-backed, prioritized decision support**.

---

## The Problem

Disasters rarely remain isolated events.

A flood can disrupt a bridge, the bridge can disrupt transportation, and transportation disruption can isolate communities or reduce access to critical services.

```text
Disaster
   ↓
Infrastructure disruption
   ↓
Connectivity loss
   ↓
Service disruption
   ↓
Secondary impact
```

Existing disaster intelligence can tell us **what happened**. The harder problem is determining **what could fail next because systems are interconnected, how strongly that cascade is supported by evidence, and where intervention should happen first.**

---

## How CascadeGuard Works

```text
Natural-Language Request
          ↓
   Event Identification
          ↓
  Investigation Area
          ↓
   Evidence Collection
          ↓
   Context & Dependency
          ↓
 Multiple Cascade Hypotheses
          ↓
 Evidence Verification
          ↓
 Risk Prioritization
          ↓
 Intervention per Cascade
          ↓
 Highest-Priority Intervention
```

CascadeGuard uses one investigation agent that coordinates multiple real-world data tools. The agent determines what information is needed, retrieves it, evaluates the resulting evidence, and continues the investigation based on what it discovers.

---

## Core Intelligence

### Context Construction

CascadeGuard identifies relevant entities around the disaster—such as roads, bridges, hospitals, communities, supply routes, and environmental conditions—and models meaningful relationships between them.

This creates a dependency-aware view of the affected system rather than treating each observation independently.

### Cascade Analysis

The system explores multiple possible downstream failure pathways instead of producing a single generic prediction.

Each cascade is treated as a **hypothesis** and evaluated against the available evidence.

### Risk Prioritization

Cascades are evaluated using separate dimensions:

- **Confidence** — strength of supporting evidence
- **Impact** — potential severity
- **Priority** — relative importance and urgency

### Intervention Engine

Every significant cascade receives a recommended intervention, including the target, rationale, and supporting evidence.

CascadeGuard then identifies the **overall highest-priority intervention**—the intervention point with the greatest potential to reduce downstream risk.

---

## Evidence-First Design

CascadeGuard is designed to avoid turning plausible AI reasoning into false facts.

The system distinguishes between:

**Observed** — directly supported by a source  
**Inferred** — derived from observations  
**Hypothesis** — a possible downstream outcome  
**Unknown** — insufficient evidence

For example, knowing that a bridge exists does **not** mean the bridge is damaged.

Likewise, recorded rainfall does **not** automatically prove a specific infrastructure failure was caused by that rainfall.

When evidence is insufficient, CascadeGuard reports uncertainty rather than fabricating an answer.

---

## Real-World Data

Depending on the investigation, CascadeGuard can use real external sources including:

- **GDACS** — disaster events and reported impacts
- **OpenStreetMap / Overpass** — infrastructure and geographic context
- **Open-Meteo** — weather observations
- **Flood / river datasets** — hydrological context
- **Population datasets** — exposure context
- **USGS** — earthquake information
- **NOAA IBTrACS** — cyclone information
- **NASA FIRMS** — wildfire information

The system uses hazard-aware data selection rather than querying every source for every investigation.

---

## Reliability

CascadeGuard deliberately fails safely.

Invalid or ambiguous requests do not produce fabricated disasters, locations, statistics, or conclusions.

The system also surfaces:

- missing data
- conflicting sources
- unavailable APIs
- unverified conditions
- evidence limitations

This makes uncertainty an explicit part of the result rather than something hidden from the user.

---

## Dashboard

The interface is designed as an operational investigation dashboard focused on five questions:

**What happened?**  
Current event and context.

**What could fail next?**  
Ranked cascade hypotheses.

**Why do we believe it?**  
Evidence and source provenance.

**What should we do first?**  
Highest-priority intervention.

**What remains uncertain?**  
Conflicts and data gaps.

A live investigation trace shows observable agent actions without exposing hidden model reasoning.

---

## Technology

- Python
- FastAPI
- Featherless.ai
- Qwen open-weight model
- OpenStreetMap / Overpass
- GDACS
- Open-Meteo
- Leaflet
- REST APIs
- Structured evidence and validation

---

## Safety

CascadeGuard is a **human decision-support system**.

It does not autonomously dispatch emergency services, issue public warnings, control infrastructure, or perform physical interventions.

Its recommendations are intended to help humans determine **where attention should be focused first**.

---

## Why CascadeGuard?

The key shift is:

> **From reporting isolated disaster information to investigating connected failure chains and prioritizing intervention.**

CascadeGuard does not simply answer:

> *“What happened?”*

It investigates:

> **“What could fail next, why do we believe it, and where can intervention have the greatest leverage?”**

---

## Project

**CascadeGuard**  
*Autonomous Cascading-Risk Investigation & Intervention System*

Built for **HackWave 3.0 — Autonomous AI Workflows**.
