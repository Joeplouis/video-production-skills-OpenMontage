# VPMS Design Decisions — Phase 1 + Phase 2

## Overview

This log records major design decisions made during Phase 1 implementation, including the rationale and trade-offs considered.

---

## 1. SQLAlchemy 2.0 ORM, not raw SQL

**Decision**: Use SQLAlchemy 2.0 ORM (`DeclarativeBase`, `Mapped`, `mapped_column`) with PostgreSQL.

**Reason**: Provides type safety, migration tooling compatibility, and reduces boilerplate vs raw SQL. The existing OpenMontage repo already uses Python.

**Evidence**: `vpms/db/models.py` uses SQLAlchemy 2.0 ORM style.

---

## 2. Shared MetaData for schema inheritance

**Decision**: Use `MetaData(schema="vpms")` shared across all model `Base` classes, rather than per-model `__table_args__ = {"schema": "vpms"}`.

**Reason**: SQLAlchemy 2.0 `DeclarativeBase` interprets dicts in `__table_args__` as dialect-level kwargs (e.g., `{"schema": "vpms"}` is rejected as an unnamed argument). Using a shared `MetaData` object at the module level, assigned to `Base.metadata`, is the idiomatic SQLAlchemy 2.0 pattern.

**Evidence**: `vpms/db/models.py` — `vpms_metadata = MetaData(schema="vpms")` assigned to `Base.metadata`.

---

## 3. One canonical state management service

**Decision**: All job status mutations go through `JobManager.transition_state()`. No code may mutate `job.status` directly.

**Reason**: Ensures every transition is validated against the state machine, every transition emits an event, and invalid transitions fail loudly rather than silently corrupting state.

**Evidence**: `vpms/core/job_manager.py:transition_state()` is the only method that calls `_job_repo.update_status()`. The API routes go through `JobManager` for all mutations.

---

## 4. Event ledger is append-only

**Decision**: `job_events` table records are never updated or deleted. The ledger is an immutable audit trail.

**Reason**: Auditability. Every state change is preserved. No risk of losing history.

**Evidence**: `vpms/core/event_ledger.py` — `EventLedger.append()` writes events; no update or delete methods exist.

---

## 5. Worker receipt required before COMPLETE state

**Decision**: Workers must send a `WorkerReceipt` before a job can transition to `PROVIDER_CONFIRMED` or beyond. `DISPATCHING → READY` is an invalid transition.

**Reason**: Prevents VPMS from claiming completion when only the API request was accepted, not the actual work done.

**Evidence**: `vpms/core/dispatcher.py:process_receipt()` enforces this. `test_state_machine.py` has `test_dispatching_to_complete_is_invalid`.

---

## 6. No new database server

**Decision**: Use existing PostgreSQL/Supabase infrastructure. VPMS uses its own `vpms` schema.

**Reason**: Avoids operational overhead. The `affiliates_autopilot` database already runs on port 5435. VPMS uses `vpms.*` tables in the same database.

**Evidence**: `vpms/db/session.py` — `DATABASE_URL` defaults to `postgresql://empire:empire_pass_2026@localhost:5435/affiliates_autopilot`.

---

## 7. Source app auth via X-Source-App header

**Decision**: Source applications authenticate via `X-Source-App` header, validated against `vpms.source_apps`.

**Reason**: Simple, auditable. Does not require full OAuth or API key management for Phase 1. Real auth (OAuth, service tokens) is Phase 2.

**Evidence**: `vpms/api/routes.py:require_source_app()` — validates header against `source_apps` table.

---

## 8. Mock worker for Phase 1 testing

**Decision**: Build a mock production worker in Phase 1 instead of connecting real workers.

**Reason**: Proves the full VPMS flow (job creation → dispatch → receipt → artifact → QA → approval → READY) without depending on external worker availability. The mock supports all failure modes (success, transient failure, permanent failure, timeout, duplicate callback, restart).

**Evidence**: `vpms/adapters/mock_worker/worker.py` — FastAPI app on port 8091 with all 6 endpoints.

---

## 9. No new queue server

**Decision**: Job state is persisted in PostgreSQL. No Redis or RabbitMQ for Phase 1.

**Reason**: Simplicity. PostgreSQL is already available. Restart-safety is achieved via DB persistence, not a message queue. If a job is `DISPATCHING` when VPMS restarts, it stays `DISPATCHING` — the worker is the source of truth.

**Evidence**: All job state is in `vpms.jobs`. No queue tables or queue dependencies.

---

## 10. Adapters for worker integration, not direct calls

**Decision**: VPMS communicates with workers through adapter classes (`BaseWorkerAdapter`), not direct HTTP calls in core logic.

**Reason**: Isolates VPMS from worker API changes. Each worker can have a different native API. The adapter pattern means Phase 2 worker wiring doesn't require core code changes.

**Evidence**: `vpms/adapters/base.py` defines `BaseWorkerAdapter`. `vpms/adapters/mock_worker/worker.py` implements it. Real adapters go in `vpms/adapters/chronos/`, `vpms/adapters/avatar_webinar/`, `vpms/adapters/vmf/`.

---

## 11. Pydantic for API validation

**Decision**: Use Pydantic v2 for all API request/response schemas.

**Reason**: FastAPI's native integration, automatic OpenAPI docs, runtime validation with clear error messages.

**Evidence**: `vpms/api/schemas.py` — all request/response models use Pydantic `BaseModel`.

---

## 12. OpenMontage fork preserved as-is

**Decision**: Do not modify OpenMontage code. VPMS is a new `vpms/` package that sits alongside the OpenMontage tools.

**Reason**: OpenMontage tools (167 tool files) are the worker capabilities VPMS dispatches to. Changing them risks breaking existing OpenMontage users. VPMS manages OpenMontage; it does not replace it.

**Evidence**: `vpms/` is a separate top-level package. OpenMontage code under `lib/`, `tools/`, `skills/`, etc. is unmodified.

---

## 13. AGPL v3 license preserved

**Decision**: VPMS fork preserves the GNU AGPL v3.0 license from OpenMontage.

**Reason**: Required by the OpenMontage license. VPMS adds attribution but does not remove upstream copyright.

**Evidence**: `vpms/__init__.py` — `__version__`, `__product_name__`, license note. Repository `LICENSE` file unchanged.

---

## Phase 2 Decisions

## 14. Chronos adapter is file-based, not HTTP

**Decision**: Chronos has no HTTP API. VPMS communicates via a file queue (`vpms_queue.json`) which Chronos reads on its next cron run.

**Reason**: Chronos is a cron script (`run_chronos.sh`), not a long-running HTTP service. The file-based queue is the correct integration point. This avoids building an unnecessary HTTP wrapper around a batch job.

**Evidence**: `vpms/adapters/chronos/worker.py` — `_save_queue()` writes JSON to `vpms_queue.json`. `dispatch()` returns a `worker_job_id` of form `chronos_queue_<index>` for polling.

**Trade-off**: Chronos jobs are not immediately picked up. VPMS must poll `series_state.json` for completion. This is acceptable for Phase 2 (no strict SLA).

---

## 15. Avatar Webinar auth via JWT minting

**Decision**: VPMS mints short-lived (5-min) HS256 JWTs using the Supabase service-role key, instead of storing a permanent user token.

**Reason**: Avatar Webinar's `requireAuth` middleware calls `supabase.auth.getUser(token)` which validates against Supabase's JWT secret. VPMS uses the service-role key as the HMAC secret to produce tokens that Supabase will accept. Tokens are cached and refreshed automatically.

**Evidence**: `vpms/adapters/avatar_webinar/worker.py` — `_mint_vpms_jwt()`. Requires `VPMS_AVATAR_WEBINAR_SUPABASE_URL` and `VPMS_AVATAR_WEBINAR_SERVICE_KEY` env vars.

**Alternative considered**: Store a permanent VPMS user token in Supabase and rotate it manually. Rejected — too much operational overhead.

---

## 16. VMF auth via JWT Bearer token env var

**Decision**: VMF uses `VPMS_VMF_JWT_TOKEN` env var for Bearer auth. Falls back gracefully if not set.

**Reason**: VMF's `requireAuth` middleware accepts JWT Bearer tokens. VPMS can use a service token without needing to mint JWTs. Falls back to anonymous (public) access for health/capabilities checks — works without credentials.

**Evidence**: `vpms/adapters/vmf/worker.py` — `_get_auth_token()` reads `VPMS_VMF_JWT_TOKEN`.

---

## 17. Golden Path is an ergonomic convenience, not the primary path

**Decision**: `ProductionDirector.run_golden_path()` is a synchronous wrapper. Production use should call individual dispatch methods and poll via receipts API.

**Reason**: Synchronous wrappers hide failures and don't scale to async workers. The receipts API (`POST /workers/{id}/receipt`) is the canonical async callback mechanism. The director is for scripting and simple workflows only.

**Evidence**: `vpms/api/routes_golden_path.py` — `start_golden_path()` calls `director.run_golden_path()`. Worker callbacks use `worker_receipt_callback()`.

---

## 18. One worker at a time for Phase 2 integration

**Decision**: Workers are connected one at a time (Chronos, then Avatar Webinar, then VMF), not simultaneously.

**Reason**: Parallel integration makes failure attribution ambiguous. Sequential integration allows each worker's adapter to be verified in isolation before adding the next.

**Evidence**: Per PRD Section 53: "Do not connect every system simultaneously." The adapters were built sequentially: VMF → Avatar Webinar → Chronos.

---

## 19. Production Director does not own the state machine

**Decision**: `ProductionDirector` dispatches to workers and processes receipts, but does NOT directly mutate job state. It delegates to `JobManager.transition_state()`.

**Reason**: Keeps state machine ownership in one place. Ensures every state transition is validated, events are emitted, and invalid transitions fail loudly.

**Evidence**: `vpms/core/production_director.py` — all state transitions go through `JobManager` (via `self._job_manager`). The Director only calls `JobManager.transition_state()`, never `_job_repo.update_status()` directly.

---

## 20. `vpms_queue.json` for Chronos integration

**Decision**: VPMS writes a separate queue file (`vpms_queue.json`), not the existing `series_state.json` that Chronos owns.

**Reason**: Chronos owns `series_state.json` and may rewrite it on each run. A separate VPMS queue avoids write conflicts. Chronos can be extended later to read `vpms_queue.json` alongside its own state.

**Evidence**: `vpms/adapters/chronos/worker.py` — `_queue_file = vpms_queue.json` (separate from `STATE_FILE = series_state.json`).

---

## 21. Worker receipts stored in DB, not just in memory

**Decision**: Every worker dispatch creates a `WorkerJob` record in `vpms.worker_jobs`. Every receipt creates artifact records.

**Reason**: Restart-safety. If VPMS restarts mid-production, the worker job records are preserved. VPMS can poll workers to reconcile state on restart.

**Evidence**: `vpms/core/dispatcher.py:dispatch()` creates `WorkerJob` record. `process_receipt()` updates it. `vpms/db/models.py:WorkerJob` has `worker_job_id`, `status`, `provider`, `actual_cost`, `errors` fields.
