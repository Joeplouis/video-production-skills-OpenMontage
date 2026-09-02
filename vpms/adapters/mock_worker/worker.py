"""
Mock Test Worker — VPMS Phase 1
Simulates a production worker for end-to-end testing.
Supports: success, transient failure, permanent failure, timeout, duplicate callback, restart.
"""

import asyncio
import random
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from pydantic import BaseModel
import uvicorn


# ─── Simulated Failure Modes ────────────────────────────────────────────────────


class FailureMode(str, Enum):
    SUCCESS = "success"
    TRANSIENT_FAILURE = "transient_failure"  # retry once
    PERMANENT_FAILURE = "permanent_failure"
    TIMEOUT = "timeout"
    DUPLICATE_CALLBACK = "duplicate_callback"  # sends receipt twice
    RESTART_DURING_WORK = "restart_during_work"


# ─── Receipt & Artifact Models ─────────────────────────────────────────────────


class MockReceipt(BaseModel):
    vpms_job_id: str
    worker: str = "mock-worker"
    worker_job_id: str
    status: str  # PENDING, PROVIDER_CONFIRMED, COMPLETED, FAILED
    provider: str = "mock-provider"
    model: str = "mock-model-v1"
    artifacts: list[dict] = []
    estimated_cost: float = 0.05
    actual_cost: float = 0.05
    started_at: str
    completed_at: Optional[str] = None
    errors: list[str] = []


# ─── Mock Worker State ────────────────────────────────────────────────────────


class MockWorkerState:
    """
    In-memory state for the mock worker.
    Simulates: in-progress jobs, receipts, artifacts.
    """

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.receipts: dict[str, MockReceipt] = {}
        self.restart_count = 0

    def start_job(
        self,
        vpms_job_id: str,
        failure_mode: str = "success",
        work_duration: float = 2.0,
    ) -> MockReceipt:
        """Simulate starting work on a job."""
        worker_job_id = f"mwk_{uuid.uuid4().hex[:12]}"

        receipt = MockReceipt(
            vpms_job_id=vpms_job_id,
            worker_job_id=worker_job_id,
            status="PROVIDER_CONFIRMED",
            started_at=datetime.now(timezone.utc).isoformat(),
            artifacts=[],
        )

        job_state = {
            "worker_job_id": worker_job_id,
            "failure_mode": failure_mode,
            "work_duration": work_duration,
            "status": "RUNNING",
            "receipt": receipt,
            "call_count": 0,
        }

        self.jobs[vpms_job_id] = job_state
        self.receipts[worker_job_id] = receipt

        return receipt

    def complete_job(self, vpms_job_id: str) -> MockReceipt:
        """Simulate completing work."""
        job = self.jobs.get(vpms_job_id)
        if not job:
            raise ValueError(f"No job found: {vpms_job_id}")

        receipt = job["receipt"]
        failure_mode = job["failure_mode"]

        if failure_mode == "success":
            receipt.status = "COMPLETED"
            receipt.completed_at = datetime.now(timezone.utc).isoformat()
            receipt.actual_cost = receipt.estimated_cost
            receipt.artifacts = [
                {
                    "type": "video",
                    "name": f"mock_video_{vpms_job_id}.mp4",
                    "url": f"https://storage.example.com/vpms/{vpms_job_id}/output.mp4",
                    "size_bytes": random.randint(1_000_000, 10_000_000),
                    "duration_seconds": 120.0,
                    "width": 1920,
                    "height": 1080,
                }
            ]

        elif failure_mode == "transient_failure":
            if job["call_count"] == 0:
                job["call_count"] += 1
                receipt.status = "PROVIDER_CONFIRMED"
                receipt.errors = ["Transient error: provider temporarily unavailable"]
                # On retry, it succeeds
                return self.complete_job(vpms_job_id)
            else:
                receipt.status = "COMPLETED"
                receipt.completed_at = datetime.now(timezone.utc).isoformat()

        elif failure_mode == "permanent_failure":
            receipt.status = "FAILED"
            receipt.completed_at = datetime.now(timezone.utc).isoformat()
            receipt.errors = ["Permanent error: model not available"]

        elif failure_mode == "timeout":
            receipt.status = "FAILED"
            receipt.completed_at = datetime.now(timezone.utc).isoformat()
            receipt.errors = ["Error: job timed out after 300 seconds"]

        elif failure_mode == "duplicate_callback":
            # First call: success
            receipt.status = "COMPLETED"
            receipt.completed_at = datetime.now(timezone.utc).isoformat()
            # Duplicate is handled by VPMS idempotency

        job["status"] = "COMPLETED" if receipt.status == "COMPLETED" else "FAILED"
        self.receipts[job["worker_job_id"]] = receipt

        return receipt

    def get_receipt(self, worker_job_id: str) -> Optional[MockReceipt]:
        return self.receipts.get(worker_job_id)

    def is_job_complete(self, vpms_job_id: str) -> bool:
        job = self.jobs.get(vpms_job_id)
        return job is not None and job["status"] == "COMPLETED"

    def simulate_restart(self):
        """Simulate a worker restart — state is preserved in VPMS, not here."""
        self.restart_count += 1


# ─── FastAPI App ───────────────────────────────────────────────────────────────


app = FastAPI(title="VPMS Mock Worker", version="1.0.0")
state = MockWorkerState()


@app.get("/health")
def health():
    return {"status": "healthy", "worker": "mock-worker"}


@app.get("/capabilities")
def capabilities():
    return {
        "worker_id": "mock-worker",
        "capabilities": [
            {
                "capability": "mock_video_render",
                "code_present": True,
                "healthy": True,
            }
        ],
    }


class JobRequest(BaseModel):
    vpms_job_id: str
    failure_mode: str = "success"
    work_duration: float = 2.0


@app.post("/jobs")
def create_job(request: JobRequest):
    """Simulate job creation on worker side."""
    receipt = state.start_job(
        vpms_job_id=request.vpms_job_id,
        failure_mode=request.failure_mode,
        work_duration=request.work_duration,
    )
    return receipt


@app.get("/jobs/{worker_job_id}")
def get_job(worker_job_id: str):
    """Get job status from worker perspective."""
    receipt = state.get_receipt(worker_job_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Job not found")
    return receipt


@app.get("/jobs/{worker_job_id}/artifacts")
def get_artifacts(worker_job_id: str):
    """Get artifacts from worker."""
    receipt = state.get_receipt(worker_job_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"artifacts": receipt.artifacts}


@app.post("/jobs/{worker_job_id}/complete")
def complete_job(worker_job_id: str):
    """Manually trigger job completion (for testing)."""
    # Find job by worker_job_id
    for vpms_job_id, job_data in state.jobs.items():
        if job_data["worker_job_id"] == worker_job_id:
            receipt = state.complete_job(vpms_job_id)
            return receipt
    raise HTTPException(status_code=404, detail="Job not found")


@app.post("/jobs/{worker_job_id}/cancel")
def cancel_job(worker_job_id: str):
    """Cancel a worker job."""
    for vpms_job_id, job_data in state.jobs.items():
        if job_data["worker_job_id"] == worker_job_id:
            job_data["status"] = "CANCELLED"
            job_data["receipt"].status = "FAILED"
            job_data["receipt"].errors = ["Cancelled by VPMS"]
            return {"status": "cancelled"}
    raise HTTPException(status_code=404, detail="Job not found")


# ─── Simulated Auto-Complete ───────────────────────────────────────────────────


@app.post("/jobs/{worker_job_id}/simulate-work")
async def simulate_work(worker_job_id: str, work_duration: float = Query(2.0)):
    """
    Simulate async work and auto-complete.
    This endpoint is for testing: it waits, then completes the job.
    """
    for vpms_job_id, job_data in list(state.jobs.items()):
        if job_data["worker_job_id"] == worker_job_id:
            await asyncio.sleep(work_duration)
            receipt = state.complete_job(vpms_job_id)
            return receipt
    raise HTTPException(status_code=404, detail="Job not found")


# ─── Restart Simulation ────────────────────────────────────────────────────────


@app.post("/simulate-restart")
def simulate_restart():
    """Simulate worker restart."""
    state.simulate_restart()
    return {
        "status": "restarted",
        "restart_count": state.restart_count,
        "jobs_preserved": len(state.jobs),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8091)
