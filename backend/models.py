from typing import Literal
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    id: str
    claim: str
    source: str
    source_url: str | None = None
    evidence_type: str = "observation"
    event_id: str | None = None
    location: str | None = None
    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    value: dict = Field(default_factory=dict)
    source_credibility: float = Field(0.7, ge=0.0, le=1.0)


class CascadeNode(BaseModel):
    label: str
    role: Literal["hazard", "failure", "exposure", "consequence", "service"] = "failure"
    status: Literal["confirmed", "inference", "unknown"] = "inference"
    evidence_ids: list[str] = Field(default_factory=list)


class CascadeCandidate(BaseModel):
    id: str
    title: str
    mechanism: str
    nodes: list[CascadeNode]
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    impact_score: float = Field(0.0, ge=0.0, le=100.0)
    priority_score: float = Field(0.0, ge=0.0, le=100.0)
    intervention: dict = Field(default_factory=dict)
    uncertainty: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class InvestigationResult(BaseModel):
    status: str
    summary: str
    aoi: dict
    source_status: list[dict]
    evidence_summary: dict
    cascades: list[CascadeCandidate]
    top_cascade_id: str | None = None
    mode: str = "incident"
    location: dict | None = None
    selected_events: list[dict] = Field(default_factory=list)
    overall_intervention: dict = Field(default_factory=dict)
    investigation_trace: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
