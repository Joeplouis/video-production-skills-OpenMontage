# VPMS Design Decisions — Phase 1

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
