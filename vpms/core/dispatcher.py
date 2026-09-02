"""
VPMS Dispatcher — Dispatches jobs to workers and handles receipts.
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from vpms.core.state_machine import JobState
from vpms.core.event_ledger import EventType
from vpms.core.job_manager import JobManager
from vpms.db.models import WorkerJob, Artifact
from vpms.db.repositories.job_repository import JobRepository
from vpms.db.repositories.worker_repository import CapabilityRepository
from vpms.db.repositories.artifact_repository import ArtifactRepository
from vpms.db.session import get_db_session


class Dispatcher:
    """
    Dispatches jobs to workers and processes receipts.
    Ensures no direct transition from DISPATCHING to COMPLETE.
    Every dispatch creates a WorkerJob record.
    Every receipt creates an artifact record.
    """

    def __init__(self, session: Session):
        self._session = session
        self._job_repo = JobRepository(session)
        self._cap_repo = CapabilityRepository(session)
        self._artifact_repo = ArtifactRepository(session)
        self._job_manager = JobManager(session)

    def dispatch(
        self,
        vpms_job_id: str,
        worker_id: str,
        capability: str,
        job_request: dict,
    ) -> WorkerJob:
        """
        Dispatch a job to a worker.
        Returns the WorkerJob record.
        """
        # Verify capability is dispatchable
        cap = self._cap_repo.get_capability(worker_id, capability)
        if not cap:
            raise ValueError(
                f"Capability {capability} not found for worker {worker_id}"
            )
        if not cap.is_dispatchable():
            raise ValueError(
                f"Capability {capability} on worker {worker_id} is not dispatchable "
                f"(code_present={cap.code_present}, "
                f"credential_verified={cap.credential_verified}, "
                f"integration_verified={cap.integration_verified}, "
                f"healthy={cap.healthy})"
            )

        job = self._job_repo.find_by_id(vpms_job_id)
        if not job:
            raise ValueError(f"Job not found: {vpms_job_id}")

        # Create worker job record
        worker_job = WorkerJob(
            vpms_job_id=vpms_job_id,
            worker_id=worker_id,
            status="PENDING",
        )
        self._session.add(worker_job)
        self._session.flush()

        # Transition job to DISPATCHING
        self._job_manager.transition_state(
            vpms_job_id,
            JobState.DISPATCHING,
            EventType.WORKER_DISPATCHED,
            worker=worker_id,
            metadata={
                "worker_job_id": worker_job.id,
                "capability": capability,
            },
        )

        return worker_job

    def process_receipt(
        self,
        worker_job_id: str,
        receipt: dict,
    ) -> WorkerJob:
        """
        Process a worker receipt.
        Updates WorkerJob, creates artifacts, and advances job state.
        """
        worker_job = self._session.query(WorkerJob).filter(
            WorkerJob.id == worker_job_id
        ).scalar_one_or_none()
        if not worker_job:
            raise ValueError(f"Worker job not found: {worker_job_id}")

        vpms_job_id = worker_job.vpms_job_id

        # Update worker job with receipt data
        worker_job.status = receipt.get("status", worker_job.status)
        worker_job.provider = receipt.get("provider", worker_job.provider)
        worker_job.model = receipt.get("model", worker_job.model)
        worker_job.actual_cost = receipt.get("actual_cost", worker_job.actual_cost)
        worker_job.completed_at = datetime.now(timezone.utc)

        if receipt.get("errors"):
            worker_job.errors = receipt["errors"]

        self._session.flush()

        # Process artifacts
        artifacts = receipt.get("artifacts", [])
        for art_data in artifacts:
            self._artifact_repo.create(
                job_id=vpms_job_id,
                worker_job_id=worker_job_id,
                artifact_type=art_data.get("type", "unknown"),
                name=art_data.get("name", "unknown"),
                url=art_data.get("url"),
                file_path=art_data.get("file_path"),
                file_size_bytes=art_data.get("size_bytes"),
                mime_type=art_data.get("mime_type"),
                duration_seconds=art_data.get("duration_seconds"),
                width=art_data.get("width"),
                height=art_data.get("height"),
                metadata=art_data.get("metadata", {}),
            )

        # Log receipt event
        self._job_manager._event_ledger.append(
            job_id=vpms_job_id,
            event_type=EventType.WORKER_RECEIPT_RECEIVED,
            worker=worker_job.worker_id,
            metadata={
                "worker_job_id": worker_job_id,
                "receipt_status": receipt.get("status"),
                "artifacts_count": len(artifacts),
            },
        )

        # Advance state based on receipt status
        if receipt.get("status") == "COMPLETED":
            self._job_manager.transition_state(
                vpms_job_id,
                JobState.PROVIDER_CONFIRMED,
                EventType.WORKER_RECEIPT_RECEIVED,
                worker=worker_job.worker_id,
                metadata={"worker_job_id": worker_job_id},
            )

        elif receipt.get("status") == "FAILED":
            if self._is_transient_error(receipt.get("errors", [])):
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.RETRYABLE_FAILURE,
                    EventType.JOB_FAILED,
                    worker=worker_job.worker_id,
                    metadata={"worker_job_id": worker_job_id, "errors": receipt["errors"]},
                )
            else:
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.FAILED,
                    EventType.JOB_FAILED,
                    worker=worker_job.worker_id,
                    metadata={"worker_job_id": worker_job_id, "errors": receipt["errors"]},
                )

        return worker_job

    def _is_transient_error(self, errors: list[str]) -> bool:
        """Determine if errors are transient (retryable)."""
        transient_keywords = [
            "timeout",
            "temporary",
            "unavailable",
            "rate limit",
            "connection",
            "network",
        ]
        error_text = " ".join(errors).lower()
        return any(kw in error_text for kw in transient_keywords)
