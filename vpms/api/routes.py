"""
VPMS API Router — All 11 Phase 1 endpoints.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from vpms import __version__
from vpms.core.state_machine import JobState
from vpms.core.event_ledger import EventType
from vpms.core.job_manager import JobManager
from vpms.db.session import get_db
from vpms.db.repositories.worker_repository import WorkerRepository, CapabilityRepository
from vpms.api.schemas import (
    ContentJobRequest,
    VideoJobRequest,
    JobResponse,
    JobCreateResponse,
    JobStatusResponse,
    EventResponse,
    ArtifactResponse,
    ArtifactListResponse,
    ApprovalRequest,
    ApprovalResponse,
    CancelRequest,
    CancelResponse,
    WorkerResponse,
    WorkerListResponse,
    CapabilityResponse,
    CapabilityListResponse,
    HealthResponse,
)

router = APIRouter(prefix="/api/v1", tags=["VPMS"])


# ─── Internal Auth Helper ─────────────────────────────────────────────────────


def require_source_app(
    x_source_app: str = Header(..., description="Source application ID"),
    db: Session = Depends(get_db),
) -> str:
    """Validate source app is registered and active."""
    from vpms.db.models import SourceApp
    from sqlalchemy import select

    stmt = select(SourceApp).where(
        SourceApp.app_id == x_source_app, SourceApp.is_active == True
    )
    app = db.execute(stmt).scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=401, detail="Unknown or inactive source application")
    return x_source_app


# ─── Health ──────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="healthy",
        version=__version__,
        database=db_status,
        timestamp=datetime.now(timezone.utc),
    )


# ─── Content Jobs ─────────────────────────────────────────────────────────────


@router.post(
    "/content/jobs",
    response_model=JobCreateResponse,
    status_code=201,
    summary="Create a content job",
)
def create_content_job(
    request: ContentJobRequest,
    db: Session = Depends(get_db),
):
    """Create a new content job (triggers Chronos workflow)."""
    manager = JobManager(db)

    job, created = manager.create_content_job(
        source_app=request.source_app,
        request_type=request.request_type,
        content=request.content,
        production=request.production,
        requested_outputs=request.requested_outputs,
        budget=request.budget,
        external_reference_id=request.external_reference_id,
        idempotency_key=request.idempotency_key,
        created_by=request.created_by,
        priority=request.priority,
    )

    if not created:
        # Idempotent — return existing job
        return JobCreateResponse(
            job_id=job.id,
            status=job.status,
            created_at=job.created_at,
        )

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


# ─── Video Jobs ───────────────────────────────────────────────────────────────


@router.post(
    "/video/jobs",
    response_model=JobCreateResponse,
    status_code=201,
    summary="Create a video job",
)
def create_video_job(
    request: VideoJobRequest,
    db: Session = Depends(get_db),
):
    """Create a new video job (already has content/script)."""
    manager = JobManager(db)

    job, created = manager.create_video_job(
        source_app=request.source_app,
        request_type=request.request_type,
        content=request.content,
        production=request.production,
        requested_outputs=request.requested_outputs,
        budget=request.budget,
        external_reference_id=request.external_reference_id,
        idempotency_key=request.idempotency_key,
        created_by=request.created_by,
        priority=request.priority,
    )

    if not created:
        return JobCreateResponse(
            job_id=job.id,
            status=job.status,
            created_at=job.created_at,
        )

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


# ─── Job Detail ───────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="Get job details")
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get full job details."""
    manager = JobManager(db)
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.get(
    "/jobs/{job_id}/status", response_model=JobStatusResponse, summary="Get job status"
)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get lightweight job status."""
    manager = JobManager(db)
    status = manager.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**status)


@router.get(
    "/jobs/{job_id}/events", response_model=list[EventResponse], summary="Get job events"
)
def get_job_events(job_id: str, db: Session = Depends(get_db)):
    """Get event history for a job."""
    manager = JobManager(db)
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    events = manager.get_events(job_id)
    return [EventResponse.model_validate(e) for e in events]


@router.get(
    "/jobs/{job_id}/artifacts",
    response_model=ArtifactListResponse,
    summary="Get job artifacts",
)
def get_job_artifacts(job_id: str, db: Session = Depends(get_db)):
    """Get all artifacts for a job."""
    manager = JobManager(db)
    job = manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    artifacts = manager.get_artifacts(job_id)
    return ArtifactListResponse(
        job_id=job_id,
        artifacts=[ArtifactResponse.model_validate(a) for a in artifacts],
        total=len(artifacts),
    )


# ─── Job Actions ──────────────────────────────────────────────────────────────


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse, summary="Cancel job")
def cancel_job(
    job_id: str,
    request: CancelRequest = None,
    db: Session = Depends(get_db),
):
    """Cancel a job."""
    manager = JobManager(db)
    try:
        job = manager.cancel_job(job_id, reason=request.reason if request else None)
        return CancelResponse(
            job_id=job.id,
            status=job.status,
            message="Job cancelled successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/jobs/{job_id}/approve", response_model=ApprovalResponse, summary="Approve job at gate"
)
def approve_job(
    job_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
):
    """Approve a job at a human approval gate."""
    manager = JobManager(db)
    try:
        # Determine approval type from current state
        job = manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status == JobState.WAITING_FOR_PRODUCTION_APPROVAL.value:
            approval_type = "PRODUCTION"
        elif job.status == JobState.WAITING_FOR_FINAL_APPROVAL.value:
            approval_type = "FINAL_VIDEO"
        elif job.status == JobState.SCRIPT_APPROVED.value:
            approval_type = "PRODUCTION"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not at an approval gate (status: {job.status})",
            )

        job, approval = manager.approve_job(
            job_id=job_id,
            approval_type=approval_type,
            approved_by=request.approved_by,
            notes=request.notes,
        )

        return ApprovalResponse.model_validate(approval)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/jobs/{job_id}/reject", response_model=ApprovalResponse, summary="Reject job"
)
def reject_job(
    job_id: str,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
):
    """Reject a job."""
    manager = JobManager(db)
    try:
        job, approval = manager.reject_job(
            job_id=job_id,
            approved_by=request.approved_by,
            notes=request.notes,
        )
        return ApprovalResponse.model_validate(approval)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Workers ─────────────────────────────────────────────────────────────────


@router.get("/workers", response_model=WorkerListResponse, summary="List workers")
def list_workers(
    status: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List registered workers."""
    repo = WorkerRepository(db)
    workers = repo.list_workers(status=status, visibility=visibility)
    return WorkerListResponse(
        workers=[WorkerResponse.model_validate(w) for w in workers],
        total=len(workers),
    )


# ─── Capabilities ────────────────────────────────────────────────────────────


@router.get(
    "/capabilities", response_model=CapabilityListResponse, summary="List capabilities"
)
def list_capabilities(
    capability: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List all worker capabilities."""
    repo = CapabilityRepository(db)
    caps = repo.list_all(capability=capability, visibility=visibility)
    return CapabilityListResponse(
        capabilities=[CapabilityResponse.model_validate(c) for c in caps],
        total=len(caps),
    )


# ─── Root Health ─────────────────────────────────────────────────────────────


health_router = APIRouter(tags=["Health"])


@health_router.get("/health", response_model=HealthResponse)
def root_health(db: Session = Depends(get_db)):
    """Root health check."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="healthy",
        version=__version__,
        database=db_status,
        timestamp=datetime.now(timezone.utc),
    )
