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

## Phase 2 Adapters (wired, tested, in production use)

### `vpms/adapters/chronos/worker.py` — Chronos Content Showrunner

Chronos is a cron-driven autonomous showrunner with no HTTP API. VPMS communicates via file-based queue.

| Method | Implementation |
|--------|--------------|
| `health_check()` | Checks series_state.json exists + run_chronos.sh is executable |
| `get_capabilities()` | Returns static list: research, script_generation, fish_audio_tts, shotstack_render, postiz_publish |
| `dispatch()` | Writes VPMS job to `vpms_queue.json`, returns queue index as worker_job_id |
| `get_status()` | Reads `series_state.json` — maps episodes_history entries to VPMS receipt status |
| `get_artifacts()` | Reads completed episode data (video URL, thumbnail, YouTube metadata) |
| `cancel()` | Removes entry from `vpms_queue.json` |

Auth: None (local filesystem).

### `vpms/adapters/avatar_webinar/worker.py` — Avatar Webinar Production

Avatar Webinar is an HTTP REST API (Node.js/Express) on `localhost:3200`. It uses Supabase JWT auth.

| Method | Implementation |
|--------|--------------|
| `health_check()` | GET `/health` |
| `get_capabilities()` | GET `/api/production/providers/list` |
| `dispatch()` | POST `/api/production/render-from-script` (one-call, best for VPMS) |
| `get_status()` | GET `/api/production/:id/status` — maps `done/failed/rendering` to VPMS |
| `get_artifacts()` | GET `/api/production/:id/assets` — returns final video, clips, scene renders |
| `cancel()` | Not supported by Avatar Webinar — returns False |

Auth: VPMS mints short-lived (5-min) HS256 JWTs using the Supabase service-role key.

### `vpms/adapters/vmf/worker.py` — Video Media Factory

VMF is a Node.js Express API on `localhost:4100`. Uses JWT Bearer auth.

| Method | Implementation |
|--------|--------------|
| `health_check()` | GET `/api/health` |
| `get_capabilities()` | GET `/api/providers` |
| `dispatch()` | POST `/api/pipeline/generate` (pipeline) or POST `/api/ugc/batch` (UGC) |
| `get_status()` | GET `/api/pipeline/status/:jobId` — maps VMF status to VPMS |
| `get_artifacts()` | GET `/api/renders/:jobId` — fetches final render URLs |
| `cancel()` | Not supported by VMF — returns False |

Auth: Set `VPMS_VMF_JWT_TOKEN` env var. Falls back gracefully if not set (anonymous calls to public endpoints).

## Environment Setup for Phase 2 Adapters

```bash
# VMF auth
export VPMS_VMF_JWT_TOKEN="your-vmf-jwt-token"

# Avatar Webinar auth
export VPMS_AVATAR_WEBINAR_SUPABASE_URL="https://your-project.supabase.co"
export VPMS_AVATAR_WEBINAR_SERVICE_KEY="your-service-role-key"
```
