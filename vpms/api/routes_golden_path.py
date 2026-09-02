"""
VPMS Phase 2 API Routes — Golden Path, Worker Receipts, QA.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vpms.core.state_machine import JobState
from vpms.core.event_ledger import EventType
from vpms.core.job_manager import JobManager
from vpms.core.production_director import ProductionDirector
from vpms.db.session import get_db
from vpms.db.models import SourceApp, WorkerJob, QAReport, Job
from vpms.db.repositories.worker_repository import WorkerRepository
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["VPMS Phase 2"])


# ─── Auth ──────────────────────────────────────────────────────────────────────


def require_source_app(
    x_source_app: str = Header(..., description="Source application ID"),
    db: Session = Depends(get_db),
) -> str:
    stmt = select(SourceApp).where(
        SourceApp.app_id == x_source_app, SourceApp.is_active == True
    )
    app = db.execute(stmt).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=401, detail="Unknown or inactive source application")
    return x_source_app


# ─── Golden Path: Start Episode Production ─────────────────────────────────────


class GoldenPathRequest(BaseModel):  # noqa: F821 — imported below
    source_app: str
    topic: str
    audience: Optional[str] = None
    goal: Optional[str] = None
    duration_minutes: Optional[int] = 10
    speakers: list[dict] = []  # [{name, voice_id, avatar_image_url}]
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    requested_outputs: list[str] = ["long_video", "shorts", "thumbnail"]
    budget: Optional[dict] = None
    idempotency_key: Optional[str] = None
    created_by: Optional[str] = None
    metadata: Optional[dict] = None


class GoldenPathResponse(BaseModel):  # noqa: F821
    job_id: str
    status: str
    chronos_worker_job_id: str
    current_state: str
    message: str


@router.post(
    "/golden-path",
    response_model=GoldenPathResponse,  # type: ignore[name-defined]
    status_code=202,
    summary="Start a two-person podcast Golden Path",
)
def start_golden_path(
    request: GoldenPathRequest,  # type: ignore[name-defined]
    db: Session = Depends(get_db),
):
    """
    Start the Golden Path for a two-person podcast episode.

    Creates a VPMS content job and immediately dispatches it to Chronos
    for research and script generation.

    Flow:
    1. VPMS creates content job (QUEUED)
    2. Dispatches to Chronos (RESEARCHING)
    3. Returns job_id for polling / approval callbacks

    After Chronos completes, POST to /jobs/{job_id}/script-ready to continue.
    """
    manager = JobManager(db)
    director = ProductionDirector(db)

    # Build content payload
    content = {
        "topic": request.topic,
        "audience": request.audience,
        "goal": request.goal,
        "duration_minutes": request.duration_minutes,
    }

    # Create the VPMS job
    job, created = manager.create_content_job(
        source_app=request.source_app,
        request_type="podcast_episode",
        content=content,
        production={
            "mode": "podcast_hybrid",
            "speakers": len(request.speakers),
            "aspect_ratio": request.aspect_ratio,
            "resolution": request.resolution,
            "speakers": request.speakers,
        },
        requested_outputs=request.requested_outputs,
        budget=request.budget,
        idempotency_key=request.idempotency_key,
        created_by=request.created_by,
    )

    if not created:
        raise HTTPException(
            status_code=409,
            detail=f"Job already exists with idempotency_key: {request.idempotency_key}",
        )

    # Dispatch to Chronos via Production Director
    try:
        result = director.run_golden_path(
            vpms_job_id=job.id,
            content=content,
            production={
                "mode": "podcast_hybrid",
                "speakers": request.speakers,
                "aspect_ratio": request.aspect_ratio,
                "resolution": request.resolution,
            },
            requested_outputs=request.requested_outputs,
            budget=request.budget,
            metadata={
                "duration_minutes": request.duration_minutes,
                "goal": request.goal,
                **(request.metadata or {}),
            },
        )
    except Exception as e:
        # If dispatch fails, transition job to failed
        manager.transition_state(
            job.id,
            JobState.FAILED,
            EventType.JOB_FAILED,
            metadata={"error": str(e)},
        )
        raise HTTPException(status_code=502, detail=f"Worker dispatch failed: {e}")

    return GoldenPathResponse(
        job_id=job.id,
        status=job.status,
        chronos_worker_job_id=result["chronos_worker_job_id"],
        current_state=result["current_state"],
        message=result["message"],
    )


# ─── Worker Receipt Callback ───────────────────────────────────────────────────
# Workers call this endpoint when they complete or need to report status.


class WorkerReceiptCallback(BaseModel):  # noqa: F821
    worker_job_id: str
    status: str  # PENDING | PROVIDER_CONFIRMED | COMPLETED | FAILED
    provider: Optional[str] = None
    model: Optional[str] = None
    artifacts: list[dict] = []
    actual_cost: float = 0.0
    errors: list[str] = []


class ReceiptCallbackResponse(BaseModel):  # noqa: F821
    received: bool
    job_id: str
    new_state: Optional[str] = None


@router.post(
    "/workers/{worker_id}/receipt",
    response_model=ReceiptCallbackResponse,  # type: ignore[name-defined]
    summary="Worker receipt callback",
)
def worker_receipt_callback(
    worker_id: str,
    receipt: WorkerReceiptCallback,  # type: ignore[name-defined]
    db: Session = Depends(get_db),
):
    """
    Workers call this endpoint to report job completion or status updates.

    VPMS processes the receipt:
    - Creates artifacts in the DB
    - Advances the job state
    - Returns the new state
    """
    # Find the WorkerJob by our internal ID or by the worker's own ID
    wj = db.query(WorkerJob).filter(
        WorkerJob.id == receipt.worker_job_id
    ).scalar_one_or_none()

    if not wj:
        # Try by worker_job_id field (some workers use their own IDs)
        wj = db.query(WorkerJob).filter(
            WorkerJob.worker_id == worker_id,
            WorkerJob.worker_job_id == receipt.worker_job_id,
        ).scalar_one_or_none()

    if not wj:
        raise HTTPException(status_code=404, detail="Worker job not found")

    director = ProductionDirector(db)

    try:
        director.advance_from_receipt(
            vpms_job_id=wj.vpms_job_id,
            worker_job_id=wj.id,
            worker_id=worker_id,
            receipt_status=receipt.status,
            artifacts=receipt.artifacts,
            errors=receipt.errors,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process receipt: {e}")

    job = db.query(Job).filter(Job.id == wj.vpms_job_id).scalar_one_or_none()  # type: ignore[name-defined]

    return ReceiptCallbackResponse(
        received=True,
        job_id=wj.vpms_job_id,
        new_state=job.status if job else None,
    )


# ─── Job Worker Jobs ──────────────────────────────────────────────────────────


class WorkerJobResponse(BaseModel):  # noqa: F821
    id: str
    vpms_job_id: str
    worker_id: str
    worker_job_id: Optional[str]
    status: str
    provider: Optional[str]
    model: Optional[str]
    actual_cost: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    errors: list[str]


@router.get(
    "/jobs/{job_id}/worker-jobs",
    summary="Get all worker jobs for a VPMS job",
)
def get_worker_jobs(job_id: str, db: Session = Depends(get_db)):
    """Return all WorkerJob records for a given VPMS job."""
    wjs = db.query(WorkerJob).filter(WorkerJob.vpms_job_id == job_id).all()
    return {
        "job_id": job_id,
        "worker_jobs": [
            {
                "id": wj.id,
                "worker_id": wj.worker_id,
                "worker_job_id": wj.worker_job_id,
                "status": wj.status,
                "provider": wj.provider,
                "model": wj.model,
                "actual_cost": float(wj.actual_cost) if wj.actual_cost else None,
                "started_at": wj.started_at,
                "completed_at": wj.completed_at,
                "errors": wj.errors or [],
            }
            for wj in wjs
        ],
        "total": len(wjs),
    }


# ─── QA Results ───────────────────────────────────────────────────────────────


class QASubmitRequest(BaseModel):  # noqa: F821
    qa_type: str  # TECHNICAL | CREATIVE
    decision: str  # PASS | FAIL | NEEDS_REVIEW
    scores: dict = {}
    issues: list[str] = []
    required_fixes: list[str] = []
    notes: Optional[str] = None


class QASubmitResponse(BaseModel):  # noqa: F821
    qa_report_id: str
    job_id: str
    qa_type: str
    decision: str
    new_state: str


@router.post(
    "/jobs/{job_id}/qa",
    response_model=QASubmitResponse,  # type: ignore[name-defined]
    summary="Submit QA report for a job",
)
def submit_qa_report(
    job_id: str,
    request: QASubmitRequest,  # type: ignore[name-defined]
    db: Session = Depends(get_db),
):
    """
    Submit a QA report for a job and advance the state machine.

    TECHNICAL_QA PASS → CREATIVE_QA
    CREATIVE_QA PASS → WAITING_FOR_FINAL_APPROVAL
    CREATIVE_QA FAIL → RETRYABLE_FAILURE (needs fixes)
    """
    manager = JobManager(db)

    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Create QA report
    qa_report = QAReport(
        job_id=job_id,
        qa_type=request.qa_type.upper(),
        scores=request.scores,
        issues=request.issues,
        required_fixes=request.required_fixes,
        decision=request.decision.upper(),
    )
    db.add(qa_report)
    db.flush()

    # Determine next state
    current = JobState(job.status)
    qa_type_upper = request.qa_type.upper()

    if qa_type_upper == "TECHNICAL":
        if request.decision.upper() == "PASS":
            next_state = JobState.CREATIVE_QA
            event_type = EventType.QA_PASSED
        else:
            next_state = JobState.RETRYABLE_FAILURE
            event_type = EventType.QA_FAILED
    elif qa_type_upper == "CREATIVE":
        if request.decision.upper() == "PASS":
            next_state = JobState.WAITING_FOR_FINAL_APPROVAL
            event_type = EventType.QA_PASSED
        else:
            next_state = JobState.RETRYABLE_FAILURE
            event_type = EventType.QA_FAILED
    else:
        raise HTTPException(status_code=400, detail=f"Unknown QA type: {qa_type_upper}")

    manager.transition_state(
        job_id,
        next_state,
        event_type,
        metadata={
            "qa_report_id": qa_report.id,
            "decision": request.decision.upper(),
            "notes": request.notes,
        },
    )

    return QASubmitResponse(
        qa_report_id=qa_report.id,
        job_id=job_id,
        qa_type=qa_type_upper,
        decision=request.decision.upper(),
        new_state=next_state.value,
    )


# ─── Health Check All Workers ─────────────────────────────────────────────────


class WorkerHealthResponse(BaseModel):  # noqa: F821
    worker_id: str
    status: str
    timestamp: str
    adapter_healthy: bool


@router.get(
    "/workers/health",
    summary="Health check all registered workers",
)
def health_check_all_workers(db: Session = Depends(get_db)):
    """
    Run health checks against all registered workers.
    Returns health status for each worker.
    """
    import asyncio
    from vpms.adapters.chronos import ChronosWorkerAdapter
    from vpms.adapters.avatar_webinar import AvatarWebinarWorkerAdapter
    from vpms.adapters.vmf import VMFWorkerAdapter

    results = {}

    async def check_all():
        adapters = {
            "chronos": ChronosWorkerAdapter(),
            "avatar-webinar": AvatarWebinarWorkerAdapter(),
            "vmf": VMFWorkerAdapter(),
        }
        for wid, adapter in adapters.items():
            try:
                health = await adapter.health_check()
                results[wid] = {
                    "status": health.status,
                    "timestamp": health.timestamp,
                    "adapter_healthy": health.status in ("healthy", "ok"),
                }
            except Exception as e:
                results[wid] = {
                    "status": "error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "adapter_healthy": False,
                    "error": str(e),
                }

    asyncio.get_event_loop().run_until_complete(check_all())

    # Update DB health status for reachable workers
    for wid, info in results.items():
        repo = WorkerRepository(db)
        db_status = "HEALTHY" if info["adapter_healthy"] else "UNHEALTHY"
        repo.update_health(wid, db_status)

    return {"workers": results, "timestamp": datetime.now(timezone.utc).isoformat()}


# ─── Script Ready — Continue Golden Path After Chronos ─────────────────────────


class ScriptReadyRequest(BaseModel):  # noqa: F821
    """Called after Chronos completes research + script. Triggers Avatar Webinar render."""
    script: dict  # {script_text, segments, metadata}
    speakers: list[dict]  # [{name, voice_id, avatar_image_url}]
    approved_by: Optional[str] = None
    notes: Optional[str] = None


class ScriptReadyResponse(BaseModel):  # noqa: F821
    job_id: str
    avatar_webinar_worker_job_id: str
    current_state: str
    message: str


@router.post(
    "/jobs/{job_id}/script-ready",
    response_model=ScriptReadyResponse,  # type: ignore[name-defined]
    summary="Continue Golden Path: Chronos script complete, proceed to Avatar Webinar",
)
def script_ready(
    job_id: str,
    request: ScriptReadyRequest,  # type: ignore[name-defined]
    db: Session = Depends(get_db),
):
    """
    Called after Chronos completes and the script has been approved.
    Records the approval and dispatches to Avatar Webinar for rendering.
    """
    manager = JobManager(db)
    director = ProductionDirector(db)

    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    current = JobState(job.status)
    if current != JobState.SCRIPT_APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Job must be in SCRIPT_APPROVED state. Current: {current.value}",
        )

    # Record approval
    from vpms.db.repositories.artifact_repository import ApprovalRepository
    approval_repo = ApprovalRepository(db)
    approval_repo.create(
        job_id=job_id,
        approval_type="SCRIPT",
        decision="APPROVED",
        approved_by=request.approved_by,
        notes=request.notes,
    )

    # Transition to PRODUCTION_APPROVED
    manager.transition_state(
        job_id,
        JobState.PRODUCTION_APPROVED,
        EventType.APPROVAL_GRANTED,
        metadata={"approval_type": "SCRIPT", "approved_by": request.approved_by},
    )

    # Dispatch to Avatar Webinar
    try:
        result = director.run_avatar_render(
            vpms_job_id=job_id,
            script=request.script,
            speakers=request.speakers,
            metadata={"approved_by": request.approved_by},
        )
    except Exception as e:
        manager.transition_state(
            job_id,
            JobState.FAILED,
            EventType.JOB_FAILED,
            metadata={"error": str(e)},
        )
        raise HTTPException(status_code=502, detail=f"Avatar Webinar dispatch failed: {e}")

    return ScriptReadyResponse(
        job_id=job_id,
        avatar_webinar_worker_job_id=result["avatar_webinar_worker_job_id"],
        current_state=result["current_state"],
        message=result["message"],
    )

