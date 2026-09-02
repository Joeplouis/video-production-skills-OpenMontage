# Phase 6 — VPMS API Client Migration Plan

**Status:** RESEARCH-ONLY (read-only exploration; no code written, no repo modified)
**Date:** 2026-09-02
**Author:** OpenClaw (Empire Operations Specialist)
**Scope:** Map the provider integrations of the 4 Phase-6 apps slated for VPMS migration, and produce a concrete plan to route their external provider calls through the VPMS API (job submission + status polling) instead of direct provider calls.

> **DELIVERY BLOCKER:** The requested target path `/opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo/docs/phase6-app-migration-plan.md` sits on a **read-only mount** (`/opt/empire/apps` is mounted `ro`). This file is the full deliverable, staged in the writable workspace. It must be copied to the target path once the mount is made writable (or via a writable overlay).

---

## 0. VPMS Target API (the destination contract)

All migration plans below route calls through the VPMS job API. The canonical contract (from `docs/api-contracts.md`, `docs/job-state-machine.md`, `docs/worker-contract.md`):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/content/jobs` | Create a content job (triggers Chronos workflow). Returns `{job_id, status: QUEUED}` immediately. Idempotent via `idempotency_key`. |
| `POST` | `/api/v1/video/jobs` | Create a video job (content/script already exists). Same response shape. |
| `GET` | `/api/v1/jobs/:job_id` | Full job detail (status, plan, output, cost, error). |
| `GET` | `/api/v1/jobs/:job_id/status` | Lightweight status for polling. |
| `GET` | `/api/v1/jobs/:job_id/artifacts` | Output artifacts. |
| `DELETE` | `/api/v1/jobs/:job_id` | Cancel. |

**Auth:** every request carries `X-Source-App: <app_id>`; source apps are registered in `vpms.source_apps`.

**Job lifecycle (relevant states):** `CREATED → QUEUED → PLANNING → RESEARCHING → SCRIPTING → … → DISPATCHING → ASSET_GENERATION → RENDERING → PROVIDER_CONFIRMED → OUTPUT_VERIFICATION → … → READY → PUBLISHED`. Failure states: `RETRYABLE_FAILURE`, `FAILED`, `BLOCKED`, `CANCELLED`.

**Worker adapter contract (`vpms/adapters/base.py`):** `worker_id`, `base_url`, `health_check`, `get_capabilities`, `dispatch`, `get_status`, `get_artifacts`, `cancel`. VPMS already ships a VMF adapter (see `docs/worker-api-documentation.md`).

**Migration pattern (uniform across all 4 apps):**
1. Replace direct provider HTTP calls with a VPMS client that `POST`s a job and returns a `job_id`.
2. Replace inline polling loops with VPMS `GET /jobs/:id/status` polling (or VPMS webhook/event push when available).
3. Keep the app's own DB as the source of truth for business state; store `vpms_job_id` + `vpms_status` columns.
4. Register each app as a `source_app` in `vpms.source_apps` and mint an `X-Source-App` credential.

---

## 1. BookFactory

**Repo:** `/opt/empire/apps/book-factory` (Node/TypeScript, Fastify + BullMQ + Prisma)

### 1.1 External providers / APIs

| Provider | What it does | Call pattern | Auth | Where |
|---|---|---|---|---|
| **Ollama** (local `:11434` + cloud `ollama.com` via `:cloud` model suffix) | All LLM stages: plan, outline, write, humanize, grammar, factcheck, compliance, blurb, title | **Sync** HTTP `POST /chat/completions` (non-streaming) | Bearer key for cloud; none for local | `apps/api/src/lib/llm.ts`, `lib/modelRouter.ts` |
| **xAI (Grok)** | Writer + humanizer for adult-romance categories only | **Sync** HTTP `POST /chat/completions` | `XAI_API_KEY` Bearer | `lib/llm.ts` (`callXAIChat`) |
| **Canva API** | Cover image generation: autofill brand template → export JPG | **Async job + polling** (POST `/autofills`, poll `/autofills/{id}` every 1.5s up to 20×; POST `/exports`, poll `/exports/{id}`) | OAuth token stored in DB (`oAuthToken` table) | `providers/canvaAdapter.ts`, `services/coverService.ts` |
| **Telegram Bot API** | Notifications / cover request delivery | **Sync** outbound | Bot token | `lib/telegram.ts` |
| **BullMQ + Redis** | Internal async orchestration (12 queues: planner, outline, draft, humanizer, grammar, hallucination, plagiarism, compliance, format, cover, publish, rotation) | Internal job queue | Redis | `queues.ts`, `workers/BookFactoryOrchestrator.ts` |
| **Video** | **No real generation** — `routes/videos.ts` only stores `videoAsset` URLs (kind/category/bookId). No TTS/render provider. | n/a | n/a | `routes/videos.ts` |

### 1.2 Current call pattern summary
- **LLM:** synchronous, blocking, per-stage. The orchestrator runs stages as BullMQ jobs, but each stage's LLM call is a blocking `fetch` to Ollama/xAI. No job-id + polling at the provider level.
- **Cover:** already async (Canva job + poll) — the closest to VPMS semantics today.
- **Video:** none (metadata only).

### 1.3 Migration plan
1. **Register** `book-factory` as a `source_app` in `vpms.source_apps`; mint `X-Source-App` credential.
2. **LLM stages → VPMS content jobs.** Replace `lib/llm.ts` direct `fetch` calls with a VPMS client that `POST /api/v1/content/jobs` with `request_type` per stage (`book_plan`, `book_outline`, `book_draft`, `book_humanize`, `book_grammar`, `book_factcheck`, `book_compliance`, `book_blurb`, `book_title`), `content` = the stage prompt + book context, and `idempotency_key` = `book-{bookId}-{stage}`. Poll `GET /jobs/:id/status` until `READY`/`FAILED`; read output from `GET /jobs/:id/artifacts`.
   - **Provider routing note:** VPMS must honor the existing `modelRouter.ts` rule (xAI/Grok for adult-romance write/humanize, Ollama otherwise). Pass the desired provider/model as a `production` hint in the job payload so VPMS dispatches to the right worker.
3. **Cover → VPMS video/content job.** Wrap `canvaAdapter.ts` autofill+export in a VPMS job (`request_type: book_cover`). VPMS already has a Canva/design capability path; the app should submit once and poll VPMS instead of its own 1.5s×20 loop. Keep the Canva OAuth token lifecycle in BookFactory (VPMS adapter can call back into the app's token store, or the token is moved to VPMS credential vault — decide in Phase 6 design).
4. **Video (future):** when BookFactory gains real video gen, route through `POST /api/v1/video/jobs` (VPMS already has a VMF adapter).
5. **Keep BullMQ** as the app-internal orchestrator; each BullMQ stage becomes a thin VPMS submit+poll wrapper rather than a direct provider call.

### 1.4 Blockers
- **xAI/Ollama provider routing** must be expressible in VPMS job payloads (adult-romance gating). If VPMS can't express per-job provider preference, the router logic must move into a VPMS worker.
- **Canva OAuth token** currently lives in BookFactory's DB; VPMS adapter needs a token source (move to vault or callback).
- **No real video provider** in BookFactory today — VPMS video migration is only relevant once video gen is added.

---

## 2. Affiliate Factory (UGC Affiliates Production System)

**Repo:** `/opt/empire/apps/full-stack/ugc-affiliates-production-system` (Python; note: NOT at `/opt/empire/apps/ugc-affiliates-production-system` — it lives under `/opt/empire/apps/full-stack/`)

### 2.1 External providers / APIs

| Provider | What it does | Call pattern | Auth | Where |
|---|---|---|---|---|
| **LLM Fallback Router** (9 providers, 2 tiers) | Scripts, translations, captions, compliance | **Sync + streaming** HTTP `POST /chat/completions` (tier 1 free: aihubmix_free, nvidia, openrouter_free, nous; tier 2 paid: ollama_cloud, minimax, aihubmix, deepseek, openrouter) | Per-provider Bearer keys; Nous uses OAuth device-flow + auto-refresh | `llm_fallback.py` |
| **VMF — Video Media Factory** (Joseph's own, port 4100) | Script gen + UGC video render (image-to-video, voiceover) | **Async job + polling** (`POST /api/pipeline/generate-script`, `POST /api/pipeline/script-to-video`, `GET /api/pipeline/status/:jobId`) | Bearer `VMF_API_KEY` (JWT) | `production/vmf_client.py` |
| **Video Production API** (Joseph's own) | Generic production job submit/poll | **Async job + polling** (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/output`, `DELETE /jobs/{id}`); dry-run fallback | Bearer key | `production/video_client.py` |
| **MuAPI** | TTS, lip-sync, avatar image, captions, upscale, platform publish | **Async** REST (`api.muapi.ai/api/v1`) | `MUAPI_API_KEY` | `autopilot/tools/muapi_client.py` |
| **Apify** | Social/e-commerce research scraping (YouTube, TikTok, IG, Twitter, Google, ecommerce actors) | **Async actor runs** | `APIFY_API_TOKEN` | `shared/apify_engine.py`, `research/apify_research.py` |
| **Qdrant** | Vector store for research embeddings | **Sync** HTTP | none (internal) | `shared/qdrant_client.py` |
| **Postiz** | Social scheduling of completed videos | **Sync** HTTP POST | Bearer `POSTIZ_API_KEY` | `production/postiz_publisher.py` |
| **Mautic / Supabase / Redis** | CRM / video factory state / queues | Sync / internal | creds in `.env` | config |
| **HeyGen / Cling** | **Replaced** by VMF (2026-08-01); kept only as backward-compat wrapper classes | n/a | n/a | `vmf_client.py` (HeyGenClient/ClingAIClient) |

### 2.2 Current call pattern summary
- **Video:** already async job + polling (VMF + video_client). This is the most VPMS-ready app.
- **LLM:** sync/streaming, in-process fallback router with retries.
- **Research:** async Apify actor runs, results embedded into Qdrant.
- **Publish:** sync Postiz call after video completion.

### 2.3 Migration plan
1. **Register** `ugc-affiliates` as a `source_app`.
2. **Video render → VPMS video job.** Replace `vmf_client.create_video` / `video_client.create_production_job` with `POST /api/v1/video/jobs` (`request_type: ugc_video`, `production` = video_model/image_model/voice_provider, `content` = script + product). Poll `GET /jobs/:id/status`; pull final MP4 from `GET /jobs/:id/artifacts`. VPMS already ships a **VMF adapter** (`docs/worker-api-documentation.md`) — this is a near drop-in.
3. **Script generation → VPMS content job.** Route `vmf_client.generate_script` and the LLM fallback router's script/translation calls through `POST /api/v1/content/jobs` (`request_type: ugc_script`). VPMS owns the LLM provider fallback; the app stops calling 9 providers directly.
4. **Research → VPMS research stage.** Map Apify actor runs to VPMS `RESEARCHING` state jobs (`request_type: ugc_research`, `content` = niche/category). VPMS dispatches to an Apify worker; results land in artifacts (and can be mirrored to Qdrant by the app or a VPMS worker).
5. **Publish → VPMS `PUBLISH_REQUESTED`/`SCHEDULED`.** After `READY`, submit a publish job so VPMS drives Postiz scheduling instead of the app calling Postiz directly.
6. **Keep** `video_client.py` dry-run mode as a dev fallback; gate on VPMS availability.

### 2.4 Blockers
- **LLM fallback router** is a bespoke 9-provider, 2-tier, cost-aware router with Nous OAuth auto-refresh. VPMS must either (a) adopt this router as a worker, or (b) expose a generic LLM capability that reproduces the tiering/off-peak DeepSeek window. Losing the cost logic would raise spend.
- **MuAPI** (TTS/lip-sync/avatar) has no VPMS adapter yet — needs a new worker adapter.
- **Apify** research is async and long-running; VPMS must support long `RESEARCHING` jobs and artifact handoff to Qdrant.
- **Postiz** publish is a side-effect; VPMS publish state machine must tolerate external scheduling (idempotency on `post_id`).

---

## 3. AI Audit (AI Audit Business)

**Repo:** `/opt/empire/apps/ai-audit-business` (Python, Flask + SQLite)

### 3.1 External providers / APIs

| Provider | What it does | Call pattern | Auth | Where |
|---|---|---|---|---|
| **Ollama Cloud / MiniMax / OpenRouter** | Structured assessment generation (pain points, quick wins, solutions, 4-day plan) | **Sync** HTTP `POST /chat/completions` (timeout 60s), provider fallback order from settings | Bearer keys | `02-report-engine/report_engine.py` (`call_chat_completion_provider`, `build_llm_assessment`) |
| **Hermes Agent harness bridge** (port 8792) | Per-company report writing (the **permanent** report path) | **Sync** HTTP `POST /generate` (timeout 1200s); bridge shells out to `hermes -p report-writer chat` → Ollama Cloud deepseek-v4-flash with MiniMax/OpenRouter fallbacks | none (internal) | `hermes_report_bridge.py`, `call_hermes_bridge()` |
| **Deepgram (Nova-3)** | Audio transcription (diarized, punctuated) | **Sync** HTTP `POST /v1/listen` (timeout 300s) | `DEEPGRAM_API_KEY` (Token) | `transcribe_audio_with_deepgram()` |
| **YourAIToolShop** (`youraitoolshop.com/api/tools`) | Live AI-tool catalog for recommendations | **Sync** GET, in-process cached | none | `fetch_aitoolshop_tools()` |
| **Telegram Bot API** | Audit summary notifications | **Sync** outbound | Bot token | `send_telegram_audit_summary()` |
| **Agent runtime** (`03-ai-agent`) | Onboarding chat loop; calls audit API + Telegram | Sync HTTP to audit API | `X-Audit-Key` | `agent_runtime.py` |

### 3.2 Current call pattern summary
- **Report generation is synchronous and blocking** inside request handlers: `build_llm_assessment` (60s) then `call_hermes_bridge` (up to 1200s). The HTTP request blocks for minutes.
- **Transcription** is synchronous (300s).
- **Tool catalog** is a cached sync fetch.

### 3.3 Migration plan
1. **Register** `ai-audit` as a `source_app`.
2. **Report generation → VPMS content job (async).** Replace the blocking `build_llm_assessment` + `call_hermes_bridge` sequence with `POST /api/v1/content/jobs` (`request_type: ai_audit_report`, `content` = client profile + verbatim transcript + uploaded documents). Return `job_id` to the client immediately; poll `GET /jobs/:id/status` and render the report when `READY`. This converts the current minutes-long blocking request into a proper async job — the single biggest UX/architecture win for this app.
   - **Hermes bridge** becomes a VPMS worker (or VPMS dispatches to the existing bridge as a worker adapter). The bridge's per-company, per-client report logic stays intact behind the adapter.
3. **Transcription → VPMS job.** Route `transcribe_audio_with_deepgram` through a VPMS job (`request_type: audio_transcribe`) so long audio doesn't block the request; poll for the transcript artifact.
4. **Tool catalog** can stay as a cached sync fetch (low latency, not a job candidate) — or optionally become a VPMS `RESEARCHING` artifact if the catalog grows.
5. **Keep** the structured LLM assessment as a VPMS fallback path; the Hermes harness remains the primary report writer.

### 3.4 Blockers
- **Hermes bridge** is a host-side subprocess harness (`hermes` CLI + skill file) — VPMS must either wrap it as a worker adapter or accept the bridge as the report worker. The 1200s timeout must be preserved in VPMS job semantics (long-running jobs).
- **Provider fallback order** (Ollama → MiniMax → OpenRouter) is user-configurable in the app's `provider-settings`; VPMS must honor per-tenant provider preference or the app must pass it in the job payload.
- **Deepgram** has no VPMS adapter yet — needs a new worker adapter.
- **Synchronous-to-async refactor** touches the assessment/report request handlers and the client portal polling; needs a status endpoint in the app to surface VPMS job state to the UI.

---

## 4. UGC Partner Program

**Repo:** `/opt/empire/apps/ugc-partner-program` (Python FastAPI + SQLite + React frontend)

### 4.1 External providers / APIs

| Provider | What it does | Call pattern | Auth | Where |
|---|---|---|---|---|
| **Stripe** | Payments + webhooks (affiliate commissions, payouts) | **Sync** SDK + async webhook | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | `api/main.py` (`stripe_webhook`) |
| **SQLite** | App DB (affiliates, offers, promo assets, sales, commissions, payouts) | Internal | n/a | `api/database.py`, `models.py` |
| **Content production** | **None.** `PromoAsset` stores pre-written scripts/captions as **text fields** (`tiktok_reels_script`, `facebook_caption`, `linkedin_caption`, `email_template`, `sms_template`, `video_ad_script`, `image_screenshot_url`, `demo_url`). No image/video/TTS/render provider is called. | n/a | n/a | `api/models.py` |

### 4.2 Current call pattern summary
- **No external content-generation providers.** The app is a pure affiliate CRM: Stripe for money, SQLite for state, React for UI. "Content production" is static text assets authored by admins, not generated at runtime.

### 4.3 Migration plan
1. **Register** `ugc-partner-program` as a `source_app` (for future-proofing).
2. **No provider calls to migrate today.** There are no image/TTS/video/render calls to route through VPMS.
3. **Optional forward integration:** when the program starts generating promo assets (e.g., auto-render `video_ad_script` into a real video), route that through `POST /api/v1/video/jobs` (`request_type: ugc_promo_video`, `content` = the stored script/caption). The `PromoAsset` table gains `vpms_job_id`/`vpms_status` columns; the frontend polls VPMS status to show "rendering → ready".
4. **Stripe webhooks** stay as-is (payment events are not VPMS production jobs).

### 4.4 Blockers
- **None for migration** — there is nothing to migrate today. The only work is registering the source app and (optionally) wiring future promo-video generation to VPMS.
- **Note:** this app is often conflated with Affiliate Factory (§2). They are separate repos; only Affiliate Factory has real production providers.

---

## 5. Cross-App Summary

| App | Providers to migrate | Current pattern | VPMS job type | Effort | Blockers |
|---|---|---|---|---|---|
| **BookFactory** | Ollama, xAI, Canva | LLM sync; Canva async+poll | `content/jobs` (LLM stages), `content/jobs` (cover) | Medium | xAI/Ollama routing; Canva OAuth token source; no real video yet |
| **Affiliate Factory** | VMF, LLM router, MuAPI, Apify, Postiz | Video async+poll; LLM sync; research async; publish sync | `video/jobs`, `content/jobs`, research stage, publish stage | **High** (most providers) | LLM cost-aware router; MuAPI + Apify adapters; Postiz idempotency |
| **AI Audit** | Ollama/MiniMax/OpenRouter, Hermes bridge, Deepgram | **All sync/blocking** | `content/jobs` (report), transcribe job | Medium | Hermes bridge as worker; per-tenant provider order; sync→async refactor |
| **UGC Partner Program** | Stripe (only) | Sync + webhook | none today | **Low** | None (nothing to migrate) |

### Recommended sequencing
1. **Affiliate Factory video** first — VPMS already has a VMF adapter; near drop-in, highest value.
2. **AI Audit report** — converts the worst blocking path to async; big UX win.
3. **BookFactory LLM + cover** — medium effort, needs provider-routing support.
4. **UGC Partner Program** — register source app only; no code change.

### Cross-cutting requirements for VPMS (Phase 6)
- **Per-job provider/model routing** (BookFactory xAI/Ollama; AI Audit per-tenant order; Affiliate Factory cost-aware fallback).
- **Long-running job support** (AI Audit Hermes 1200s; Apify research).
- **New worker adapters:** MuAPI, Apify, Deepgram, Hermes bridge, Canva (or reuse existing VMF/design adapters).
- **Idempotency** on publish (Postiz) and on job submission (`idempotency_key`).
- **Source-app registration + `X-Source-App` credentials** for all 4 apps.
