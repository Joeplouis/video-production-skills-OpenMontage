"""
VPMS Job Repository — Database operations for jobs.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from vpms.db.models import Job, JobEvent
from vpms.core.state_machine import JobState
from vpms.core.event_ledger import JobEvent as JobEventModel, EventType


class JobRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        source_app: str,
        job_type: str,
        request_type: str,
        request_payload: dict,
        external_reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        created_by: Optional[str] = None,
        priority: int = 5,
        budget_limit: Optional[float] = None,
    ) -> Job:
        """Create a new job."""
        job = Job(
            source_app=source_app,
            job_type=job_type,
            request_type=request_type,
            request_payload=request_payload,
            external_reference_id=external_reference_id,
            idempotency_key=idempotency_key,
            created_by=created_by,
            priority=priority,
            budget_limit=budget_limit,
            status=JobState.CREATED.value,
        )
        self._session.add(job)
        self._session.flush()
        return job

    def find_by_id(self, job_id: str) -> Optional[Job]:
        """Find a job by ID."""
        stmt = select(Job).where(Job.id == job_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def find_by_idempotency_key(
        self, source_app: str, idempotency_key: str
    ) -> Optional[Job]:
        """Find existing job by source app + idempotency key."""
        stmt = select(Job).where(
            Job.source_app == source_app,
            Job.idempotency_key == idempotency_key,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def update_status(
        self,
        job: Job,
        new_status: JobState,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Job:
        """Update job status."""
        job.status = new_status.value
        if error_code:
            job.error_code = error_code
        if error_message:
            job.error_message = error_message
        if new_status in {
            JobState.READY,
            JobState.PUBLISHED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.REJECTED,
        }:
            job.completed_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self._session.flush()
        return job

    def list_jobs(
        self,
        source_app: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs with optional filters."""
        stmt = select(Job)
        if source_app:
            stmt = stmt.where(Job.source_app == source_app)
        if status:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def count(self, source_app: Optional[str] = None, status: Optional[str] = None) -> int:
        """Count jobs matching filters."""
        stmt = select(func.count(Job.id))
        if source_app:
            stmt = stmt.where(Job.source_app == source_app)
        if status:
            stmt = stmt.where(Job.status == status)
        return self._session.execute(stmt).scalar_one()


class EventRepository:
    """Persist job events."""

    def __init__(self, session: Session):
        self._session = session

    def save(self, event: JobEventModel) -> JobEvent:
        """Persist a job event."""
        db_event = JobEvent(
            id=event.event_id,
            job_id=event.job_id,
            event_type=event.event_type.value,
            timestamp=event.timestamp,
            previous_state=event.previous_state,
            new_state=event.new_state,
            worker=event.worker,
            extra_data=event.extra_data,
        )
        self._session.add(db_event)
        self._session.flush()
        return db_event

    def get_for_job(self, job_id: str) -> list[JobEvent]:
        """Get all events for a job."""
        stmt = (
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.timestamp.asc())
        )
        return list(self._session.execute(stmt).scalars().all())
