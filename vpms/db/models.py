"""
VPMS Database Models — SQLAlchemy 2.0
All tables live in the vpms schema.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Numeric, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import uuid


# Shared metadata — all tables use the vpms schema
vpms_metadata = __import__("sqlalchemy").MetaData(schema="vpms")


class Base(DeclarativeBase):
    metadata = vpms_metadata


def utcnow():
    return datetime.now(timezone.utc)


# ─── SourceApp ────────────────────────────────────────────────────────────────
class SourceApp(Base):
    """Registered source applications."""

    __tablename__ = "source_apps"

    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text)
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ─── Job ─────────────────────────────────────────────────────────────────────
class Job(Base):
    """VPMS Job."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"vpms_{uuid.uuid4().hex[:12]}"
    )
    source_app: Mapped[str] = mapped_column(String(64), ForeignKey("vpms.source_apps.app_id"), index=True)
    external_reference_id: Mapped[Optional[str]] = mapped_column(String(256), index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(256), index=True)

    job_type: Mapped[str] = mapped_column(String(32))  # "content" or "video"
    request_type: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)

    request_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    production_plan: Mapped[Optional[dict]] = mapped_column(JSONB)
    output: Mapped[Optional[dict]] = mapped_column(JSONB)

    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    actual_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    budget_limit: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_by: Mapped[Optional[str]] = mapped_column(String(256))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


# ─── JobEvent ────────────────────────────────────────────────────────────────
class JobEvent(Base):
    """Job state change events."""

    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"ev_{uuid.uuid4().hex[:16]}"
    )
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    previous_state: Mapped[Optional[str]] = mapped_column(String(32))
    new_state: Mapped[Optional[str]] = mapped_column(String(32))
    worker: Mapped[Optional[str]] = mapped_column(String(64))
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ─── WorkerRegistry ──────────────────────────────────────────────────────────
class WorkerRegistry(Base):
    """Registered production workers."""

    __tablename__ = "worker_registry"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    base_url: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="AVAILABLE")
    visibility: Mapped[str] = mapped_column(String(32), default="internal")
    health_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    last_health_check: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    current_load: Mapped[int] = mapped_column(Integer, default=0)
    avg_latency_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    cost_per_job: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ─── WorkerCapability ─────────────────────────────────────────────────────────
class WorkerCapability(Base):
    """Capability offered by a worker with verification state."""

    __tablename__ = "worker_capabilities"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"cap_{uuid.uuid4().hex[:12]}"
    )
    worker_id: Mapped[str] = mapped_column(String(64), index=True)
    capability: Mapped[str] = mapped_column(String(64))

    code_present: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    integration_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    production_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False)

    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    average_latency_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    visibility: Mapped[str] = mapped_column(String(32), default="internal")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    def is_dispatchable(self) -> bool:
        """Can this capability accept normal production dispatch?"""
        return (
            self.code_present
            and self.credential_verified
            and self.integration_verified
            and self.healthy
        )


# ─── WorkerJob ────────────────────────────────────────────────────────────────
class WorkerJob(Base):
    """Worker-side job tracking."""

    __tablename__ = "worker_jobs"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"wrkj_{uuid.uuid4().hex[:12]}"
    )
    vpms_job_id: Mapped[str] = mapped_column(String(32), index=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    worker_job_id: Mapped[Optional[str]] = mapped_column(String(256), index=True)

    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(128))

    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    actual_cost: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    errors: Mapped[list] = mapped_column(JSONB, default=list)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ─── Artifact ────────────────────────────────────────────────────────────────
class Artifact(Base):
    """Produced artifacts."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"art_{uuid.uuid4().hex[:12]}"
    )
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    worker_job_id: Mapped[Optional[str]] = mapped_column(String(32))
    artifact_type: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    url: Mapped[Optional[str]] = mapped_column(String(1024))
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128))
    checksum: Mapped[Optional[str]] = mapped_column(String(128))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ─── QAReport ────────────────────────────────────────────────────────────────
class QAReport(Base):
    """QA reports for jobs."""

    __tablename__ = "qa_reports"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"qa_{uuid.uuid4().hex[:12]}"
    )
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    qa_type: Mapped[str] = mapped_column(String(32))  # TECHNICAL, CREATIVE
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    required_fixes: Mapped[list] = mapped_column(JSONB, default=list)
    decision: Mapped[str] = mapped_column(String(32))  # PASS, FAIL, NEEDS_REVIEW
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ─── Approval ────────────────────────────────────────────────────────────────
class Approval(Base):
    """Human approval records."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"apr_{uuid.uuid4().hex[:12]}"
    )
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    approval_type: Mapped[str] = mapped_column(String(64))  # SCRIPT, PRODUCTION, FINAL_VIDEO
    decision: Mapped[str] = mapped_column(String(32))  # APPROVED, REJECTED
    approved_by: Mapped[Optional[str]] = mapped_column(String(256))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)


# ─── PublishReceipt ──────────────────────────────────────────────────────────
class PublishReceipt(Base):
    """Publishing receipts."""

    __tablename__ = "publish_receipts"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"pub_{uuid.uuid4().hex[:12]}"
    )
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    platform: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    provider_job_id: Mapped[Optional[str]] = mapped_column(String(256))
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    published_url: Mapped[Optional[str]] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extra_data: Mapped[dict] = mapped_column(JSONB, default=dict)
