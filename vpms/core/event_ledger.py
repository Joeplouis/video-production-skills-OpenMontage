"""
Event Ledger — VPMS Core
Append-only event log for job state transitions.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


class EventType(str, Enum):
    """All VPMS event types."""

    # Job lifecycle
    JOB_CREATED = "JOB_CREATED"
    JOB_QUEUED = "JOB_QUEUED"
    STATE_TRANSITION = "STATE_TRANSITION"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_REJECTED = "JOB_REJECTED"
    JOB_FAILED = "JOB_FAILED"
    JOB_BLOCKED = "JOB_BLOCKED"
    JOB_READY = "JOB_READY"
    JOB_PUBLISHED = "JOB_PUBLISHED"

    # Worker events
    WORKER_REGISTERED = "WORKER_REGISTERED"
    WORKER_DEREGISTERED = "WORKER_DEREGISTERED"
    WORKER_HEALTH_CHECK = "WORKER_HEALTH_CHECK"
    CAPABILITY_REGISTERED = "CAPABILITY_REGISTERED"
    CAPABILITY_UPDATED = "CAPABILITY_UPDATED"
    WORKER_DISPATCHED = "WORKER_DISPATCHED"
    WORKER_RECEIPT_RECEIVED = "WORKER_RECEIPT_RECEIVED"
    WORKER_JOB_CANCELLED = "WORKER_JOB_CANCELLED"

    # Artifact events
    ARTIFACT_REGISTERED = "ARTIFACT_REGISTERED"
    ARTIFACT_DELETED = "ARTIFACT_DELETED"

    # QA events
    QA_REPORT_GENERATED = "QA_REPORT_GENERATED"
    QA_PASSED = "QA_PASSED"
    QA_FAILED = "QA_FAILED"

    # Approval events
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"

    # Idempotency
    IDEMPOTENT_REQUEST = "IDEMPOTENT_REQUEST"

    # Retry
    RETRY_INITIATED = "RETRY_INITIATED"


class JobEvent(BaseModel):
    """
    Immutable event record.
    Every state transition produces exactly one JobEvent.
    """

    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    job_id: str
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    worker: Optional[str] = None
    extra_data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"use_enum_values": False}


class EventLedger:
    """
    Event ledger service.
    Events are append-only — once written, they cannot be modified.
    """

    def __init__(self, repo=None):
        """
        Args:
            repo: EventRepository for persistence. If None, events are in-memory only.
        """
        self._repo = repo
        self._in_memory: list[JobEvent] = []

    def append(
        self,
        job_id: str,
        event_type: EventType,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        worker: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> JobEvent:
        """Append an event and persist it."""
        event = JobEvent(
            job_id=job_id,
            event_type=event_type,
            previous_state=previous_state,
            new_state=new_state,
            worker=worker,
            extra_data=metadata or {},
        )

        if self._repo:
            self._repo.save(event)
        else:
            self._in_memory.append(event)

        return event

    def get_events_for_job(self, job_id: str) -> list[JobEvent]:
        """Get all events for a job, in chronological order."""
        if self._repo:
            return self._repo.get_for_job(job_id)
        return [e for e in self._in_memory if e.job_id == job_id]

    def get_latest_event(self, job_id: str) -> Optional[JobEvent]:
        """Get the most recent event for a job."""
        events = self.get_events_for_job(job_id)
        return events[-1] if events else None

    def count_events(self, job_id: str) -> int:
        """Count events for a job."""
        return len(self.get_events_for_job(job_id))
