# VPMS API Contracts — Phase 1

## Overview

VPMS exposes 11 Phase 1 REST endpoints via FastAPI. All endpoints live under `/api/v1/`. The root `/health` is also available.

Base URL: `http://localhost:8090` (development)

**Authentication**: All endpoints require `X-Source-App: <app_id>` header. Source apps are registered in `vpms.source_apps`.

## Endpoints

### GET /health

Root health check.

**Response 200**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2025-01-15T10:00:00Z"
}
```

---

### POST /api/v1/content/jobs

Create a content job (triggers Chronos workflow). Returns immediately with job ID.

**Request**:
```json
{
  "source_app": "podcast-factory",
  "request_type": "podcast_episode",
  "content": {
    "topic": "How AI agents help small businesses",
    "audience": "SMB owners",
    "goal": "education and lead generation",
    "duration_minutes": 10
  },
  "production": {
    "mode": "podcast_hybrid",
    "speakers": 2,
    "aspect_ratio": "16:9",
    "resolution": "1080p"
  },
  "requested_outputs": ["long_video", "shorts", "thumbnail", "metadata"],
  "budget": { "maximum_usd": 5 },
  "idempotency_key": "podcast-ep-2025-001",
  "priority": 5,
  "external_reference_id": "ext-12345"
}
```

**Response 201**:
```json
{
  "job_id": "vpms_01JABC123",
  "status": "QUEUED",
  "created_at": "2025-01-15T10:00:00Z"
}
```

**Idempotency**: If `idempotency_key` matches an existing job for the same `source_app`, returns the existing job without creating a duplicate.

---

### POST /api/v1/video/jobs

Create a video job (already has content/script).

**Request**: Same as `/content/jobs` but `job_type` is `"video"` internally.

**Response 201**: Same as above.

---

### GET /api/v1/jobs/:job_id

Get full job details.

**Response 200**:
```json
{
  "id": "vpms_01JABC123",
  "source_app": "podcast-factory",
  "external_reference_id": "ext-12345",
  "job_type": "content",
  "request_type": "podcast_episode",
  "status": "QUEUED",
  "priority": 5,
  "request_payload": { ... },
  "production_plan": null,
  "output": null,
  "estimated_cost": null,
  "actual_cost": null,
  "budget_limit": 5.0,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "error_code": null,
  "error_message": null,
  "retry_count": 0
}
```

**Response 404**: `{"detail": "Job not found"}`

---

### GET /api/v1/jobs/:job_id/status

Lightweight job status for polling.

**Response 200**:
```json
{
  "job_id": "vpms_01JABC123",
  "status": "QUEUED",
  "error_code": null,
  "error_message": null,
  "retry_count": 0,
  "estimated_cost": null,
  "actual_cost": null,
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z",
  "started_at": null,
  "completed_at": null
}
```

---

### GET /api/v1/jobs/:job_id/events

Get event history for a job (append-only audit trail).

**Response 200**:
```json
[
  {
    "event_id": "ev_abc123",
    "job_id": "vpms_01JABC123",
    "event_type": "JOB_CREATED",
    "timestamp": "2025-01-15T10:00:00Z",
    "previous_state": null,
    "new_state": "CREATED",
    "worker": null,
    "extra_data": {}
  },
  {
    "event_id": "ev_def456",
    "job_id": "vpms_01JABC123",
    "event_type": "JOB_QUEUED",
    "timestamp": "2025-01-15T10:00:01Z",
    "previous_state": "CREATED",
    "new_state": "QUEUED",
    "worker": null,
    "extra_data": {}
  }
]
```

---

### GET /api/v1/jobs/:job_id/artifacts

Get all artifacts for a job.

**Response 200**:
```json
{
  "job_id": "vpms_01JABC123",
  "artifacts": [
    {
      "id": "art_abc123",
      "job_id": "vpms_01JABC123",
      "artifact_type": "video",
      "name": "final_episode.mp4",
      "url": "https://storage.example.com/vpms/01JABC123/output.mp4",
      "file_size_bytes": 52428800,
      "mime_type": "video/mp4",
      "duration_seconds": 600.0,
      "width": 1920,
      "height": 1080,
      "extra_data": {},
      "created_at": "2025-01-15T10:05:00Z"
    }
  ],
  "total": 1
}
```

---

### POST /api/v1/jobs/:job_id/cancel

Cancel a job. Only works from non-terminal states.

**Request** (optional body):
```json
{ "reason": "User requested cancellation" }
```

**Response 200**:
```json
{
  "job_id": "vpms_01JABC123",
  "status": "CANCELLED",
  "message": "Job cancelled successfully"
}
```

**Response 400**: If job is already in a terminal state.

---

### POST /api/v1/jobs/:job_id/approve

Approve a job at an approval gate. Job must be at `WAITING_FOR_PRODUCTION_APPROVAL`, `WAITING_FOR_FINAL_APPROVAL`, or `SCRIPT_APPROVED`.

**Request**:
```json
{
  "decision": "APPROVED",
  "approved_by": "admin@example.com",
  "notes": "Looks good, proceed to production"
}
```

**Response 200**: Returns the approval record.

**Response 400**: If job is not at an approval gate.

---

### POST /api/v1/jobs/:job_id/reject

Reject a job.

**Request**:
```json
{
  "decision": "REJECTED",
  "approved_by": "admin@example.com",
  "notes": "Does not meet quality standards"
}
```

**Response 200**: Returns the rejection record.

---

### GET /api/v1/capabilities

List all worker capabilities.

**Query params**:
- `capability` — filter by capability name
- `visibility` — filter by visibility (internal, public)

**Response 200**:
```json
{
  "capabilities": [
    {
      "worker_id": "vmf",
      "capability": "mock_video_render",
      "code_present": true,
      "credential_verified": true,
      "integration_verified": true,
      "production_verified": false,
      "healthy": true,
      "estimated_cost": null,
      "average_latency_seconds": null,
      "max_concurrency": 1,
      "visibility": "internal",
      "is_active": true
    }
  ],
  "total": 1
}
```

---

### GET /api/v1/workers

List registered workers.

**Query params**:
- `status` — filter by status (AVAILABLE, UNAVAILABLE, etc.)
- `visibility` — filter by visibility

**Response 200**:
```json
{
  "workers": [
    {
      "worker_id": "vmf",
      "name": "Video Media Factory",
      "base_url": null,
      "status": "AVAILABLE",
      "visibility": "internal",
      "health_status": "HEALTHY",
      "last_health_check": null,
      "max_concurrency": 1,
      "current_load": 0,
      "avg_latency_seconds": null,
      "cost_per_job": null,
      "is_active": true,
      "created_at": "2025-01-15T10:00:00Z",
      "updated_at": "2025-01-15T10:00:00Z"
    }
  ],
  "total": 4
}
```

---

## Error Responses

All endpoints return structured error responses:

| Status | Meaning |
|---|---|
| 400 | Bad request / invalid state transition |
| 401 | Unknown or inactive source application |
| 404 | Resource not found |
| 500 | Internal server error |

```json
{ "detail": "Human-readable error message" }
```

## Async / Long-Running Work

All job creation endpoints return immediately with a `job_id`. Long-running production work is async. Poll `GET /api/v1/jobs/:job_id/status` to track progress.

## Idempotency

Both `/content/jobs` and `/video/jobs` accept `idempotency_key`. If the same `source_app + idempotency_key` pair is submitted twice, the second request returns the existing job without creating a duplicate.
