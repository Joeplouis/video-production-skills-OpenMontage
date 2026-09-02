# Current State Audit — OpenMontage Fork (pre-VPMS)

**Date:** 2026-08-31
**Auditor:** Hermes (Architecture Controller role, documentation only)
**Target:** `Joeplouis/video-production-skills-OpenMontage` (cloned to `/opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo/`)
**Purpose:** Baseline audit required by the VPMS Phase 1 execution prompt BEFORE any implementation. This document records what is reusable, what conflicts with the VPMS PRD, and what is missing. No code was changed.

---

## 1. Repository Structure

```
repo/  (OpenMontage fork, 2131 files, 164MB)
├── AGENT_GUIDE.md            # 48KB — full agent operating guide / contract
├── PROJECT_CONTEXT.md        # shared project context (architecture source of truth)
├── config.yaml               # global config: llm, budget, checkpoint, output, paths
├── .env.example              # provider keys (FAL, MiniMax, Replicate, Kling, Google, ...)
├── LICENSE                   # GNU AGPL v3.0
├── pipeline_defs/            # 13 YAML pipeline manifests (talking-head, animated-explainer, ...)
├── lib/                      # Python core runtime (no orchestrator)
│   ├── checkpoint.py         # pipeline state persistence (JSON checkpoints)
│   ├── events.py             # Backlot event stream (append-only tool-event log)
│   ├── pipeline_loader.py    # YAML manifest loader + JSON-schema validation
│   ├── config_model.py       # Pydantic config loader
│   ├── cost_tracker.py       # budget governance (estimate → reserve → reconcile)
│   ├── media_profiles.py     # platform render profiles
│   ├── env_loader.py         # .env variable management
│   └── providers/            # reserved (mostly empty)
├── tools/                    # 167 Python tool files
│   ├── base_tool.py          # ToolContract ABC (name, tier, capability, provider, runtime, stability)
│   ├── tool_registry.py      # auto-discovery singleton registry
│   ├── cost_tracker.py       # budget governance
│   ├── analysis/ audio/ avatar/ capture/ character/ enhancement/ graphics/
│   ├── publishers/           # reserved (empty)
│   ├── subtitle/ video/     # 13 video gen providers, composition, stitching
│   └── _comfyui/ _kling/     # provider-specific adapters
├── skills/                   # 157 markdown skill files (Layer 2: project conventions)
│   ├── core/ creative/ meta/ pipelines/
├── .agents/skills/           # Layer 3: external technology skills (FFmpeg, HyperFrames, ...)
├── schemas/                  # JSON Schema: artifacts (11), checkpoints, pipelines, styles, tools
├── styles/                   # visual style playbooks (YAML)
├── remotion-composer/        # Node.js/React Remotion renderer
├── backlot/                  # FastAPI "living storyboard" board server (SSE, media)
├── ink-theater/              # JS animation runtime (ink-puppet.js, mocap)
├── tests/                    # contract tests, QA integration tests, eval harness
├── docs/                     # ARCHITECTURE.md, PROVIDERS.md, stage-gates, ...
└── scripts/                  # smoke tests, backlot sim, scaffold helpers
```

## 2. Package / Runtime Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (`.python-version` = 3.12) |
| Core deps | pyyaml, pydantic>=2, jsonschema, python-dotenv, Pillow, numpy, requests, google-auth, google-genai, openai |
| Web server | FastAPI + uvicorn (only used by Backlot board server) |
| Node | Remotion composer (React/Node) for programmatic composition |
| JS runtime | ink-theater (puppet/mocap animation) |
| Config | YAML (`config.yaml`) + `.env` for provider keys |
| No DB | **No database at all** — state is JSON checkpoint files on disk |

**Key finding:** OpenMontage is a *local, single-user, agent-driven* toolchain. There is no server-side job system, no multi-tenant concept, no persistent DB, no queue.

## 3. Current Database Layer

**None.** State persistence is:
- `lib/checkpoint.py` — JSON checkpoint files per pipeline stage (written to `pipeline/` dir)
- `lib/events.py` — append-only `events.jsonl` per project (Backlot observability)
- `tools/cost_tracker.py` — `cost_log.json` per project

No PostgreSQL, no SQLite, no ORM, no migrations. This is the single biggest gap versus the VPMS PRD (which requires `vpms.jobs`, `vpms.job_events`, `vpms.worker_registry`, `vpms.worker_capabilities`, `vpms.worker_jobs`, `vpms.artifacts`, `vpms.qa_reports`, `vpms.approvals`, `vpms.publish_receipts`, `vpms.source_apps` on the existing PostgreSQL/Supabase infrastructure).

## 4. Current Queue / Orchestration Code

**There is no queue and no orchestrator.** The architecture is explicitly "agent-first": the LLM coding assistant (Claude Code / Cursor / Copilot) IS the orchestrator. It reads pipeline manifests (YAML), follows stage-director skills (MD), calls Python tools, writes checkpoints, self-reviews. `PROJECT_CONTEXT.md` states: *"No Python orchestrator, no Python reviewer, no Python handlers. The agent drives the pipeline."*

Reusable pieces:
- `lib/checkpoint.py` — stage state persistence + prerequisites (conceptually similar to VPMS job state, but file-based and single-project)
- `lib/events.py` — append-only event log pattern (conceptually similar to VPMS event ledger, but tool-level, not job-level)
- `tools/cost_tracker.py` — estimate/reserve/reconcile budget pattern (reusable for VPMS cost governance)
- `pipeline_defs/*.yaml` — declarative stage manifests with approval gates (reusable as production-plan templates)

**Conflict with VPMS PRD:** VPMS requires a *server-side* deterministic job state machine with canonical transitions, event ledger, restart-safe persistence, idempotency, worker registry, capability verification, receipts, approvals. OpenMontage has none of these as a service — they exist only as agent-followed conventions.

## 5. Current Agent Architecture

- **Single-agent orchestration:** one LLM agent drives the whole pipeline (no role separation, no independent evaluator).
- **Tool contract:** `tools/base_tool.py` ToolContract — every tool declares name, version, tier (CORE/VOICE/ENHANCE/GENERATE/SOURCE/ANALYZE/PUBLISH), capability, provider, runtime (LOCAL/LOCAL_GPU/API/HYBRID), stability, dependencies, input/output schemas, fallback_tools, agent_skills, resource_profile.
- **Tool registry:** `tools/tool_registry.py` — auto-discovery, availability reporting, capability queries by tier/status.
- **Capability model:** tools declare `capability` strings (e.g. `tts`, `image_generation`, `video_post`) — but there is NO verification model (no `code_present` / `credential_verified` / `integration_verified` / `production_verified` / `healthy` flags as VPMS requires).
- **Review:** `skills/meta/reviewer.md` — advisory self-review, max 2 rounds. No independent evaluator role.
- **Approval gates:** pipeline manifests declare `human_approval_default` per stage; checkpoint protocol in `skills/meta/checkpoint-protocol.md`. No persistent approval records.

**Reusable:** the ToolContract + registry pattern maps cleanly onto the VPMS worker/capability registry (worker = tool family, capability = tool capability string). The `stability` field (EXPERIMENTAL/BETA/PRODUCTION) is a partial precursor to VPMS capability verification.

**Conflict:** VPMS requires role separation (Architecture Controller, API/State Specialist, Registry Specialist, Adapter Contract Specialist, Security Specialist, Test Specialist, Independent Evaluator) and refuses "implementer = evaluator". OpenMontage's single-agent self-review model conflicts with this.

## 6. Existing APIs

| API | Where | Notes |
|---|---|---|
| Backlot board server | `backlot/server.py` (FastAPI) | board state API, SSE change feed, media serving. Local dev tool, not a production API |
| Tool registry queries | `tools/tool_registry.py` | in-process, not HTTP |
| No job API | — | **No HTTP API for job creation, status, artifacts, cancel, approve, reject** |

**Missing entirely (VPMS Phase 1 API):** `POST /api/v1/content/jobs`, `POST /api/v1/video/jobs`, `GET /api/v1/jobs/:jobId`, `GET /api/v1/jobs/:jobId/status`, `GET /api/v1/jobs/:jobId/artifacts`, `POST /api/v1/jobs/:jobId/cancel`, `POST /api/v1/jobs/:jobId/approve`, `POST /api/v1/jobs/:jobId/reject`, `GET /api/v1/capabilities`, `GET /api/v1/workers`, `GET /health`.

## 7. Existing Tests

- `tests/contracts/` — 30+ contract test files (tool contracts, pipeline manifests, env example, provider adapters: kling, wan, hunyuan, seedance, comfyui, atlas, dashscope, jimeng)
- `tests/lib/` — checkpoint, clip embedder, corpus, source media review, variation checker
- `tests/qa/` — tool-by-tool output inspection
- `tests/pipelines/` — pipeline-level tests
- `tests/eval/` — eval harness
- `tests/test_network_guard.py` — network guard

**Missing:** no tests for job state machine, event ledger, idempotency, restart recovery, worker receipts, capability verification, approvals, auth. All VPMS-required test areas are greenfield.

## 8. License and Attribution Requirements

- **License:** GNU AGPL v3.0 (full text in `LICENSE`, 34.5KB). This is a strong copyleft license — network use triggers source-availability obligations.
- **Attribution:** README credits upstream `calesthio/OpenMontage` (original author), sponsors, and the open-source project identity. `THIRD_PARTY_NOTICES.md` exists in `ink-theater/`.
- **Fork rule (PRD §49):** before renaming product-facing references to VPMS, preserve the upstream license, copyright, and NOTICE files. The AGPL license file must remain; upstream attribution must remain in README/THIRD_PARTY_NOTICES.
- **Implication for VPMS:** VPMS is a fork of an AGPLv3 project. The AGPLv3 license must be preserved and the VPMS repo must remain AGPLv3-compatible (or the fork must be replaced with a clean-room implementation — a decision for Joseph, not the implementer).

## 9. What Is Reusable (preserve)

1. **ToolContract + tool registry** (`tools/base_tool.py`, `tools/tool_registry.py`) — maps to VPMS worker/capability registry concepts.
2. **Cost tracker pattern** (`tools/cost_tracker.py`) — estimate/reserve/reconcile maps to VPMS cost governance (estimated_cost, actual_cost, budget_limit).
3. **Checkpoint pattern** (`lib/checkpoint.py`) — stage prerequisites + state persistence concepts.
4. **Event log pattern** (`lib/events.py`) — append-only JSONL event stream concept.
5. **Pipeline manifests** (`pipeline_defs/*.yaml`) — declarative stage/approval-gate definitions usable as production-plan templates.
6. **Provider tool implementations** (167 tool files) — these are the *worker capabilities* VPMS will dispatch to (via adapters), not VPMS internals.
7. **Backlot** — useful as a VPMS observability UI later (SSE board), not Phase 1.
8. **Schemas** (`schemas/artifacts/*`) — artifact JSON schemas reusable for the VPMS artifact registry.

## 10. What Conflicts With the VPMS PRD

1. **No server-side job system** — OpenMontage is agent-driven, single-user, local. VPMS is a multi-tenant control plane with a persistent job model. (Not a conflict to fix by rewriting OpenMontage — VPMS is a NEW layer that manages these systems.)
2. **No database** — VPMS requires PostgreSQL schema (`vpms.*` tables) on existing Supabase infrastructure.
3. **No state machine** — VPMS requires a deterministic job state machine with canonical transitions, invalid-transition rejection, and per-transition events.
4. **No capability verification** — VPMS requires `code_present` / `credential_verified` / `integration_verified` / `production_verified` / `healthy` per capability, and refusal to dispatch unverified capabilities.
5. **No worker contract** — VPMS requires `GET /health`, `GET /capabilities`, `POST /jobs`, `GET /jobs/:id`, `GET /jobs/:id/artifacts`, `POST /jobs/:id/cancel` (or adapters).
6. **No receipts** — VPMS requires WorkerReceipts; OpenMontage has no concept of provider-confirmed vs. completed.
7. **No idempotency** — VPMS requires idempotency keys on job creation.
8. **No source-app auth** — VPMS requires service-level authentication/authorization; OpenMontage has none.
9. **No approval records** — VPMS requires persistent approval records (script gate + final video gate).
10. **Single-agent self-review** — conflicts with VPMS role separation + independent evaluator requirement.
11. **AGPLv3 license** — must be preserved; VPMS naming/rebranding must keep upstream attribution.

## 11. What Is Missing (greenfield for VPMS Core)

- `vpms/` package: api/, core/ (job-manager, state-machine, event-ledger, production-director, routing, approvals), adapters/ (chronos, avatar-webinar, vmf), registry/ (workers, capabilities), qa/ (technical, creative), db/ (migrations, repositories), security/
- PostgreSQL schema + migrations (`vpms.jobs`, `vpms.job_events`, `vpms.worker_registry`, `vpms.worker_capabilities`, `vpms.worker_jobs`, `vpms.artifacts`, `vpms.qa_reports`, `vpms.approvals`, `vpms.publish_receipts`, `vpms.source_apps`)
- Job state machine + event ledger service
- API Gateway (FastAPI) with the 11 Phase 1 endpoints
- Source-app authentication (service tokens)
- Idempotency handling
- Worker registry + capability registry with verification flags
- Worker adapter interface + mock test worker
- Worker receipts + artifact registry
- Approval system (script gate, final gate)
- QA routing (technical/creative)
- Dispatcher with retry/timeout/dead-letter handling
- Tests: unit, integration, restart recovery, idempotency, failure modes
- Docs: architecture.md, api-contracts.md, worker-contract.md, job-state-machine.md, capability-registry.md, decisions.md, test-evidence.md

## 12. Recommended Approach (for the implementing agent)

1. **Do NOT rewrite OpenMontage.** Keep the fork intact as the worker/tool layer. VPMS is a new control-plane package (`vpms/`) that sits above it.
2. **Use the existing PostgreSQL/Supabase infrastructure** (supabase-db container, PostgreSQL 17.6) — create a `vpms` schema, not a new DB server.
3. **Use FastAPI** (already a dependency via Backlot) for the API Gateway.
4. **Reuse the ToolContract/registry concepts** for the worker/capability registry data model.
5. **Preserve AGPLv3 license + upstream attribution** in any rename to VPMS.
6. **Build the mock worker first** to prove the golden path (job → dispatch → receipt → artifact → QA → approval → READY) before touching real workers.
7. **Phase 2** connects Chronos → Avatar Webinar → VMF adapters. Do not build MoneyPrint adapter in Phase 1 unless required for the first podcast.

---

*End of audit. No implementation performed. This document is the required deliverable before VPMS Core implementation begins (per the Phase 1 execution prompt).*
