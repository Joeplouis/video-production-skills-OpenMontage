"""
VPMS Job Manager — Core orchestration service.
All job operations go through this service.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from vpms.core.state_machine import JobState, JobStateMachine, InvalidTransitionError
from vpms.core.event_ledger import EventLedger, EventType, JobEvent as JobEventModel
from vpms.db.models import Job, JobEvent as DBJobEvent
from vpms.db.repositories.job_repository import JobRepository, EventRepository
from vpms.db.repositories.artifact_repository import ArtifactRepository, ApprovalRepository


class JobManager:
    """
    Canonical job management service.
    All state transitions go through this service to ensure:
    1. Valid transitions only
    2. Every transition produces an event
    3. Events are persisted
    """

    def __init__(self, session: Session):
        self._session = session
        self._job_repo = JobRepository(session)
        self._event_repo = EventRepository(session)
        self._artifact_repo = ArtifactRepository(session)
        self._approval_repo = ApprovalRepository(session)
        self._state_machine = JobStateMachine()
        self._event_ledger = EventLedger(repo=self._event_repo)

    def create_content_job(
        self,
        source_app: str,
        request_type: str,
        content: dict,
        production: Optional[dict] = None,
        requested_outputs: Optional[list] = None,
        budget: Optional[dict] = None,
        external_reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        created_by: Optional[str] = None,
        priority: int = 5,
    ) -> tuple[Job, bool]:
        """
        Create a content job.
        Returns (job, created) where created=False if idempotency key matched.
        """
        # Idempotency check
        if idempotency_key:
            existing = self._job_repo.find_by_idempotency_key(source_app, idempotency_key)
            if existing:
                return existing, False

        # Merge request payload
        request_payload = {
            "content": content,
            "production": production or {},
            "requested_outputs": requested_outputs or [],
            "budget": budget or {},
        }

        job = self._job_repo.create(
            source_app=source_app,
            job_type="content",
            request_type=request_type,
            request_payload=request_payload,
            external_reference_id=external_reference_id,
            idempotency_key=idempotency_key,
            created_by=created_by,
            priority=priority,
            budget_limit=budget.get("maximum_usd") if budget else None,
        )

        # Emit creation event
        self._event_ledger.append(
            job_id=job.id,
            event_type=EventType.JOB_CREATED,
            new_state=job.status,
            metadata={
                "source_app": source_app,
                "request_type": request_type,
                "idempotency_key": idempotency_key,
            },
        )

        # Transition to QUEUED
        self._transition_to(job, JobState.QUEUED, EventType.JOB_QUEUED)

        return job, True

    def create_video_job(
        self,
        source_app: str,
        request_type: str,
        content: dict,
        production: Optional[dict] = None,
        requested_outputs: Optional[list] = None,
        budget: Optional[dict] = None,
        external_reference_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        created_by: Optional[str] = None,
        priority: int = 5,
    ) -> tuple[Job, bool]:
        """Create a video job (already has content/script)."""
        if idempotency_key:
            existing = self._job_repo.find_by_idempotency_key(source_app, idempotency_key)
            if existing:
                return existing, False

        request_payload = {
            "content": content,
            "production": production or {},
            "requested_outputs": requested_outputs or [],
            "budget": budget or {},
        }

        job = self._job_repo.create(
            source_app=source_app,
            job_type="video",
            request_type=request_type,
            request_payload=request_payload,
            external_reference_id=external_reference_id,
            idempotency_key=idempotency_key,
            created_by=created_by,
            priority=priority,
            budget_limit=budget.get("maximum_usd") if budget else None,
        )

        self._event_ledger.append(
            job_id=job.id,
            event_type=EventType.JOB_CREATED,
            new_state=job.status,
            metadata={"source_app": source_app, "request_type": request_type},
        )

        self._transition_to(job, JobState.QUEUED, EventType.JOB_QUEUED)

        return job, True

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        return self._job_repo.find_by_id(job_id)

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get lightweight status for a job."""
        job = self._job_repo.find_by_id(job_id)
        if not job:
            return None
        return {
            "job_id": job.id,
            "status": job.status,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
            "estimated_cost": float(job.estimated_cost) if job.estimated_cost else None,
            "actual_cost": float(job.actual_cost) if job.actual_cost else None,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }

    def transition_state(
        self,
        job_id: str,
        to_state: JobState,
        event_type: EventType = EventType.STATE_TRANSITION,
        worker: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Job:
        """
        Transition a job to a new state.
        This is the ONLY method that should mutate job status.
        """
        job = self._job_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        current = JobState(job.status)
        self._state_machine.transition(current, to_state)

        old_status = job.status
        job = self._job_repo.update_status(job, to_state)

        self._event_ledger.append(
            job_id=job_id,
            event_type=event_type,
            previous_state=old_status,
            new_state=to_state.value,
            worker=worker,
            metadata=metadata or {},
        )

        return job

    def _transition_to(self, job: Job, to_state: JobState, event_type: EventType) -> Job:
        """Internal transition helper."""
        old_status = job.status
        job = self._job_repo.update_status(job, to_state)

        self._event_ledger.append(
            job_id=job.id,
            event_type=event_type,
            previous_state=old_status,
            new_state=to_state.value,
        )

        return job

    def cancel_job(self, job_id: str, reason: Optional[str] = None) -> Job:
        """Cancel a job."""
        job = self._job_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        return self.transition_state(
            job_id,
            JobState.CANCELLED,
            EventType.JOB_CANCELLED,
            metadata={"reason": reason} if reason else {},
        )

    def approve_job(
        self,
        job_id: str,
        approval_type: str,
        approved_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> tuple[Job, Job]:
        """
        Approve a job at a gate.
        Returns (job, approval record).
        """
        job = self._job_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        current = JobState(job.status)

        # Determine transition based on approval type and state
        if current == JobState.WAITING_FOR_PRODUCTION_APPROVAL:
            to_state = JobState.PRODUCTION_APPROVED
            event_type = EventType.APPROVAL_GRANTED
        elif current == JobState.WAITING_FOR_FINAL_APPROVAL:
            to_state = JobState.READY
            event_type = EventType.APPROVAL_GRANTED
        elif current == JobState.SCRIPT_APPROVED:
            to_state = JobState.PRODUCTION_APPROVED
            event_type = EventType.APPROVAL_GRANTED
        else:
            raise InvalidTransitionError(current, current)

        # Record approval
        approval = self._approval_repo.create(
            job_id=job_id,
            approval_type=approval_type,
            decision="APPROVED",
            approved_by=approved_by,
            notes=notes,
        )

        # Transition job
        job = self.transition_state(
            job_id,
            to_state,
            event_type,
            metadata={"approval_id": approval.id, "approved_by": approved_by},
        )

        return job, approval

    def reject_job(
        self,
        job_id: str,
        approved_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> tuple[Job, Job]:
        """Reject a job."""
        job = self._job_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        approval = self._approval_repo.create(
            job_id=job_id,
            approval_type="REJECTION",
            decision="REJECTED",
            approved_by=approved_by,
            notes=notes,
        )

        job = self.transition_state(
            job_id,
            JobState.REJECTED,
            EventType.JOB_REJECTED,
            metadata={"approval_id": approval.id, "notes": notes},
        )

        return job, approval

    def get_events(self, job_id: str) -> list[JobEventModel]:
        """Get event history for a job."""
        return self._event_ledger.get_events_for_job(job_id)

    def get_artifacts(self, job_id: str) -> list:
        """Get artifacts for a job."""
        return self._artifact_repo.list_for_job(job_id)

    def get_approvals(self, job_id: str) -> list:
        """Get approvals for a job."""
        return self._approval_repo.list_for_job(job_id)

    def list_jobs(
        self,
        source_app: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        """List jobs with filters."""
        return self._job_repo.list_jobs(
            source_app=source_app,
            status=status,
            limit=limit,
            offset=offset,
        )
