"""
VPMS API Schemas — Pydantic models for request/response validation.
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# ─── Shared ───────────────────────────────────────────────────────────────────


class TimestampedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ─── Source App ───────────────────────────────────────────────────────────────


class SourceAppCreate(BaseModel):
    app_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=256)
    description: Optional[str] = None


# ─── Content Job ─────────────────────────────────────────────────────────────


class ContentJobRequest(BaseModel):
    source_app: str = Field(..., max_length=64, description="Source application identifier")
    request_type: str = Field(..., max_length=64, description="Type of content request")
    content: dict = Field(..., description="Content specification")
    production: Optional[dict] = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)
    budget: Optional[dict] = Field(default_factory=dict)
    external_reference_id: Optional[str] = Field(None, max_length=256)
    idempotency_key: Optional[str] = Field(None, max_length=256)
    priority: int = Field(5, ge=1, le=10)
    created_by: Optional[str] = Field(None, max_length=256)


class VideoJobRequest(BaseModel):
    source_app: str = Field(..., max_length=64)
    request_type: str = Field(..., max_length=64)
    content: dict = Field(...)
    production: Optional[dict] = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)
    budget: Optional[dict] = Field(default_factory=dict)
    external_reference_id: Optional[str] = Field(None, max_length=256)
    idempotency_key: Optional[str] = Field(None, max_length=256)
    priority: int = Field(5, ge=1, le=10)
    created_by: Optional[str] = Field(None, max_length=256)


# ─── Job Response ─────────────────────────────────────────────────────────────


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_app: str
    external_reference_id: Optional[str] = None
    job_type: str
    request_type: str
    status: str
    priority: int
    request_payload: dict = Field(default_factory=dict)
    production_plan: Optional[dict] = None
    output: Optional[dict] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    budget_limit: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ─── Events ──────────────────────────────────────────────────────────────────


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    event_type: str
    timestamp: datetime
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    worker: Optional[str] = None
    extra_data: dict = Field(default_factory=dict)


# ─── Artifacts ───────────────────────────────────────────────────────────────


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    artifact_type: str
    name: str
    url: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    extra_data: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class ArtifactListResponse(BaseModel):
    job_id: str
    artifacts: list[ArtifactResponse]
    total: int


# ─── Approval ────────────────────────────────────────────────────────────────


class ApprovalRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    approved_by: Optional[str] = Field(None, max_length=256)
    notes: Optional[str] = None
    extra_data: Optional[dict] = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    approval_type: str
    decision: str
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime


# ─── Cancel ──────────────────────────────────────────────────────────────────


class CancelRequest(BaseModel):
    reason: Optional[str] = None


class CancelResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ─── Workers ─────────────────────────────────────────────────────────────────


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    name: str
    base_url: Optional[str] = None
    status: str
    visibility: str
    health_status: str
    last_health_check: Optional[datetime] = None
    max_concurrency: int
    current_load: int
    avg_latency_seconds: Optional[float] = None
    cost_per_job: Optional[float] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WorkerListResponse(BaseModel):
    workers: list[WorkerResponse]
    total: int


# ─── Capabilities ────────────────────────────────────────────────────────────


class CapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    worker_id: str
    capability: str
    code_present: bool
    credential_verified: bool
    integration_verified: bool
    production_verified: bool
    healthy: bool
    estimated_cost: Optional[float] = None
    average_latency_seconds: Optional[float] = None
    max_concurrency: int
    visibility: str
    is_active: bool


class CapabilityListResponse(BaseModel):
    capabilities: list[CapabilityResponse]
    total: int


# ─── Health ──────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    timestamp: datetime
