"""
VPMS Production Director — Golden Path Orchestrator (Phase 2)
Orchestrates a two-person podcast episode through the complete production pipeline:

  Episode Request
  → Chronos (research + script)
  → Independent Script Evaluation
  → Human Script Approval
  → Avatar Webinar (render)
  → VMF (final assembly)
  → Technical QA
  → Creative QA
  → Human Final Approval
  → READY

Publishing may remain manual for the first successful test.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from vpms.core.state_machine import JobState
from vpms.core.event_ledger import EventType
from vpms.core.job_manager import JobManager
from vpms.core.dispatcher import Dispatcher
from vpms.db.repositories.job_repository import JobRepository
from vpms.db.repositories.worker_repository import CapabilityRepository
from vpms.db.models import WorkerJob
from vpms.db.session import get_db_session

logger = logging.getLogger(__name__)

# ─── Worker routing map ────────────────────────────────────────────────────────

# Which VPMS capability maps to which worker
GOLDEN_PATH_WORKERS: dict[str, str] = {
    "content_research": "chronos",
    "script_generation": "chronos",
    "full_episode_pipeline": "chronos",
    "render_from_script": "avatar-webinar",
    "podcast_production": "avatar-webinar",
    "podcast_hybrid": "avatar-webinar",
    "pipeline_video": "vmf",
    "ugc_batch": "vmf",
}

# Default worker per production phase
PHASE_WORKER: dict[str, str] = {
    "RESEARCHING": "chronos",
    "SCRIPTING": "chronos",
    "PRODUCTION_APPROVED": "avatar-webinar",
    "ASSET_GENERATION": "vmf",
    "RENDERING": "vmf",
}


class ProductionDirector:
    """
    Orchestrates job execution through the Golden Path.

    Responsibilities:
    - Select the right worker for each phase
    - Dispatch jobs to workers via adapters
    - Track receipts and advance job state
    - Handle async polling for workers that don't web-queue
    - Record all receipts and artifacts

    The Director does NOT own the state machine — it delegates to JobManager.
    """

    def __init__(self, session: Session):
        self._session = session
        self._job_manager = JobManager(session)
        self._dispatcher = Dispatcher(session)
        self._cap_repo = CapabilityRepository(session)
        self._job_repo = JobRepository(session)

    def get_worker_for_capability(self, capability: str) -> Optional[str]:
        """Return the primary worker ID for a capability."""
        return GOLDEN_PATH_WORKERS.get(capability)

    def get_worker_for_state(self, state: JobState) -> Optional[str]:
        """Return the worker that should handle a given job state."""
        return PHASE_WORKER.get(state.value)

    # ─── Phase 1: Chronos — Research + Script ──────────────────────────────────

    def dispatch_research_and_script(
        self,
        vpms_job_id: str,
        content: dict,
        metadata: Optional[dict] = None,
    ) -> WorkerJob:
        """
        Dispatch to Chronos for research and script generation.
        Maps to the 'full_episode_pipeline' capability.
        """
        from vpms.adapters.chronos import ChronosWorkerAdapter

        adapter = ChronosWorkerAdapter()

        from vpms.adapters.base import WorkerJobRequest

        job_request = WorkerJobRequest(
            vpms_job_id=vpms_job_id,
            worker="chronos",
            production_type="full_episode_pipeline",
            content=content,
            speakers=metadata.get("speakers") if metadata else None,
            metadata=metadata or {},
        )

        # Sync dispatch through the adapter
        receipt = asyncio.get_event_loop().run_until_complete(
            adapter.dispatch(job_request)
        )

        # Record the worker job
        worker_job = WorkerJob(
            vpms_job_id=vpms_job_id,
            worker_id="chronos",
            worker_job_id=receipt.worker_job_id,
            status=receipt.status,
        )
        self._session.add(worker_job)
        self._session.flush()

        # Transition to RESEARCHING
        self._job_manager.transition_state(
            vpms_job_id,
            JobState.RESEARCHING,
            EventType.WORKER_DISPATCHED,
            worker="chronos",
            metadata={"worker_job_id": worker_job.id, "capability": "full_episode_pipeline"},
        )

        return worker_job

    # ─── Phase 2: Avatar Webinar — Render ──────────────────────────────────────

    def dispatch_avatar_render(
        self,
        vpms_job_id: str,
        script: dict,
        speakers: list[dict],
        output: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> WorkerJob:
        """
        Dispatch to Avatar Webinar for podcast rendering.
        Uses the render_from_script one-call endpoint.
        """
        from vpms.adapters.avatar_webinar import AvatarWebinarWorkerAdapter

        adapter = AvatarWebinarWorkerAdapter()

        from vpms.adapters.base import WorkerJobRequest

        job_request = WorkerJobRequest(
            vpms_job_id=vpms_job_id,
            worker="avatar-webinar",
            production_type="podcast_hybrid",
            script=script,
            speakers=speakers,
            output=output or {},
            metadata=metadata or {},
        )

        receipt = asyncio.get_event_loop().run_until_complete(
            adapter.dispatch(job_request)
        )

        worker_job = WorkerJob(
            vpms_job_id=vpms_job_id,
            worker_id="avatar-webinar",
            worker_job_id=receipt.worker_job_id,
            status=receipt.status,
            provider="avatar-webinar",
            estimated_cost=receipt.estimated_cost,
        )
        self._session.add(worker_job)
        self._session.flush()

        self._job_manager.transition_state(
            vpms_job_id,
            JobState.ASSET_GENERATION,
            EventType.WORKER_DISPATCHED,
            worker="avatar-webinar",
            metadata={"worker_job_id": worker_job.id, "capability": "render_from_script"},
        )

        return worker_job

    # ─── Phase 3: VMF — Final Assembly ─────────────────────────────────────────

    def dispatch_vmf_assembly(
        self,
        vpms_job_id: str,
        source_video_url: str,
        metadata: Optional[dict] = None,
    ) -> WorkerJob:
        """
        Dispatch to VMF for final assembly (clipping, shorts generation, etc.).
        """
        from vpms.adapters.vmf import VMFWorkerAdapter

        adapter = VMFWorkerAdapter()

        from vpms.adapters.base import WorkerJobRequest

        job_request = WorkerJobRequest(
            vpms_job_id=vpms_job_id,
            worker="vmf",
            production_type="pipeline_video",
            content={"source_video_url": source_video_url},
            metadata=metadata or {},
        )

        receipt = asyncio.get_event_loop().run_until_complete(
            adapter.dispatch(job_request)
        )

        worker_job = WorkerJob(
            vpms_job_id=vpms_job_id,
            worker_id="vmf",
            worker_job_id=receipt.worker_job_id,
            status=receipt.status,
            provider="vmf",
        )
        self._session.add(worker_job)
        self._session.flush()

        self._job_manager.transition_state(
            vpms_job_id,
            JobState.RENDERING,
            EventType.WORKER_DISPATCHED,
            worker="vmf",
            metadata={"worker_job_id": worker_job.id, "capability": "pipeline_video"},
        )

        return worker_job

    # ─── Receipt Processing ─────────────────────────────────────────────────────

    def poll_worker_status(self, worker_job_id: str, worker_id: str) -> dict:
        """
        Poll a worker's status and return a receipt dict.
        Used for async workers that don't call back.
        """
        if worker_id == "chronos":
            from vpms.adapters.chronos import ChronosWorkerAdapter
            adapter = ChronosWorkerAdapter()
        elif worker_id == "avatar-webinar":
            from vpms.adapters.avatar_webinar import AvatarWebinarWorkerAdapter
            adapter = AvatarWebinarWorkerAdapter()
        elif worker_id == "vmf":
            from vpms.adapters.vmf import VMFWorkerAdapter
            adapter = VMFWorkerAdapter()
        else:
            return {"status": "FAILED", "errors": [f"Unknown worker: {worker_id}"]}

        receipt = asyncio.get_event_loop().run_until_complete(
            adapter.get_status(worker_job_id)
        )

        return {
            "status": receipt.status,
            "artifacts": [a.model_dump() for a in receipt.artifacts],
            "errors": receipt.errors,
            "completed_at": receipt.completed_at,
        }

    def advance_from_receipt(
        self,
        vpms_job_id: str,
        worker_job_id: str,
        worker_id: str,
        receipt_status: str,
        artifacts: list[dict],
        errors: list[str],
    ):
        """
        Process a receipt and advance the job state accordingly.
        """
        # Process artifacts
        from vpms.db.repositories.artifact_repository import ArtifactRepository

        artifact_repo = ArtifactRepository(self._session)
        for art in artifacts:
            artifact_repo.create(
                job_id=vpms_job_id,
                worker_job_id=worker_job_id,
                artifact_type=art.get("type", "unknown"),
                name=art.get("name", "unknown"),
                url=art.get("url"),
                file_path=art.get("file_path"),
                file_size_bytes=art.get("size_bytes"),
                mime_type=art.get("mime_type"),
                duration_seconds=art.get("duration_seconds"),
                width=art.get("width"),
                height=art.get("height"),
                metadata=art.get("metadata", {}),
            )

        # Update worker job status
        wj = self._session.query(WorkerJob).filter(
            WorkerJob.id == worker_job_id
        ).scalar_one_or_none()
        if wj:
            wj.status = receipt_status
            if errors:
                wj.errors = errors
            self._session.flush()

        # Advance state machine
        if receipt_status == "COMPLETED":
            # Determine next state based on current state and worker
            job = self._job_repo.find_by_id(vpms_job_id)
            current = JobState(job.status)

            if current == JobState.RESEARCHING:
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.RESEARCH_READY,
                    EventType.WORKER_RECEIPT_RECEIVED,
                    worker=worker_id,
                    metadata={"worker_job_id": worker_job_id},
                )
            elif current == JobState.ASSET_GENERATION:
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.PROVIDER_CONFIRMED,
                    EventType.WORKER_RECEIPT_RECEIVED,
                    worker=worker_id,
                    metadata={"worker_job_id": worker_job_id},
                )
            elif current == JobState.RENDERING:
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.OUTPUT_VERIFICATION,
                    EventType.WORKER_RECEIPT_RECEIVED,
                    worker=worker_id,
                    metadata={"worker_job_id": worker_job_id},
                )

        elif receipt_status == "FAILED":
            if self._is_transient(errors):
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.RETRYABLE_FAILURE,
                    EventType.JOB_FAILED,
                    worker=worker_id,
                    metadata={"worker_job_id": worker_job_id, "errors": errors},
                )
            else:
                self._job_manager.transition_state(
                    vpms_job_id,
                    JobState.FAILED,
                    EventType.JOB_FAILED,
                    worker=worker_id,
                    metadata={"worker_job_id": worker_job_id, "errors": errors},
                )

    def _is_transient(self, errors: list[str]) -> bool:
        """Check if errors are retryable."""
        transient = ["timeout", "temporary", "unavailable", "rate limit", "connection"]
        return any(kw in " ".join(errors).lower() for kw in transient)

    # ─── Full Golden Path Orchestration ─────────────────────────────────────────

    def run_golden_path(
        self,
        vpms_job_id: str,
        content: dict,
        production: dict,
        requested_outputs: list[str],
        budget: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Execute the full Golden Path for a two-person podcast episode.

        This is a synchronous convenience method that dispatches all
        workers in sequence. For production use, call individual
        dispatch methods and use the polling API for status updates.

        Returns a summary of dispatched workers.
        """
        metadata = metadata or {}

        # ── Step 1: Chronos — Research + Script ──────────────────────────────
        chronos_wj = self.dispatch_research_and_script(
            vpms_job_id=vpms_job_id,
            content=content,
            metadata={
                "niche": content.get("niche"),
                "speakers": production.get("speakers", []),
                "budget": budget,
                **metadata,
            },
        )

        return {
            "vpms_job_id": vpms_job_id,
            "chronos_worker_job_id": chronos_wj.id,
            "current_state": JobState.RESEARCHING.value,
            "message": "Chronos dispatched for research and script. "
                       "Awaiting script approval before Avatar Webinar render.",
        }

    def run_avatar_render(
        self,
        vpms_job_id: str,
        script: dict,
        speakers: list[dict],
        output: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Dispatch Avatar Webinar render after script approval.
        """
        aw_wj = self.dispatch_avatar_render(
            vpms_job_id=vpms_job_id,
            script=script,
            speakers=speakers,
            output=output,
            metadata=metadata,
        )

        return {
            "vpms_job_id": vpms_job_id,
            "avatar_webinar_worker_job_id": aw_wj.id,
            "current_state": JobState.ASSET_GENERATION.value,
            "message": "Avatar Webinar dispatched for rendering.",
        }
