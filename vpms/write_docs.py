#!/usr/bin/env python3
"""Write VPMS Phase 1 documentation files."""

import os

BASE = "/opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo/docs"

def write(path, content):
    full = os.path.join(BASE, path)
    with open(full, "w") as f:
        f.write(content)
    print("  Wrote %s (%d bytes)" % (full, len(content)))


# ==============================================================
# FILE 1: architecture.md
# ==============================================================
write("architecture.md", """\
# VPMS Architecture

## Overview

VPMS (Video Product Management System) is a **management and orchestration layer** for video production workflows. It is explicitly NOT a video generation engine. VPMS sits between source applications (e.g., Podcast Factory, BookFactory, Affiliate Production) and the underlying production workers that generate video content.

VPMS provides:
- A canonical job state machine governing every production lifecycle
- An append-only event ledger as an immutable audit trail
- A worker registry with capability-based dispatch routing
- Human approval gates at key production milestones
- Idempotent job creation to prevent duplicates from retries

VPMS is a fork of **OpenMontage** (GNU AGPL v3.0), a video composition engine originally developed by Claude Code. VPMS reuses the AGPLv3 license and attribution. See LICENSE in this repository.

---

## Architecture Layers

```
+------------------------------------------------------------------+
|                    Source Applications                             |
|  (Podcast Factory, BookFactory, Affiliate Production, etc.)       |
|         All authenticated via X-Source-App header                 |
+----------------------------+--------------------------------------+
                             | HTTP/REST
                             v
+------------------------------------------------------------------+
|                      API Gateway (FastAPI)                         |
|              /api/v1/* endpoints -- 11 Phase 1 routes            |
|          All requests require X-Source-App authentication         |
+----------------------------+--------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                  Video Product Manager (JobManager)                |
|    - Job creation (content / video)                              |
|    - State machine enforcement (only valid transitions)           |
|    - Approval gate handling                                      |
|    - Cancellation and rejection                                  |
|    - Event emission on every transition                          |
+----------------------------+--------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|               Production Director (Dispatcher)                     |
|    - Selects worker based on capability and verification flags     |
|    - Dispatches to worker adapter                               |
|    - Processes worker receipts and artifacts                      |
|    - Enforces: no DISPATCHING -> COMPLETE (must go through      |
|      PROVIDER_CONFIRMED)                                          |
+----------------------------+--------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                    Worker Adapters (BaseWorkerAdapter)             |
|     +--------------+  +---------------+  +--------------+         |
|     | Chronos      |  | Avatar        |  | MoneyPrint   |         |
|     | Content      |  | Webinar       |  | Faceless     |         |
|     | Showrunner   |  |               |  |              |         |
|     +--------------+  +---------------+  +--------------+         |
|     +--------------+  +---------------+                          |
|     | VMF          |  | Mock Worker  |                           |
|     | (Phase 2)    |  | (Phase 1     |                           |
|     |              |  |  test only)  |                           |
|     +--------------+  +---------------+                           |
+------------------------------------------------------------------+
```

---

## Package Structure

The vpms/ package is organized by concern:

```
vpms/
|-- __init__.py          # Package metadata: version, product name, license
|-- main.py              # FastAPI app factory (create_app), runs on port 8090
|
|-- api/
|   |-- routes.py        # All 11 Phase 1 endpoints + health
|   +-- schemas.py       # Pydantic request/response models
|
|-- core/
|   |-- state_machine.py # JobState enum + JobStateMachine + InvalidTransitionError
|   |-- event_ledger.py  # EventLedger + JobEvent + EventType enum
|   |-- job_manager.py   # JobManager: all job operations go through here
|   +-- dispatcher.py    # Dispatcher: worker selection, dispatch, receipt processing
|
|-- db/
|   |-- models.py        # SQLAlchemy 2.0 ORM models (all in vpms schema)
|   |-- session.py       # Session factory, get_db dependency
|   |-- repositories/    # Data access layer
|   +-- migrations/
|       +-- 001_create_vpms_schema.sql  # Full schema + seed data
|
|-- registry/
|   |-- workers.py        # WorkerRegistryService
|   +-- capabilities.py  # CapabilityRegistryService + is_dispatchable()
|
|-- adapters/
|   |-- base.py          # BaseWorkerAdapter ABC + WorkerReceipt + WorkerJobRequest
|   +-- mock_worker.py  # Mock test worker (Phase 1, not for production)
|
|-- qa/                  # QA report generation (Phase 2)
|-- security/            # Authentication / authorization (future)
+-- tests/
    |-- unit/            # Unit tests: state_machine, event_ledger, schemas
    +-- integration/     # API integration tests
```

---

## PostgreSQL Schema

VPMS uses the **existing Supabase PostgreSQL 17.6** instance. It does NOT create a new database server. All VPMS tables live in the vpms schema:

```
public             -- existing Supabase schema
supabase_*        -- existing Supabase schemas
vpms              -- VPMS schema (created by migration 001)
```

Tables in the vpms schema:

| Table | Purpose |
|---|---|
| vpms.source_apps | Registered source applications |
| vpms.jobs | Job records with status, payload, budget |
| vpms.job_events | Append-only event ledger |
| vpms.worker_registry | Registered production workers |
| vpms.worker_capabilities | Capability + verification flags per worker |
| vpms.worker_jobs | VPMS-side tracking of worker-side jobs |
| vpms.artifacts | Produced video/audio/image artifacts |
| vpms.qa_reports | Technical and creative QA reports |
| vpms.approvals | Human approval records at gates |
| vpms.publish_receipts | Publishing platform receipts |

A composite unique index on (source_app, idempotency_key) enforces idempotency at the database level.

---

## State Machine

The state machine is the **canonical state authority**. No code may directly mutate jobs.status. All transitions must go through JobManager.transition_state(), which:

1. Validates the transition against the TRANSITIONS map
2. Raises InvalidTransitionError for invalid transitions
3. Updates the job status
4. Emits a job_events record

This means the state machine is the single source of truth for "where is this job in its lifecycle."

---

## Event Ledger

The event ledger (vpms.job_events) is **append-only**. Events cannot be updated or deleted. Every state transition produces a JobEvent record with:

- event_type (e.g., STATE_TRANSITION, WORKER_DISPATCHED, WORKER_RECEIPT_RECEIVED)
- previous_state / new_state
- worker (if applicable)
- extra_data (arbitrary metadata dict)

The full event history for any job is queryable via GET /api/v1/jobs/:jobId/events.

---

## All 11 API Endpoints

| Method | Path | Role |
|---|---|---|
| GET | /health | Root health check (no auth) |
| GET | /api/v1/health | API health check (no auth) |
| POST | /api/v1/content/jobs | Create a content job (triggers Chronos workflow) |
| POST | /api/v1/video/jobs | Create a video job (already has content/script) |
| GET | /api/v1/jobs/:jobId | Get full job details |
| GET | /api/v1/jobs/:jobId/status | Get lightweight job status |
| GET | /api/v1/jobs/:jobId/events | Get event history for a job |
| GET | /api/v1/jobs/:jobId/artifacts | Get all artifacts for a job |
| POST | /api/v1/jobs/:jobId/cancel | Cancel a job |
| POST | /api/v1/jobs/:jobId/approve | Approve a job at a gate |
| POST | /api/v1/jobs/:jobId/reject | Reject a job |
| GET | /api/v1/capabilities | List all worker capabilities |
| GET | /api/v1/workers | List registered workers |

---

## Authentication

VPMS uses **source application authentication** via the X-Source-App HTTP header. There is no per-endpoint auth middleware for Phase 1 -- every API route (except health) validates that the X-Source-App value matches a registered, active entry in vpms.source_apps.

Seeded source apps (from migration 001):
- podcast-factory -- Podcast Factory, Podcast episode production system
- bookfactory -- BookFactory, Book factory video production
- affiliate-production -- Affiliate Production, Affiliate video production
- vpms-internal -- VPMS Internal, Internal VPMS test client

Future phases will add API key hashing and per-app permission scopes.

---

## Worker Registry and Capability Registry

### Worker Registry

vpms.worker_registry stores worker metadata: health status, concurrency limits, latency, cost, and load. The WorkerRegistryService manages read/write.

Seeded workers (from migration 001):
- chronos -- Chronos Content Showrunner (Phase 2 wiring)
- avatar-webinar -- Avatar Webinar (Phase 2 wiring)
- moneyprint -- MoneyPrint Faceless (Phase 2 wiring)
- vmf -- Video Media Factory (Phase 2 wiring)
- mock (via adapter, not in DB) -- Phase 1 test worker

### Capability Registry

vpms.worker_capabilities stores the capabilities each worker offers along with five verification flags. The CapabilityRegistryService provides find_dispatchable() and can_dispatch().

The is_dispatchable() logic on WorkerCapability:

```python
def is_dispatchable(self) -> bool:
    return (
        self.code_present
        and self.credential_verified
        and self.integration_verified
        and self.healthy
    )
```

**Production dispatch is refused** if any of these flags is false.

The only seeded capability in Phase 1 is vmf -> mock_video_render, with code_present, credential_verified, integration_verified, and healthy all true, but production_verified false. The is_dispatchable() check does not require production_verified.

---

## Phase 1 vs Phase 2 Scope

### Phase 1 (current)
- Full API: 11 endpoints as documented above
- State machine: all states, transitions, and enforcement
- Event ledger: append-only audit trail
- Job creation: content jobs (triggers Chronos path) and video jobs (already has script)
- Worker dispatch: dispatcher and WorkerReceipt contract with mock worker
- Capability registry: verification flags and dispatch eligibility
- Human approval gates: production approval and final approval
- Idempotency: via source_app + idempotency_key composite
- Persistent PostgreSQL storage: vpms schema
- Health checks: root and API-level

### Phase 2 (planned, not implemented)
- Real worker adapters: Chronos, Avatar Webinar, VMF (interface exists in adapters/base.py, not wired)
- Full production verification pipeline
- Publishing workflow: PUBLISH_REQUESTED -> SCHEDULED -> PUBLISHED
- Creative QA engine
- Budget enforcement and cost tracking
- API key authentication (beyond source app header)
- Webhook notifications
- Rate limiting

---

## License and Attribution

VPMS is a fork of **OpenMontage**, Copyright (c) Claude Code. OpenMontage is released under the **GNU General Public License v3.0 (AGPLv3)**.

VPMS retains the AGPLv3 license and attribution requirements. See the LICENSE file in this repository.

```
VPMS -- Video Product Management System
Copyright (c) Claude Code, Video Product Management System
A fork of OpenMontage (AGPLv3)
```
""")

# ==============================================================
# FILE 2: api-contracts.md
# ==============================================================
write("api-contracts.md", """\
# VPMS API Contracts -- Phase 1

All 13 endpoints (11 operational + 2 health) are documented below.

Base URL: `http://localhost:8090`

---

## Authentication

All endpoints except /health and /api/v1/health require the X-Source-App HTTP header set to a registered source application ID.

Example:
```
X-Source-App: podcast-factory
```

Registered source apps (seeded by migration 001):
- podcast-factory
- bookfactory
- affiliate-production
- vpms-internal

If the header is missing or references an inactive app, the server returns HTTP 401.

---

## Error Response Format

All error responses follow this structure:

```json
{
  "detail": "Human-readable error message"
}
```

HTTP 400: Bad request (validation error, invalid transition, etc.)
HTTP 401: Unauthorized (missing or unknown X-Source-App)
HTTP 404: Not found (job not found)
HTTP 422: Unprocessable entity (Pydantic validation failure)
HTTP 500: Internal server error

---

## Endpoints

### GET /health

Root-level health check. No authentication required.

**Response body** (HTTP 200):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

Fields:
- status: Always "healthy" when the endpoint responds
- version: The VPMS version string from vpms/__init__.py
- database: "connected" if the DB query succeeded, "disconnected" otherwise
- timestamp: ISO 8601 timestamp of the response

**Error cases**: Returns 500 if the database is disconnected.

---

### GET /api/v1/health

API-level health check. No authentication required.

Identical response format to GET /health. Provided for load balancer health checks under /api/v1/.

**Response body** (HTTP 200):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

### POST /api/v1/content/jobs

Create a new content job. The job enters the state machine at CREATED, then immediately transitions to QUEUED.

**Idempotency**: If idempotency_key is provided and matches an existing job from the same source_app, the existing job is returned with HTTP 201. No new job is created.

**Request body**:
```json
{
  "source_app": "podcast-factory",
  "request_type": "episode-outline",
  "content": {
    "topic": "How to build a podcast",
    "target_duration_seconds": 600,
    "style": "educational"
  },
  "production": {
    "resolution": "1080p",
    "format": "landscape"
  },
  "requested_outputs": ["video", "audio", "transcript"],
  "budget": {
    "maximum_usd": 50.0,
    "currency": "USD"
  },
  "external_reference_id": "pf-episode-001",
  "idempotency_key": "episode-2025-01-15-001",
  "priority": 7,
  "created_by": "user@example.com"
}
```

Fields (from schemas.py ContentJobRequest):
- source_app (required): Registered source application identifier
- request_type (required): Type of content request (e.g., "episode-outline", "article-summary")
- content (required): Arbitrary dict describing the content specification
- production (optional): Production parameters (resolution, format, etc.)
- requested_outputs (optional): List of desired output types
- budget (optional): Budget constraints with maximum_usd
- external_reference_id (optional): External system reference
- idempotency_key (optional): Client-supplied idempotency key
- priority (optional, default=5, range 1-10): Job priority
- created_by (optional): User who created the job

**Response body** (HTTP 201):
```json
{
  "job_id": "vpms_a1b2c3d4e5f6",
  "status": "QUEUED",
  "created_at": "2025-01-15T10:30:00Z"
}
```

For idempotent matches, the same response is returned with the existing job's ID and status.

**Error cases**:
- HTTP 401: Unknown or inactive source application
- HTTP 422: Validation error (missing required fields, invalid priority range)

---

### POST /api/v1/video/jobs

Create a new video job. Used when the caller already has content/script and wants to go directly to production. Same idempotency semantics as content/jobs.

**Request body**: Identical fields to ContentJobRequest (see above).

**Response body** (HTTP 201):
```json
{
  "job_id": "vpms_f6e5d4c3b2a1",
  "status": "QUEUED",
  "created_at": "2025-01-15T10:31:00Z"
}
```

---

### GET /api/v1/jobs/:jobId

Get full job details including all metadata.

**Path parameters**:
- jobId: The VPMS job ID (e.g., "vpms_a1b2c3d4e5f6")

**Response body** (HTTP 200):
```json
{
  "id": "vpms_a1b2c3d4e5f6",
  "source_app": "podcast-factory",
  "external_reference_id": "pf-episode-001",
  "job_type": "content",
  "request_type": "episode-outline",
  "status": "QUEUED",
  "priority": 7,
  "request_payload": {
    "content": { "topic": "How to build a podcast", "target_duration_seconds": 600, "style": "educational" },
    "production": { "resolution": "1080p", "format": "landscape" },
    "requested_outputs": ["video", "audio", "transcript"],
    "budget": { "maximum_usd": 50.0, "currency": "USD" }
  },
  "production_plan": null,
  "output": null,
  "estimated_cost": null,
  "actual_cost": null,
  "budget_limit": 50.0,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z",
  "started_at": null,
  "completed_at": null,
  "error_code": null,
  "error_message": null,
  "retry_count": 0
}
```

**Error cases**: HTTP 404 if job not found.

---

### GET /api/v1/jobs/:jobId/status

Get lightweight job status. Faster than GET /jobs/:jobId when only status metadata is needed.

**Response body** (HTTP 200):
```json
{
  "job_id": "vpms_a1b2c3d4e5f6",
  "status": "QUEUED",
  "error_code": null,
  "error_message": null,
  "retry_count": 0,
  "estimated_cost": null,
  "actual_cost": null,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z",
  "started_at": null,
  "completed_at": null
}
```

**Error cases**: HTTP 404 if job not found.

---

### GET /api/v1/jobs/:jobId/events

Get the complete event history for a job, in chronological order.

**Response body** (HTTP 200) -- list of events:
```json
[
  {
    "event_id": "ev_abc123def456",
    "job_id": "vpms_a1b2c3d4e5f6",
    "event_type": "JOB_CREATED",
    "timestamp": "2025-01-15T10:30:00Z",
    "previous_state": null,
    "new_state": "CREATED",
    "worker": null,
    "extra_data": {
      "source_app": "podcast-factory",
      "request_type": "episode-outline",
      "idempotency_key": "episode-2025-01-15-001"
    }
  },
  {
    "event_id": "ev_def456abc789",
    "job_id": "vpms_a1b2c3d4e5f6",
    "event_type": "JOB_QUEUED",
    "timestamp": "2025-01-15T10:30:00Z",
    "previous_state": "CREATED",
    "new_state": "QUEUED",
    "worker": null,
    "extra_data": {}
  }
]
```

**Error cases**: HTTP 404 if job not found.

---

### GET /api/v1/jobs/:jobId/artifacts

Get all artifacts produced for a job.

**Response body** (HTTP 200):
```json
{
  "job_id": "vpms_a1b2c3d4e5f6",
  "artifacts": [
    {
      "id": "art_ghi789jkl012",
      "job_id": "vpms_a1b2c3d4e5f6",
      "artifact_type": "video",
      "name": "episode-001.mp4",
      "url": "https://storage.example.com/artifacts/episode-001.mp4",
      "file_path": null,
      "file_size_bytes": 104857600,
      "mime_type": "video/mp4",
      "duration_seconds": 600.0,
      "width": 1920,
      "height": 1080,
      "extra_data": {},
      "created_at": "2025-01-15T11:00:00Z"
    }
  ],
  "total": 1
}
```

**Error cases**: HTTP 404 if job not found.

---

### POST /api/v1/jobs/:jobId/cancel

Cancel a job. Only valid if the job is in a state that can transition to CANCELLED.

**Request body** (optional):
```json
{
  "reason": "Customer requested cancellation"
}
```

**Response body** (HTTP 200):
```json
{
  "job_id": "vpms_a1b2c3d4e5f6",
  "status": "CANCELLED",
  "message": "Job cancelled successfully"
}
```

**Error cases**:
- HTTP 400: Invalid state transition (job cannot be cancelled from its current state)
- HTTP 404: Job not found

---

### POST /api/v1/jobs/:jobId/approve

Approve a job at a human approval gate. The server determines the gate from the job's current state:
- WAITING_FOR_PRODUCTION_APPROVAL -> transitions to PRODUCTION_APPROVED
- WAITING_FOR_FINAL_APPROVAL -> transitions to READY
- SCRIPT_APPROVED -> transitions to PRODUCTION_APPROVED

**Request body**:
```json
{
  "decision": "APPROVED",
  "approved_by": "supervisor@example.com",
  "notes": "Looks good, proceed to production.",
  "extra_data": {}
}
```

Fields:
- decision (required): Must be "APPROVED" (enum pattern enforced by Pydantic)
- approved_by (optional): Who approved the job
- notes (optional): Approval notes
- extra_data (optional): Additional metadata

**Response body** (HTTP 200):
```json
{
  "id": "apr_mno345pqr678",
  "job_id": "vpms_a1b2c3d4e5f6",
  "approval_type": "PRODUCTION",
  "decision": "APPROVED",
  "approved_by": "supervisor@example.com",
  "notes": "Looks good, proceed to production.",
  "timestamp": "2025-01-15T11:05:00Z"
}
```

**Error cases**:
- HTTP 400: Job is not at an approval gate
- HTTP 404: Job not found

---

### POST /api/v1/jobs/:jobId/reject

Reject a job. Transitions the job to REJECTED (a terminal failure state).

**Request body**:
```json
{
  "decision": "REJECTED",
  "approved_by": "qa-reviewer@example.com",
  "notes": "Script quality below threshold. Please revise."
}
```

**Response body** (HTTP 200):
```json
{
  "id": "apr_stu901vwx234",
  "job_id": "vpms_a1b2c3d4e5f6",
  "approval_type": "REJECTION",
  "decision": "REJECTED",
  "approved_by": "qa-reviewer@example.com",
  "notes": "Script quality below threshold. Please revise.",
  "timestamp": "2025-01-15T11:10:00Z"
}
```

**Error cases**: HTTP 404 if job not found.

---

### GET /api/v1/capabilities

List all worker capabilities across all registered workers.

**Query parameters**:
- capability (optional): Filter by capability name (exact match)
- visibility (optional): Filter by visibility ("internal" or "public")

**Response body** (HTTP 200):
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

Verification flag meanings:
- code_present: Worker code exists for this capability
- credential_verified: Credentials/API keys are validated
- integration_verified: Integration tests pass
- production_verified: Production environment verified (Phase 2)
- healthy: Worker is passing health checks

A capability is dispatchable only when code_present AND credential_verified AND integration_verified AND healthy are all true. production_verified is not required for Phase 1 dispatch.

---

### GET /api/v1/workers

List all registered workers.

**Query parameters**:
- status (optional): Filter by worker status (e.g., "AVAILABLE")
- visibility (optional): Filter by visibility ("internal" or "public")

**Response body** (HTTP 200):
```json
{
  "workers": [
    {
      "worker_id": "chronos",
      "name": "Chronos Content Showrunner",
      "base_url": null,
      "status": "AVAILABLE",
      "visibility": "internal",
      "health_status": "UNKNOWN",
      "last_health_check": null,
      "max_concurrency": 1,
      "current_load": 0,
      "avg_latency_seconds": null,
      "cost_per_job": null,
      "is_active": true,
      "created_at": "2025-01-15T00:00:00Z",
      "updated_at": "2025-01-15T00:00:00Z"
    },
    {
      "worker_id": "avatar-webinar",
      "name": "Avatar Webinar",
      "base_url": null,
      "status": "AVAILABLE",
      "visibility": "internal",
      "health_status": "UNKNOWN",
      "last_health_check": null,
      "max_concurrency": 1,
      "current_load": 0,
      "avg_latency_seconds": null,
      "cost_per_job": null,
      "is_active": true,
      "created_at": "2025-01-15T00:00:00Z",
      "updated_at": "2025-01-15T00:00:00Z"
    },
    {
      "worker_id": "moneyprint",
      "name": "MoneyPrint Faceless",
      "base_url": null,
      "status": "AVAILABLE",
      "visibility": "internal",
      "health_status": "UNKNOWN",
      "last_health_check": null,
      "max_concurrency": 1,
      "current_load": 0,
      "avg_latency_seconds": null,
      "cost_per_job": null,
      "is_active": true,
      "created_at": "2025-01-15T00:00:00Z",
      "updated_at": "2025-01-15T00:00:00Z"
    },
    {
      "worker_id": "vmf",
      "name": "Video Media Factory",
      "base_url": null,
      "status": "AVAILABLE",
      "visibility": "internal",
      "health_status": "UNKNOWN",
      "last_health_check": null,
      "max_concurrency": 1,
      "current_load": 0,
      "avg_latency_seconds": null,
      "cost_per_job": null,
      "is_active": true,
      "created_at": "2025-01-15T00:00:00Z",
      "updated_at": "2025-01-15T00:00:00Z"
    }
  ],
  "total": 4
}
```
""")

# ==============================================================
# FILE 3: worker-contract.md
# ==============================================================
write("worker-contract.md", """\
# VPMS Worker Contract

## Overview

VPMS interacts with external production systems ("workers") through a well-defined adapter interface. Workers are not embedded in VPMS -- they are external services that VPMS dispatches jobs to and receives receipts from. This document describes:

1. The canonical worker adapter interface (BaseWorkerAdapter ABC)
2. The WorkerReceipt contract -- what workers must produce and when
3. The WorkerJob model -- VPMS-side tracking of worker-side jobs
4. The mock test worker -- how to run it and what it simulates
5. The production worker contract -- what real workers must implement
6. The five verification flags and dispatch eligibility
7. Phase 2 workers (interface only, not wired)

---

## BaseWorkerAdapter Interface

All worker adapters inherit from vpms/adapters/base.py::BaseWorkerAdapter. It is an abstract base class (ABC) with six required methods.

```python
from vpms.adapters.base import BaseWorkerAdapter

class MyWorkerAdapter(BaseWorkerAdapter):
    @property
    def worker_id(self) -> str:
        return "my-worker"

    @property
    def base_url(self) -> str:
        return "https://my-worker.internal.example.com"

    async def health_check(self) -> WorkerHealth:
        ...

    async def get_capabilities(self) -> WorkerCapabilities:
        ...

    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        ...

    async def get_status(self, worker_job_id: str) -> WorkerReceipt:
        ...

    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]:
        ...

    async def cancel(self, worker_job_id: str) -> bool:
        ...
```

### health_check() -> WorkerHealth

Must return the current health status of the worker. VPMS uses this to populate vpms.worker_registry.health_status and vpms.worker_capabilities.healthy.

```python
class WorkerHealth(BaseModel):
    status: str       # "healthy" or "unhealthy"
    worker_id: str
    timestamp: str    # ISO 8601
```

### get_capabilities() -> WorkerCapabilities

Returns the list of capabilities this worker offers.

```python
class WorkerCapabilities(BaseModel):
    worker_id: str
    capabilities: list[dict]  # list of {capability: str, version: str, ...}
```

### dispatch(job_request: WorkerJobRequest) -> WorkerReceipt

Called by the Dispatcher to send a job to the worker. This is the main integration point.

```python
class WorkerJobRequest(BaseModel):
    vpms_job_id: str
    worker: str
    production_type: str
    script: Optional[dict] = None
    scene_plan: Optional[list] = None
    brand: Optional[dict] = None
    speakers: Optional[list] = None
    output: Optional[dict] = None
    requested_outputs: Optional[list] = None
    budget: Optional[dict] = None
    metadata: Optional[dict] = None
```

The worker must return a WorkerReceipt (see below).

### get_status(worker_job_id: str) -> WorkerReceipt

Poll the worker for the status of a previously dispatched job. The worker_job_id is the ID returned by the worker in the WorkerReceipt.

### get_artifacts(worker_job_id: str) -> list[WorkerArtifact]

Retrieve artifacts from the worker after job completion.

```python
class WorkerArtifact(BaseModel):
    type: str
    name: str
    url: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    checksum: Optional[str] = None
    metadata: dict = {}
```

### cancel(worker_job_id: str) -> bool

Cancel a running job on the worker. Returns True if cancellation succeeded.

---

## WorkerReceipt Contract

The WorkerReceipt is the fundamental proof-of-work artifact. Every meaningful worker operation must produce one.

```python
class WorkerReceipt(BaseModel):
    vpms_job_id: str           # VPMS job ID (echoed back)
    worker: str                # Worker ID
    worker_job_id: str         # ID assigned by the worker
    status: str                # PENDING | PROVIDER_CONFIRMED | COMPLETED | FAILED
    provider: Optional[str] = None    # e.g., "heygen", "runway"
    model: Optional[str] = None       # e.g., "s-01-video", "gen3-turbo"
    artifacts: list[dict] = []        # List of WorkerArtifact dicts
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    started_at: str            # ISO 8601
    completed_at: Optional[str] = None  # ISO 8601
    errors: list[str] = []
```

### Receipt Lifecycle

1. dispatch() returns a receipt with status=PENDING. VPMS creates a WorkerJob record and transitions the VPMS job to DISPATCHING.

2. get_status() or a webhook may return status=PROVIDER_CONFIRMED. VPMS transitions the job to PROVIDER_CONFIRMED.

3. When done, the worker returns status=COMPLETED with artifacts. VPMS transitions the job to PROVIDER_CONFIRMED and processes artifacts.

4. On failure, the worker returns status=FAILED with error messages. VPMS classifies the errors as transient or permanent and transitions to RETRYABLE_FAILURE or FAILED respectively.

### Receipt Processing in Dispatcher.process_receipt()

When VPMS receives a receipt, the Dispatcher:

1. Updates the WorkerJob record with status, provider, model, costs, errors
2. Creates Artifact records for each artifact in the receipt
3. Logs a WORKER_RECEIPT_RECEIVED event
4. Transitions the job based on receipt status:
   - COMPLETED -> PROVIDER_CONFIRMED
   - FAILED with transient errors -> RETRYABLE_FAILURE
   - FAILED with permanent errors -> FAILED

### Key Rule: No Direct DISPATCHING to COMPLETE

VPMS enforces that no job can go directly from DISPATCHING to a terminal or post-production state. All receipts must flow through PROVIDER_CONFIRMED. This ensures the job lifecycle is explicit and auditable.

---

## WorkerJob Model

The vpms.worker_jobs table tracks VPMS's understanding of worker-side jobs:

```sql
CREATE TABLE vpms.worker_jobs (
    id VARCHAR(32) PRIMARY KEY,          -- e.g., "wrkj_a1b2c3d4e5f6"
    vpms_job_id VARCHAR(32) NOT NULL,   -- links to vpms.jobs
    worker_id VARCHAR(64) NOT NULL,      -- links to vpms.worker_registry
    worker_job_id VARCHAR(256),          -- worker's own job ID (set on receipt)
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    provider VARCHAR(64),
    model VARCHAR(128),
    estimated_cost NUMERIC(10, 4),
    actual_cost NUMERIC(10, 4),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    errors JSONB NOT NULL DEFAULT '[]',
    extra_data JSONB NOT NULL DEFAULT '{}'
);
```

A WorkerJob is created on dispatch and updated on receipt. It serves as the VPMS-side record of the worker-side job lifecycle.

---

## Mock Test Worker

VPMS ships with a mock test worker (vpms/adapters/mock_worker.py) for Phase 1 integration testing. It is **not for production use**.

### Running the Mock Worker

The mock worker is a standalone FastAPI app that implements the production worker contract. To run it:

```bash
cd /opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo
uvicorn vpms.adapters.mock_worker:app --host 127.0.0.1 --port 8091
```

### Simulated Failure Modes

The mock worker accepts query parameters to simulate various failure conditions:

- ?simulate=timeout -- Simulates a network timeout
- ?simulate=transient_error -- Simulates a transient failure (rate limit, temporary unavailable)
- ?simulate=permanent_error -- Simulates a permanent failure (invalid credentials, bad request)
- ?delay_seconds=N -- Introduces an artificial delay before responding

These modes allow testing of:
- Retry logic (RETRYABLE_FAILURE -> re-queue)
- Dead-letter handling (FAILED -> terminal)
- Timeout handling
- Idempotency

### Mock Worker Endpoints

```
GET  /health                    # Health check
GET  /capabilities              # Returns mock capabilities
POST /jobs                      # Create mock job (returns pending receipt)
GET  /jobs/:worker_job_id       # Get job status (simulates progression)
GET  /jobs/:worker_job_id/artifacts  # Get mock artifacts
POST /jobs/:worker_job_id/cancel     # Cancel mock job
```

---

## Production Worker Contract

A production worker must implement the following HTTP contract. VPMS calls these endpoints through a worker adapter.

### GET /health

Returns worker health status. Must return HTTP 200 with:

```json
{
  "status": "healthy",
  "worker_id": "heygen",
  "timestamp": "2025-01-15T10:00:00Z"
}
```

Return HTTP 503 if unhealthy.

### GET /capabilities

Returns the worker's capabilities:

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

Create a new job on the worker. VPMS sends a WorkerJobRequest as the request body. The worker must return a WorkerReceipt with status=PENDING and a worker_job_id.

### GET /jobs/:worker_job_id

Poll for job status. Returns a WorkerReceipt with current status.

### GET /jobs/:worker_job_id/artifacts

Returns the list of WorkerArtifact produced by the job.

### POST /jobs/:worker_job_id/cancel

Cancel a running job. Returns HTTP 200 on success.

---

## Verification Flags and Dispatch Eligibility

Each WorkerCapability record has five boolean verification flags. These are the gates that determine whether a worker can be used for production dispatch.

| Flag | Meaning |
|---|---|
| code_present | Worker code exists and is deployed for this capability |
| credential_verified | API keys / credentials are validated and active |
| integration_verified | Integration tests pass in the test environment |
| production_verified | Worker has been verified in the production environment |
| healthy | Worker is passing periodic health checks |

The is_dispatchable() method on WorkerCapability returns True only when:

```python
def is_dispatchable(self) -> bool:
    return (
        self.code_present
        and self.credential_verified
        and self.integration_verified
        and self.healthy
    )
```

**Note**: production_verified is NOT required for Phase 1 dispatch eligibility. It is a Phase 2 flag.

If any of the four required flags is False, the Dispatcher refuses to dispatch:

```python
if not cap.is_dispatchable():
    raise ValueError(
        f"Capability {capability} on worker {worker_id} is not dispatchable "
        f"(code_present={cap.code_present}, "
        f"credential_verified={cap.credential_verified}, "
        f"integration_verified={cap.integration_verified}, "
        f"healthy={cap.healthy})"
    )
```

Verification flags are managed via CapabilityRegistryService.update_verification() and can be updated by operators as workers are validated.

---

## Phase 2 Workers

The following workers are defined in the database (migration 001) but their adapters are not yet wired in Phase 1. Their interfaces exist in adapters/base.py and adapters/ but the dispatch logic is not connected.

### Chronos Content Showrunner (worker_id: "chronos")

Planned capabilities:
- content-generation: Generate full content outlines and scripts
- research: Topic research and fact verification
- script-writing: Professional script composition

Phase 2 wiring will connect Chronos as the primary content generation worker.

### Avatar Webinar (worker_id: "avatar-webinar")

Planned capabilities:
- avatar-video: AI avatar-based video generation
- webinar-production: Webinar-style video production

Phase 2 wiring will connect Avatar Webinar as the avatar video generation worker.

### VMF -- Video Media Factory (worker_id: "vmf")

Planned capabilities:
- video-render: Final video rendering and composition
- video-merge: Multi-format video output generation
- mock-video-render: Test/fallback rendering

Phase 2 wiring will connect VMF as the rendering and output worker. The mock_video_render capability (seeded in Phase 1) is the initial test capability for VMF.

### MoneyPrint Faceless (worker_id: "moneyprint")

Planned capabilities:
- faceless-video: Faceless video generation for affiliate content
- automated-narration: AI narration generation

Phase 2 wiring will connect MoneyPrint as the faceless video worker.
""")

# ==============================================================
# FILE 4: job-state-machine.md
# ==============================================================
write("job-state-machine.md", """\
# VPMS Job State Machine

## Overview

The job state machine is the **canonical authority** on job lifecycle state. All state transitions in VPMS must pass through JobManager.transition_state(), which delegates to JobStateMachine. The state machine:

1. Validates transitions against the TRANSITIONS map
2. Raises InvalidTransitionError for invalid transitions
3. Does not mutate the database directly -- it returns the new state for the caller to persist

Every transition emits a job_events record, making the full history auditable.

Source: vpms/core/state_machine.py

---

## All States

### Normal Progression States (in order)

| State | Description |
|---|---|
| CREATED | Job created, not yet queued |
| QUEUED | Job accepted and queued for processing |
| PLANNING | Production planning underway |
| RESEARCHING | Research phase (content gathering) |
| RESEARCH_READY | Research complete, ready for scripting |
| SCRIPTING | Script writing in progress |
| SCRIPT_EVALUATING | Script being evaluated/qa'd |
| SCRIPT_APPROVED | Script approved, ready for production planning |
| PRODUCTION_PLANNING | Production plan being assembled |
| WAITING_FOR_PRODUCTION_APPROVAL | Human approval gate: production plan |
| PRODUCTION_APPROVED | Production plan approved |
| DISPATCHING | Job dispatched to worker, awaiting response |
| ASSET_GENERATION | Worker is generating assets |
| RENDERING | Worker is rendering final output |
| PROVIDER_CONFIRMED | Worker confirmed job completion |
| OUTPUT_VERIFICATION | Output being verified |
| TECHNICAL_QA | Technical QA checks (resolution, codec, etc.) |
| CREATIVE_QA | Creative QA checks (content quality) |
| WAITING_FOR_FINAL_APPROVAL | Human approval gate: final output |
| READY | Job ready for publishing |
| PUBLISH_REQUESTED | Publishing requested |
| SCHEDULED | Publishing scheduled |
| PUBLISHED | Job published (terminal success) |

### Failure / Terminal Non-Success States

| State | Description |
|---|---|
| RETRYABLE_FAILURE | Transient failure -- can be re-queued or re-dispatched |
| FAILED | Permanent failure -- terminal |
| BLOCKED | Job blocked -- can be re-queued or cancelled |
| REJECTED | Human rejected at approval gate -- terminal |
| CANCELLED | Cancelled by user -- terminal |

---

## Complete Transitions Table

The TRANSITIONS dict in state_machine.py defines all valid from -> to transitions.

### Normal Forward Flow

```
CREATED              -> QUEUED, CANCELLED
QUEUED               -> PLANNING, CANCELLED
PLANNING             -> RESEARCHING, CANCELLED, BLOCKED
RESEARCHING          -> RESEARCH_READY, RETRYABLE_FAILURE, FAILED
RESEARCH_READY       -> SCRIPTING, CANCELLED
SCRIPTING            -> SCRIPT_EVALUATING, RETRYABLE_FAILURE, FAILED
SCRIPT_EVALUATING    -> SCRIPT_APPROVED, SCRIPTING (retry with feedback), REJECTED, FAILED
SCRIPT_APPROVED      -> PRODUCTION_PLANNING, CANCELLED
PRODUCTION_PLANNING  -> WAITING_FOR_PRODUCTION_APPROVAL, CANCELLED, BLOCKED
WAITING_FOR_PRODUCTION_APPROVAL -> PRODUCTION_APPROVED, REJECTED, CANCELLED
PRODUCTION_APPROVED  -> DISPATCHING, CANCELLED
DISPATCHING          -> ASSET_GENERATION, RETRYABLE_FAILURE, FAILED, BLOCKED
ASSET_GENERATION     -> RENDERING, RETRYABLE_FAILURE, FAILED, BLOCKED
RENDERING            -> PROVIDER_CONFIRMED, RETRYABLE_FAILURE, FAILED, BLOCKED
PROVIDER_CONFIRMED   -> OUTPUT_VERIFICATION, RETRYABLE_FAILURE, FAILED
OUTPUT_VERIFICATION  -> TECHNICAL_QA, RETRYABLE_FAILURE, FAILED
TECHNICAL_QA         -> CREATIVE_QA, RETRYABLE_FAILURE, FAILED, BLOCKED
CREATIVE_QA          -> WAITING_FOR_FINAL_APPROVAL, RETRYABLE_FAILURE, FAILED, BLOCKED
WAITING_FOR_FINAL_APPROVAL -> READY, REJECTED, CANCELLED
READY                -> PUBLISH_REQUESTED, CANCELLED
PUBLISH_REQUESTED    -> SCHEDULED, FAILED, RETRYABLE_FAILURE
SCHEDULED            -> PUBLISHED, FAILED, RETRYABLE_FAILURE
```

### Retry Path

```
RETRYABLE_FAILURE    -> QUEUED (re-queue), DISPATCHING (re-dispatch), FAILED (escalate), BLOCKED
```

### Failure Terminal States

```
FAILED               -> (no outgoing transitions -- terminal)
REJECTED             -> (no outgoing transitions -- terminal)
CANCELLED            -> (no outgoing transitions -- terminal)
BLOCKED              -> QUEUED, CANCELLED
PUBLISHED            -> (no outgoing transitions -- terminal success)
```

---

## Invalid Transition Behavior

When an invalid transition is attempted, JobStateMachine.transition() raises InvalidTransitionError:

```python
class InvalidTransitionError(Exception):
    def __init__(self, from_state: JobState, to_state: JobState):
        self.from_state = from_state
        self.to_state = to_state
        allowed = TRANSITIONS.get(from_state, set())
        super().__init__(
            f"Invalid state transition: {from_state.value} -> {to_state.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )
```

The API layer catches this and returns HTTP 400:

```python
@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: CancelRequest = None, db: Session = Depends(get_db)):
    manager = JobManager(db)
    try:
        job = manager.cancel_job(job_id, reason=request.reason if request else None)
        return CancelResponse(job_id=job.id, status=job.status, message="Job cancelled successfully")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Terminal States

A state is terminal if it has no valid outgoing transitions (i.e., len(TRANSITIONS[state]) == 0):

- FAILED -- terminal failure
- REJECTED -- human rejection
- CANCELLED -- user cancellation
- PUBLISHED -- successful completion

BLOCKED and RETRYABLE_FAILURE are not terminal -- they have outgoing transitions.

---

## Approval Gates

VPMS has two human approval gates:

### 1. WAITING_FOR_PRODUCTION_APPROVAL

Triggered after PRODUCTION_PLANNING. The production plan (scene plan, assets, rendering settings) is reviewed by a human before actual video generation begins.

- Approve (APPROVAL_REQUESTED -> APPROVAL_GRANTED) -> PRODUCTION_APPROVED
- Reject -> REJECTED (terminal)
- Cancel -> CANCELLED (terminal)

### 2. WAITING_FOR_FINAL_APPROVAL

Triggered after CREATIVE_QA. The final video output is reviewed by a human before publishing.

- Approve (APPROVAL_REQUESTED -> APPROVAL_GRANTED) -> READY
- Reject -> REJECTED (terminal)
- Cancel -> CANCELLED (terminal)

Both gates are handled by the same /approve and /reject endpoints. The server determines which gate is active based on the job's current state.

---

## Key Rule: No Direct DISPATCHING to PROVIDER_CONFIRMED

**Critical invariant**: A job must never transition directly from DISPATCHING to PROVIDER_CONFIRMED. The dispatch is an async operation -- the worker must confirm completion via a WorkerReceipt. The Dispatcher enforces this:

```python
# In dispatcher.process_receipt():
if receipt.get("status") == "COMPLETED":
    self._job_manager.transition_state(
        vpms_job_id,
        JobState.PROVIDER_CONFIRMED,
        EventType.WORKER_RECEIPT_RECEIVED,
        ...
    )
```

Direct transitions from DISPATCHING to any post-dispatch state (ASSET_GENERATION, RENDERING, etc.) are only valid within the DISPATCHING entry in the TRANSITIONS map -- and those go through the worker's async completion, not through VPMS code directly.

---

## Event Generation

Every state transition generates a job_events record. The event type is determined by the caller:

```python
# Normal state transition
EventType.STATE_TRANSITION

# Job lifecycle events
EventType.JOB_CREATED
EventType.JOB_QUEUED
EventType.JOB_CANCELLED
EventType.JOB_REJECTED
EventType.JOB_FAILED
EventType.JOB_BLOCKED
EventType.JOB_READY
EventType.JOB_PUBLISHED

# Worker events
EventType.WORKER_DISPATCHED
EventType.WORKER_RECEIPT_RECEIVED
EventType.WORKER_JOB_CANCELLED

# Approval events
EventType.APPROVAL_REQUESTED
EventType.APPROVAL_GRANTED
EventType.APPROVAL_DENIED

# Retry
EventType.RETRY_INITIATED
```

The full event history is retrievable via GET /api/v1/jobs/:jobId/events.

---

## State Machine Methods

```python
class JobStateMachine:
    def can_transition(self, from_state: JobState, to_state: JobState) -> bool:
        """Check if a transition is valid without raising."""

    def transition(self, from_state: JobState, to_state: JobState, reason=None) -> JobState:
        """Execute a state transition. Raises InvalidTransitionError if not allowed."""

    def get_allowed_transitions(self, from_state: JobState) -> Set[JobState]:
        """Return the set of valid next states."""

    def is_terminal(self, state: JobState) -> bool:
        """True if the state has no valid outgoing transitions."""

    def is_success(self, state: JobState) -> bool:
        """True if this is a successful terminal state (PUBLISHED)."""

    def is_failure(self, state: JobState) -> bool:
        """True if this is a failure terminal state (FAILED, REJECTED, CANCELLED, BLOCKED)."""

    def is_waiting_approval(self, state: JobState) -> bool:
        """True if job is at a human approval gate."""
```
""")

# ==============================================================
# FILE 5: capability-registry.md
# ==============================================================
write("capability-registry.md", """\
# VPMS Capability Registry

## Overview

The capability registry tracks two related things:
1. Which workers exist and their operational status (WorkerRegistry)
2. What capabilities each worker offers and their verification status (WorkerCapability)

The registry is the source of truth for dispatch routing -- the Dispatcher queries the registry to find eligible workers for a given capability.

Source files:
- vpms/registry/workers.py -- WorkerRegistryService
- vpms/registry/capabilities.py -- CapabilityRegistryService
- vpms/db/models.py -- WorkerRegistry and WorkerCapability ORM models

---

## WorkerRegistry Table

```sql
CREATE TABLE vpms.worker_registry (
    worker_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    base_url VARCHAR(512),
    status VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE',
    visibility VARCHAR(32) NOT NULL DEFAULT 'internal',
    health_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    last_health_check TIMESTAMPTZ,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    current_load INTEGER NOT NULL DEFAULT 0,
    avg_latency_seconds NUMERIC(10, 2),
    cost_per_job NUMERIC(10, 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);
```

### Fields

| Field | Type | Description |
|---|---|---|
| worker_id | VARCHAR(64) PK | Unique worker identifier |
| name | VARCHAR(256) | Human-readable name |
| base_url | VARCHAR(512) | Worker's HTTP endpoint (if applicable) |
| status | VARCHAR(32) | Operational status: AVAILABLE, UNAVAILABLE, etc. |
| visibility | VARCHAR(32) | "internal" or "public" -- controls API exposure |
| health_status | VARCHAR(32) | HEALTHY, UNHEALTHY, UNKNOWN |
| last_health_check | TIMESTAMPTZ | When health was last checked |
| max_concurrency | INTEGER | Max simultaneous jobs |
| current_load | INTEGER | Current job count |
| avg_latency_seconds | NUMERIC | Average job completion time |
| cost_per_job | NUMERIC | Average cost per job |
| is_active | BOOLEAN | Whether the worker is active |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| extra_data | JSONB | Arbitrary additional data |

### Seeded Workers (from migration 001)

| worker_id | name | base_url | visibility |
|---|---|---|---|
| chronos | Chronos Content Showrunner | NULL | internal |
| avatar-webinar | Avatar Webinar | NULL | internal |
| moneyprint | MoneyPrint Faceless | NULL | internal |
| vmf | Video Media Factory | NULL | internal |

The mock test worker is not in the database -- it is a standalone test adapter in vpms/adapters/mock_worker.py.

---

## WorkerCapability Table

```sql
CREATE TABLE vpms.worker_capabilities (
    id VARCHAR(32) PRIMARY KEY,
    worker_id VARCHAR(64) NOT NULL REFERENCES vpms.worker_registry(worker_id),
    capability VARCHAR(64) NOT NULL,
    code_present BOOLEAN NOT NULL DEFAULT FALSE,
    credential_verified BOOLEAN NOT NULL DEFAULT FALSE,
    integration_verified BOOLEAN NOT NULL DEFAULT FALSE,
    production_verified BOOLEAN NOT NULL DEFAULT FALSE,
    healthy BOOLEAN NOT NULL DEFAULT FALSE,
    estimated_cost NUMERIC(10, 4),
    average_latency_seconds NUMERIC(10, 2),
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    visibility VARCHAR(32) NOT NULL DEFAULT 'internal',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_data JSONB NOT NULL DEFAULT '{}'
);
```

### Fields

| Field | Type | Description |
|---|---|---|
| id | VARCHAR(32) PK | Unique capability record ID |
| worker_id | VARCHAR(64) FK | Links to worker_registry |
| capability | VARCHAR(64) | Capability name (e.g., "mock_video_render", "avatar-video") |
| code_present | BOOLEAN | Worker code exists for this capability |
| credential_verified | BOOLEAN | Credentials/API keys validated |
| integration_verified | BOOLEAN | Integration tests pass |
| production_verified | BOOLEAN | Production environment verified |
| healthy | BOOLEAN | Worker passing health checks |
| estimated_cost | NUMERIC | Estimated cost per job |
| average_latency_seconds | NUMERIC | Average latency |
| max_concurrency | INTEGER | Max simultaneous jobs for this capability |
| visibility | VARCHAR(32) | "internal" or "public" |
| is_active | BOOLEAN | Whether this capability is active |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| extra_data | JSONB | Arbitrary additional data |

### Seeded Capabilities (from migration 001)

| worker_id | capability | code_present | credential_verified | integration_verified | production_verified | healthy |
|---|---|---|---|---|---|---|
| vmf | mock_video_render | TRUE | TRUE | TRUE | FALSE | TRUE |

This is the only capability seeded in Phase 1. It is dispatchable because all four required flags are true.

---

## is_dispatchable() Logic

The is_dispatchable() method on WorkerCapability is the canonical dispatch eligibility check:

```python
def is_dispatchable(self) -> bool:
    """Can this capability accept normal production dispatch?"""
    return (
        self.code_present
        and self.credential_verified
        and self.integration_verified
        and self.healthy
    )
```

**Key point**: production_verified is NOT required for Phase 1 dispatch eligibility. This is intentional -- it allows workers to be wired and tested in production-like environments before full production verification.

### Dispatch Refusal

When a capability is not dispatchable, the Dispatcher raises:

```
ValueError: Capability mock_video_render on worker vmf is not dispatchable
(code_present=True, credential_verified=True, integration_verified=True, healthy=True)
```

This happens when calling Dispatcher.dispatch() with a non-dispatchable capability.

---

## find_dispatchable() Query Example

The CapabilityRepository provides a find_dispatchable() method that returns all capabilities meeting the dispatch criteria:

```python
# In vpms/db/repositories/worker_repository.py
def find_dispatchable(self, capability: str, visibility: str = "internal") -> list[WorkerCapability]:
    return self._session.query(WorkerCapability).filter(
        WorkerCapability.capability == capability,
        WorkerCapability.visibility == visibility,
        WorkerCapability.is_active == True,
        WorkerCapability.code_present == True,
        WorkerCapability.credential_verified == True,
        WorkerCapability.integration_verified == True,
        WorkerCapability.healthy == True,
    ).all()
```

This is the query used by CapabilityRegistryService.find_dispatchable(), which the Dispatcher would call to select a worker for a job (Phase 2).

### Example: Finding all dispatchable mock_video_render capabilities

```python
capabilities = capability_repo.find_dispatchable("mock_video_render", "internal")
# Returns list of WorkerCapability records where:
#   capability == "mock_video_render"
#   visibility == "internal"
#   is_active == True
#   code_present == True
#   credential_verified == True
#   integration_verified == True
#   healthy == True
```

---

## Verification Flag Update Mechanism

Verification flags are managed via CapabilityRegistryService.update_verification():

```python
def update_verification(
    self,
    worker_id: str,
    capability: str,
    code_present: Optional[bool] = None,
    credential_verified: Optional[bool] = None,
    integration_verified: Optional[bool] = None,
    production_verified: Optional[bool] = None,
    healthy: Optional[bool] = None,
) -> Optional[WorkerCapability]:
    """Update verification flags for a capability."""
```

This method upserts the capability record (creates if it doesn't exist, updates if it does), setting only the flags that are not None.

### Example: Marking a capability as integration-verified

```python
cap_service = CapabilityRegistryService(db_session)
cap = cap_service.update_verification(
    worker_id="vmf",
    capability="mock_video_render",
    integration_verified=True,
)
# Updates the record: integration_verified = True
# All other fields unchanged
```

### Workflow for Adding a New Worker (Phase 2)

1. Operator registers worker in worker_registry (or seeds via migration)
2. Operator creates capability record with all flags False
3. As each verification step passes, operator calls update_verification() to set flags
4. When is_dispatchable() returns True, the worker can accept production dispatch

---

## Initial Mock Worker Capability

The mock worker is seeded with a single capability for Phase 1 testing:

| Field | Value |
|---|---|
| worker_id | vmf |
| capability | mock_video_render |
| code_present | TRUE |
| credential_verified | TRUE |
| integration_verified | TRUE |
| production_verified | FALSE |
| healthy | TRUE |
| visibility | internal |
| is_active | TRUE |

This capability is dispatchable in Phase 1 because is_dispatchable() does not require production_verified. It allows the full golden path to be tested (dispatch -> receipt -> artifact) without real worker credentials.
""")

# ==============================================================
# FILE 6: decisions.md
# ==============================================================
write("decisions.md", """\
# VPMS Architecture Decision Records

## ADR-001: PostgreSQL Schema (Not New DB Server)

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS needs persistent storage for jobs, events, workers, and capabilities. The infrastructure already includes a Supabase PostgreSQL 17.6 instance.

### Decision

VPMS uses the **existing Supabase PostgreSQL 17.6** instance. All VPMS tables are created in a dedicated vpms schema within the existing database.

### Rationale

- No new database infrastructure to operate or pay for
- Supabase PostgreSQL is already monitored, backed up, and maintained
- Schema isolation (vpms prefix) prevents naming collisions with existing tables
- Existing migrations and backup tooling applies
- PostgreSQL JSONB support is ideal for flexible payload storage (job content, event metadata)

### Consequences

- VPMS is tightly coupled to the Supabase PostgreSQL instance
- If the Supabase instance is unavailable, VPMS is unavailable
- All VPMS migrations must run against the shared database

---

## ADR-002: SQLAlchemy 2.0 ORM (Not Raw SQL)

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS is a Python project built on the same stack as OpenMontage. It needs a database access layer.

### Decision

VPMS uses **SQLAlchemy 2.0 ORM** with async support, not raw SQL strings.

### Rationale

- Matches OpenMontage's existing Python stack (less context switching)
- SQLAlchemy 2.0 provides type-safe query building, migration tools (Alembic-ready), and session management
- ORM models serve as self-documenting schema contracts
- SQLAlchemy's SQL expression language can still be used for complex queries
- Pydantic models (for API schemas) can be validated against ORM models

### Consequences

- ORM model definitions in vpms/db/models.py must stay in sync with migrations
- Complex queries may require sqlalchemy.text() for raw SQL
- Session management must be handled explicitly (FastAPI Depends(get_db))

---

## ADR-003: FastAPI for API Gateway

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS needs a REST API for job management, worker queries, and approval actions.

### Decision

VPMS uses **FastAPI** as the API framework.

### Rationale

- Already a dependency via the Backlot ecosystem
- Native Pydantic v2 integration for request/response validation
- Automatic OpenAPI documentation at /docs
- ASGI-based (async-capable) for future worker adapter calls
- Dependency injection system (Depends()) for database sessions and auth
- APIRouter for clean endpoint organization

### Consequences

- All endpoints defined in vpms/api/routes.py
- Schemas defined in vpms/api/schemas.py (Pydantic models)
- Running on port 8090 (configured in vpms/main.py)

---

## ADR-004: State Machine as Canonical Authority

**Date**: 2025-01-15
**Status**: Accepted

### Context

Jobs in VPMS follow a complex lifecycle with many states and transition rules. Without a central authority, ad-hoc state mutations would produce inconsistent job states.

### Decision

All job state transitions go through JobManager.transition_state(), which calls JobStateMachine.transition(). Invalid transitions raise InvalidTransitionError.

### Rationale

- Single source of truth: the TRANSITIONS dict in state_machine.py
- Impossible to accidentally skip states or make invalid jumps
- Every transition produces a job_events record automatically
- The state machine is testable in isolation (no DB needed)
- Invalid transitions fail fast with a clear error message

### Consequences

- No code may directly mutate jobs.status -- all mutations must go through the state machine
- The API returns HTTP 400 for invalid transitions (caught as generic Exception in routes)
- Adding new states or transitions requires updating state_machine.py in one place

---

## ADR-005: Event Ledger is Append-Only

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS needs a complete, immutable audit trail of everything that happens to each job.

### Decision

The vpms.job_events table is **append-only**. Events are never updated or deleted. The EventLedger.append() method is the only write path.

### Rationale

- True audit trail: no event can be erased or modified
- Enables replay: the full history can be reconstructed from events
- Debugging: event history shows exactly what happened and when
- Compliance: immutable logs are required for production video pipelines
- Simplicity: no update/delete logic needed for events

### Consequences

- Event history is always queryable via GET /api/v1/jobs/:jobId/events
- Events cannot be corrected -- if a bad event is written, it stays (but a compensating event can be added)
- No event deletion, even on job cancellation or failure

---

## ADR-006: Worker Adapter Pattern for External Systems

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS must integrate with external production workers (Chronos, Avatar Webinar, VMF, MoneyPrint). These are existing services with their own APIs and authentication.

### Decision

VPMS communicates with workers through **adapter classes** that implement BaseWorkerAdapter. Workers are never embedded in VPMS code.

### Rationale

- Workers are external, independently deployed services
- Each worker has a different API, authentication, and error handling
- Adapters isolate this complexity from the core Dispatcher
- Adapters can be tested independently with mock responses
- New workers can be added without modifying core VPMS code
- The BaseWorkerAdapter ABC enforces a consistent interface

### Consequences

- All workers implement the same 6-method interface
- Each adapter handles its own HTTP client, auth, and error mapping
- Phase 1 ships with a mock adapter for testing without real workers
- Phase 2 requires implementing real adapters for Chronos, Avatar Webinar, VMF, MoneyPrint

---

## ADR-007: Mock Worker for Phase 1

**Date**: 2025-01-15
**Status**: Accepted

### Context

Phase 1 needs to prove the full VPMS dispatch -> receipt -> artifact flow without depending on real external workers (which are Phase 2).

### Decision

VPMS ships with a **mock test worker** (vpms/adapters/mock_worker.py) that implements the production worker contract locally.

### Rationale

- Full golden path can be tested without external dependencies
- Mock worker can simulate failure modes (timeout, transient error, permanent error)
- Allows deterministic integration testing in CI/CD
- Proves the dispatcher, receipt processing, and artifact registration work end-to-end

### Consequences

- Mock worker is a standalone FastAPI app running on port 8091
- It is NOT for production use
- Phase 2 real worker adapters replace the mock
- The mock worker's mock_video_render capability is the seeded capability in worker_capabilities

---

## ADR-008: Idempotency via source_app + idempotency_key Composite

**Date**: 2025-01-15
**Status**: Accepted

### Context

Source applications may retry job creation requests due to network timeouts or client-side retries. Without idempotency, duplicate jobs would be created.

### Decision

Job creation endpoints accept an optional idempotency_key field. When provided with a source_app, the combination (source_app, idempotency_key) is unique. If a matching job already exists, the existing job is returned instead of creating a new one.

### Rationale

- Prevents duplicate jobs from retry storms
- Composite unique index at the DB level enforces uniqueness
- Idempotent responses return HTTP 201 (same as new jobs) so clients don't need special handling
- The created flag in JobManager.create_content_job() return value distinguishes new from existing jobs
- GET /jobs/:jobId/events shows an IDEMPOTENT_REQUEST event for idempotent matches

### Consequences

- idempotency_key is optional -- callers that don't provide it can still create jobs
- Keys should be stable and unique per logical operation (e.g., "episode-001-2025-01-15")
- Keys should be stored/managed by the source application
- No automatic key expiration in Phase 1 (future: TTL-based cleanup)
- The IX_JOBS_SOURCE_IDEMPOTENCY composite index enforces uniqueness

---

## ADR-009: AGPLv3 Fork -- License and Attribution Preserved

**Date**: 2025-01-15
**Status**: Accepted

### Context

VPMS is a fork of OpenMontage, which is released under GNU AGPL v3.0.

### Decision

VPMS retains the **AGPLv3 license** and preserves all attribution requirements. The LICENSE file and copyright notices are preserved in the vpms/__init__.py package header.

### Rationale

- AGPLv3 is a strong copyleft license -- derivative works must also be AGPLv3
- VPMS is a derivative work of OpenMontage (substantial code reuse and architectural influence)
- Attribution is a minimal requirement that costs nothing
- Preserving the license maintains legal compliance and respects the original author

### Consequences

- Any third party receiving VPMS must receive the source under AGPLv3
- Modified versions must be clearly marked as modified
- The license text is included in the repository
- vpms/__init__.py includes the copyright notice and license reference
""")

# ==============================================================
# FILE 7: test-evidence.md
# ==============================================================
write("test-evidence.md", """\
# VPMS Phase 1 Test Evidence

## Overview

This document describes the test evidence requirements for VPMS Phase 1 acceptance. Each item represents a capability that must be demonstrated with concrete test results. Test files are located in:

- Unit tests: vpms/tests/unit/
- Integration tests: vpms/tests/integration/

Run all tests with:
```bash
cd /opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo
python -m pytest vpms/tests/ -v
```

---

## 1. API Job Creation -- POST /content/jobs returns job_id immediately

**What to demonstrate**: Creating a content job via POST /api/v1/content/jobs returns a job_id in the response body with HTTP 201.

**Test files**: vpms/tests/integration/test_api.py -- test_create_content_job

**Expected behavior**:
```json
// POST /api/v1/content/jobs
// Headers: X-Source-App: vpms-internal
// Body: { "source_app": "vpms-internal", "request_type": "test", "content": {} }

{
  "job_id": "vpms_abc123def456",
  "status": "QUEUED",
  "created_at": "2025-01-15T10:30:00Z"
}
// HTTP 201
```

**Evidence required**: pytest output showing HTTP 201 and a non-null job_id.

---

## 2. Idempotency -- Same idempotency_key returns same job

**What to demonstrate**: Sending the same idempotency_key twice from the same source_app returns the same job ID both times. No duplicate is created.

**Test files**: vpms/tests/integration/test_api.py -- test_idempotent_content_job

**Expected behavior**:
```python
# First call
job1, created1 = manager.create_content_job(..., idempotency_key="test-key-001", ...)
assert created1 == True
assert job1.id.startswith("vpms_")

# Second call with same key
job2, created2 = manager.create_content_job(..., idempotency_key="test-key-001", ...)
assert created2 == False
assert job2.id == job1.id  # Same job
```

**Evidence required**: pytest output showing second call returns created=False and same job ID.

---

## 3. Persistent DB Job -- Job survives process restart

**What to demonstrate**: A job created via the API is persisted in the PostgreSQL vpms.jobs table and survives the FastAPI process being restarted.

**Test files**: vpms/tests/integration/test_api.py -- test_job_persistence

**Method**:
1. Create a job via POST /api/v1/content/jobs
2. Stop the FastAPI process
3. Start a new FastAPI process
4. Query GET /api/v1/jobs/:jobId
5. Assert the job exists and has correct status

**Evidence required**: Job returned after restart with same job_id and status.

---

## 4. Event History -- GET /jobs/:id/events shows full transition log

**What to demonstrate**: Every state transition produces an event in vpms.job_events. The full history is queryable.

**Test files**:
- vpms/tests/unit/test_event_ledger.py -- test_append_and_retrieve
- vpms/tests/integration/test_api.py -- test_get_job_events

**Expected behavior**: After job creation, at least 2 events are returned (JOB_CREATED and JOB_QUEUED), each with event_type, previous_state, new_state, timestamp, and extra_data.

**Evidence required**: At least 2 events returned in chronological order.

---

## 5. Worker Registry -- GET /workers returns seeded workers

**What to demonstrate**: GET /api/v1/workers returns the 4 workers seeded by migration 001: chronos, avatar-webinar, moneyprint, vmf.

**Test files**: vpms/tests/integration/test_api.py -- test_list_workers

**Expected behavior**:
```json
// GET /api/v1/workers
{
  "workers": [
    { "worker_id": "chronos", "name": "Chronos Content Showrunner", ... },
    { "worker_id": "avatar-webinar", "name": "Avatar Webinar", ... },
    { "worker_id": "moneyprint", "name": "MoneyPrint Faceless", ... },
    { "worker_id": "vmf", "name": "Video Media Factory", ... }
  ],
  "total": 4
}
```

**Evidence required**: Response with total=4 and all 4 worker IDs present.

---

## 6. Capability Verification -- GET /capabilities shows all verification flags

**What to demonstrate**: GET /api/v1/capabilities returns the seeded capability with all 5 verification flags visible.

**Test files**: vpms/tests/integration/test_api.py -- test_list_capabilities

**Expected behavior**:
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
      "is_active": true
    }
  ],
  "total": 1
}
```

**Evidence required**: Response showing all 5 verification flags with correct values.

---

## 7. Mock Worker Dispatch -- Dispatcher refuses non-dispatchable capabilities

**What to demonstrate**: Calling Dispatcher.dispatch() with a capability where is_dispatchable() returns False raises ValueError.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_dispatcher_refuses_non_dispatchable

**Method**: Create a capability record where one of the required flags (code_present, credential_verified, integration_verified, healthy) is False. Attempt dispatch. Assert ValueError is raised.

**Expected behavior**:
```python
# Set integration_verified = False on a capability
cap = create_capability(worker_id="vmf", capability="mock_video_render",
                         code_present=True, credential_verified=True,
                         integration_verified=False, healthy=True)
# is_dispatchable() returns False
assert cap.is_dispatchable() == False

# Dispatcher raises
dispatcher = Dispatcher(db_session)
with pytest.raises(ValueError, match="is not dispatchable"):
    dispatcher.dispatch(vpms_job_id="vpms_test123", worker_id="vmf",
                        capability="mock_video_render", job_request={})
```

**Evidence required**: pytest output showing ValueError raised with "is not dispatchable" message.

---

## 8. Worker Receipt -- Receipt transitions job to PROVIDER_CONFIRMED

**What to demonstrate**: Processing a COMPLETED worker receipt via Dispatcher.process_receipt() transitions the VPMS job from its current state to PROVIDER_CONFIRMED.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_dispatcher_process_completed_receipt

**Method**:
1. Create a job and transition it to DISPATCHING
2. Call Dispatcher.process_receipt() with status="COMPLETED"
3. Assert job status is now PROVIDER_CONFIRMED

**Expected behavior**:
```python
job = create_job_in_state(db_session, JobState.DISPATCHING)
receipt = {
    "status": "COMPLETED",
    "provider": "mock-provider",
    "artifacts": [{"type": "video", "name": "output.mp4", ...}],
    "actual_cost": 0.05,
}
dispatcher = Dispatcher(db_session)
dispatcher.process_receipt(worker_job_id="wrkj_test123", receipt=receipt)
# job.status == JobState.PROVIDER_CONFIRMED.value
```

**Evidence required**: Job state transitions to PROVIDER_CONFIRMED after receipt processing.

---

## 9. Artifact Registration -- Artifacts appear in GET /jobs/:id/artifacts

**What to demonstrate**: Artifacts in a worker receipt are persisted to vpms.artifacts and queryable via GET /api/v1/jobs/:jobId/artifacts.

**Test files**:
- vpms/tests/integration/test_api.py -- test_get_job_artifacts
- vpms/tests/unit/test_state_machine.py -- test_artifact_registration

**Expected behavior**:
```json
// GET /api/v1/jobs/vpms_abc123/artifacts
{
  "job_id": "vpms_abc123",
  "artifacts": [
    {
      "id": "art_xyz789",
      "job_id": "vpms_abc123",
      "artifact_type": "video",
      "name": "output.mp4",
      "url": "https://storage.example.com/output.mp4",
      "file_size_bytes": 104857600,
      "mime_type": "video/mp4",
      "duration_seconds": 600.0,
      "width": 1920,
      "height": 1080
    }
  ],
  "total": 1
}
```

**Evidence required**: Artifact list with at least one artifact after processing a COMPLETED receipt.

---

## 10. Human Approval -- Job advances through approval gate

**What to demonstrate**: A job at WAITING_FOR_PRODUCTION_APPROVAL transitions to PRODUCTION_APPROVED after calling POST /api/v1/jobs/:jobId/approve.

**Test files**:
- vpms/tests/unit/test_state_machine.py -- test_approve_at_production_gate
- vpms/tests/integration/test_api.py -- test_approve_job

**Method**:
1. Create a job and transition it to WAITING_FOR_PRODUCTION_APPROVAL
2. Call POST /api/v1/jobs/:jobId/approve with decision=APPROVED
3. Assert job status is now PRODUCTION_APPROVED
4. Assert an approval record was created

**Expected behavior**:
```python
# Job at WAITING_FOR_PRODUCTION_APPROVAL
job, approval = manager.approve_job(
    job_id="vpms_test123",
    approval_type="PRODUCTION",
    approved_by="supervisor@example.com",
    notes="Looks good",
)
assert job.status == JobState.PRODUCTION_APPROVED.value
assert approval.decision == "APPROVED"
assert approval.approval_type == "PRODUCTION"
```

**Evidence required**: Job state changes to PRODUCTION_APPROVED, approval record exists.

---

## 11. Valid READY State -- Job reaches READY after approval

**What to demonstrate**: A job at WAITING_FOR_FINAL_APPROVAL transitions to READY after final approval.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_approve_at_final_gate

**Method**:
1. Create a job and transition it through the full pipeline to WAITING_FOR_FINAL_APPROVAL
2. Call POST /api/v1/jobs/:jobId/approve
3. Assert job status is now READY

**Evidence required**: Job state changes to READY after final approval.

---

## 12. Invalid Transition Rejection -- InvalidTransitionError raised

**What to demonstrate**: Attempting an invalid state transition raises InvalidTransitionError.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_invalid_transition_raises, test_state_machine_invalid_transitions

**Expected behavior**:
```python
from vpms.core.state_machine import JobStateMachine, InvalidTransitionError

sm = JobStateMachine()
with pytest.raises(InvalidTransitionError) as exc_info:
    sm.transition(JobState.CREATED, JobState.PUBLISHED)  # Invalid: CREATED can't go directly to PUBLISHED

assert exc_info.value.from_state == JobState.CREATED
assert exc_info.value.to_state == JobState.PUBLISHED
assert "Invalid state transition" in str(exc_info.value)
```

**Evidence required**: pytest output showing InvalidTransitionError raised with correct from/to states.

---

## 13. Process Restart Recovery -- Job state persists after restart

**What to demonstrate**: Job state is stored in PostgreSQL and survives a process restart.

**Test files**: vpms/tests/integration/test_api.py -- test_job_state_persists_after_restart

**Method**:
1. Create a job and transition it to a non-initial state (e.g., PLANNING)
2. Simulate process restart (close and reopen DB session)
3. Query the job
4. Assert status is still PLANNING

**Evidence required**: Job status unchanged after session reset.

---

## 14. Timeout Handling -- Transient errors go to RETRYABLE_FAILURE

**What to demonstrate**: Worker errors containing transient keywords (timeout, temporary, unavailable, rate limit, connection, network) cause the job to enter RETRYABLE_FAILURE, not FAILED.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_dispatcher_process_transient_failure

**Method**:
1. Dispatch a job
2. Process a receipt with status=FAILED and transient error messages
3. Assert job state is RETRYABLE_FAILURE

```python
receipt = {
    "status": "FAILED",
    "errors": ["Connection timeout after 30s", "Worker temporarily unavailable"]
}
dispatcher.process_receipt(worker_job_id="wrkj_test", receipt=receipt)
# job.status == JobState.RETRYABLE_FAILURE.value
```

**Evidence required**: Job transitions to RETRYABLE_FAILURE with transient errors.

---

## 15. Retry Handling -- RETRYABLE_FAILURE can re-queue

**What to demonstrate**: A job in RETRYABLE_FAILURE can be re-queued or re-dispatched via valid transitions.

**Test files**: vpms/tests/unit/test_state_machine.py -- test_retryable_failure_transitions

**Valid transitions from RETRYABLE_FAILURE**:
- -> QUEUED (re-queue)
- -> DISPATCHING (re-dispatch)
- -> FAILED (escalate)
- -> BLOCKED

**Evidence required**: State machine accepts RETRYABLE_FAILURE -> QUEUED and RETRYABLE_FAILURE -> DISPATCHING transitions.

---

## 16. Automated Test Results -- pytest output showing all tests pass

**What to demonstrate**: All unit and integration tests pass in a clean environment.

**Test files**:
- vpms/tests/unit/test_state_machine.py
- vpms/tests/unit/test_event_ledger.py
- vpms/tests/unit/test_schemas.py
- vpms/tests/integration/test_api.py

**Run command**:
```bash
cd /opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo
python -m pytest vpms/tests/ -v --tb=short
```

**Evidence required**: pytest summary output showing all tests passed, 0 failures, 0 errors.

### Test File Locations

```
vpms/tests/
|-- __init__.py
|-- unit/
|   |-- __init__.py
|   |-- test_state_machine.py   # State machine logic, transitions, InvalidTransitionError
|   |-- test_event_ledger.py    # EventLedger append, retrieval, immutability
|   +-- test_schemas.py         # Pydantic schema validation
|-- integration/
    |-- __init__.py
    +-- test_api.py             # All 13 API endpoints, full request/response cycle
```

---

## Running the Full Test Suite

```bash
cd /opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo

# Unit tests only (no DB required for state machine tests)
python -m pytest vpms/tests/unit/ -v

# Integration tests (requires database)
python -m pytest vpms/tests/integration/ -v

# All tests
python -m pytest vpms/tests/ -v

# With coverage
python -m pytest vpms/tests/ -v --cov=vpms --cov-report=term-missing
```

## Minimum Passing Evidence

For Phase 1 acceptance, all 16 test evidence items above must have supporting pytest output. The key evidence items are:

1. State machine tests pass (all valid/invalid transitions)
2. Event ledger tests pass (append-only, retrieval)
3. API integration tests pass (all 13 endpoints)
4. Mock worker dispatch/receipt flow works end-to-end
5. Idempotency test passes
6. Human approval gate tests pass
""")

print("\nAll 7 documentation files written successfully.")
