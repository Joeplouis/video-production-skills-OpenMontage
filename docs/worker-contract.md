# VPMS Worker Contract

## Overview

VPMS manages production workers via a **canonical adapter interface**. Workers do not need to implement VPMS endpoints directly — VPMS provides adapters that translate between VPMS's contract and each worker's native API.

## Canonical Worker Interface (vpms/adapters/base.py)

Every worker adapter must implement:

```python
class BaseWorkerAdapter(ABC):
    @property
    @abstractmethod
    def worker_id(self) -> str: ...

    @property
    @abstractmethod
    def base_url(self) -> str: ...

    @abstractmethod
    async def health_check(self) -> WorkerHealth: ...

    @abstractmethod
    async def get_capabilities(self) -> WorkerCapabilities: ...

    @abstractmethod
    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt: ...

    @abstractmethod
    async def get_status(self, worker_job_id: str) -> WorkerReceipt: ...

    @abstractmethod
    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]: ...

    @abstractmethod
    async def cancel(self, worker_job_id: str) -> bool: ...
```

## HTTP Contract (for reference adapters)

Workers that expose an HTTP API should implement:

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/capabilities` | List capabilities |
| POST | `/jobs` | Create job |
| GET | `/jobs/:worker_job_id` | Get job status |
| GET | `/jobs/:worker_job_id/artifacts` | Get artifacts |
| POST | `/jobs/:worker_job_id/cancel` | Cancel job |

### GET /health

Returns:

```json
{
  "status": "healthy",
  "worker_id": "heygen",
  "timestamp": "2025-01-15T10:00:00Z"
}
```

Return HTTP 503 if unhealthy.

### GET /capabilities

Returns:

```json
{
  "worker_id": "heygen",
  "capabilities": [
    {
      "capability": "avatar-video",
      "version": "2.1",
      "supported_formats": ["mp4", "webm"]
    }
  ]
}
```

### POST /jobs

VPMS sends a `WorkerJobRequest`:

```json
{
  "vpms_job_id": "vpms_01JABC123",
  "worker": "avatar-webinar",
  "production_type": "podcast_hybrid",
  "script": { ... },
  "scene_plan": [ ... ],
  "speakers": [ ... ],
  "output": {
    "aspect_ratio": "16:9",
    "resolution": "1080p",
    "duration_seconds": 1200
  },
  "requested_outputs": ["long_video", "shorts", "thumbnail"],
  "budget": { "maximum_usd": 5 }
}
```

Worker must return a `WorkerReceipt` with status `PENDING` and a `worker_job_id`.

### GET /jobs/:worker_job_id

Returns current worker-side status as a `WorkerReceipt`.

### GET /jobs/:worker_job_id/artifacts

Returns list of `WorkerArtifact` objects for the job.

### POST /jobs/:worker_job_id/cancel

Cancels the worker-side job. Returns `{"status": "cancelled"}`.

## Worker Receipt Contract

Every meaningful worker operation must produce a `WorkerReceipt`:

```python
class WorkerReceipt(BaseModel):
    vpms_job_id: str
    worker: str
    worker_job_id: str
    status: str  # PENDING, PROVIDER_CONFIRMED, COMPLETED, FAILED
    provider: Optional[str] = None
    model: Optional[str] = None
    artifacts: list[dict] = []
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    started_at: str
    completed_at: Optional[str] = None
    errors: list[str] = []
```

**Critical**: Workers must NOT go directly from `PENDING` to `COMPLETED`. The correct path:

1. Accept job → status: `PENDING` or `PROVIDER_CONFIRMED`
2. Complete work → status: `COMPLETED` (with artifacts)

## Artifact Contract

```python
class WorkerArtifact(BaseModel):
    type: str          # "video", "audio", "image", "metadata"
    name: str          # human-readable name
    url: Optional[str]
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    mime_type: Optional[str]
    duration_seconds: Optional[float]
    width: Optional[int]
    height: Optional[int]
    checksum: Optional[str]
    metadata: dict = {}
```

## Phase 1 Adapter: Mock Worker

`vpms/adapters/mock_worker/worker.py` is the Phase 1 test worker. It implements all 6 endpoints and supports simulated failure modes:

- `success` — normal completion
- `transient_failure` — retry succeeds on second attempt
- `permanent_failure` — always fails
- `timeout` — simulates timeout error
- `duplicate_callback` — sends receipt twice (VPMS handles idempotency)
- `restart_during_work` — simulates restart (VPMS state preserved)

Run with: `python -m vpms.adapters.mock_worker.worker` (port 8091)

## Phase 2 Adapters (not wired in Phase 1)

- `vpms/adapters/chronos/` — Chronos content showrunner
- `vpms/adapters/avatar_webinar/` — Avatar Webinar production
- `vpms/adapters/vmf/` — Video Media Factory

These directories contain `__init__.py` stubs for Phase 2 wiring.
