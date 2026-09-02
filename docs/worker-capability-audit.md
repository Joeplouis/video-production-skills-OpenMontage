# VPMS Worker Capability & Credential Audit

**Date:** 2026-09-02
**Type:** Read-only audit (no code modified)
**Scope:** Capability (verified vs stubbed) + credential presence (PRESENT/MISSING only — no secret values) for the four VPMS worker systems.

> ⚠️ **DELIVERY BLOCKER:** The required target `/opt/empire/apps/VIDEO-PRODUCT-MANAGEMENT-SYSTEM/repo/docs/worker-capability-audit.md` is on a **read-only mount** (`/opt/empire/apps` is `ro`). Elevated write is not available in this session. This file is staged in the writable workspace as a fallback. Copy it to the target once the mount is remounted rw (or run as root).

---

## 1. VMF — Video Media Factory

**Path:** `/opt/empire/apps/full-stack/90percent-Video-Media-Factory/apps/ai-media-factory/api/`

### Capability — VERIFIED (real, wired)
- **Provider router** (`services/provider-router.js`) is a real, live implementation with per-provider call + poll logic:
  - **WaveSpeed** — real `api.wavespeed.ai/api/v3` submit + poll (`_wavespeedPoll`), models mapped (flux-klein, z-image-turbo, wan-2.7, kling-3.0-std, seedance-2.0-fast). Verified against docs.
  - **MuAPI** — real `api.muapi.ai/api/v1` submit + poll (`_muapiPoll`), models (seedream-v5.0-pro, veo3-fast, happy-horse-1).
  - **Runware** — real `api.runware.ai/v1/image_generation`.
  - **MiniMax H3** — real official API (`api.minimaxi.chat`), uses `MINIMAX_TOKENS_KEY` (H3 video token), submit + poll + download. Marked `verified-2026-08-28-joe-official`.
- **Render routes** (`routes/render.pipeline.js`, `render.creatomate.js`, `render.shotstack.js`) are real pipelines:
  - Shotstack dispatch + status polling + webhook completion (`webhooks/shotstack.js`).
  - Creatomate short-form dispatch (`services/creatomate.js`).
  - Fish Audio TTS + MiniMax TTS (real HTTP calls).
  - Pexels stock fetch (real).
- **Health/readiness check** (`render.pipeline.js` ~line 918) reports per-provider key presence.

### Capability — STUBBED / BLOCKED
- **SiliconFlow** (`siliconflow-*` models) — **placeholder only** (`source: 'placeholder-2026-08-28-joe'`). `siliconflowCall()` returns `blocked: 'SILICONFLOW_API_KEY_missing'`; no key in `.env`. **Not usable.**
- `emitJobEvent` is a Socket.io placeholder (no-op) — cosmetic only, does not block rendering.
- `render-worker.js` contains no provider logic (thin/legacy).

### Credentials (`.env`)
| Credential | Status |
|---|---|
| CREATOMATE_API_KEY | PRESENT |
| OLLAMA_CLOUD_API_KEY | PRESENT |
| RUNWARE_API_KEY_BOOKAISTUDIO | PRESENT |
| MUAPI_API_KEY | PRESENT |
| SHOTSTACK_API_KEY / SHOTSTACK_KEY | PRESENT |
| PEXELS_API_KEY | PRESENT |
| FISH_AUDIO_API_KEY | PRESENT |
| WAVESPEED_API_KEY | PRESENT |
| MINIMAX_API_KEY | PRESENT |
| MINIMAX_TOKENS_KEY (H3) | PRESENT |
| POSTIZ_API_KEY | PRESENT |
| SUPABASE_SERVICE_ROLE_KEY | PRESENT |
| PG_PASSWORD | PRESENT |

### VPMS adapter blockers
- **None for the core providers** (WaveSpeed, MuAPI, Runware, MiniMax H3, Shotstack, Creatomate, Fish) — all wired and keyed.
- **SiliconFlow models are NOT usable** (placeholder, no key) — do not route VPMS jobs to `siliconflow-*`.

---

## 2. Avatar Webinar

**Path:** `/opt/empire/apps/avatar-webinar/backend/` (container `avatar-webinar-api`, port 3200)

### Capability — VERIFIED (real, wired)
- **Provider router** (`services/avatar-provider-router.js`) — real catalog of MuAPI (infinitetalk, omnihuman, kling v1/v2, wan-2-2-speech), WaveSpeed (wan-ultra-fast, kling-std, seedance-fast), Runware (seedance). Preferred default: `muapi-infinitetalk` (marked "Working default (verified)").
- **Render queue** (`jobs/render-queue.js`) — real worker: `muapi.generateTalkingHead`, `muapi.generateCaptions`, `muapi.upscaleVideo`, `shotstack.composeSideBySide` for single/dual/podcast jobs.
- **Render routes** (`routes/renders.js`, `photo-video.js`) — real endpoints (`/single`, `/dual`, `/podcast`, `/render`, status polling) that enqueue to the worker. No stub markers found.
- **Services present:** muapi, runware, wavespeed, shotstack, did, tavus, elevenlabs, deepgram, voice-providers, laptop-render.

### Capability — STUBBED / BLOCKED
- **DID / Tavus** services exist but are **not** in the active provider router path (MuAPI is the working default). Treat as secondary/unverified.
- **Laptop GPU render node** (`LAPTOP_RENDER_URL`) is configured but the node is not reachable from this audit (port checks closed) — laptop-render is a separate on-demand path, not the primary cloud path.

### Credentials (`.env`)
| Credential | Status |
|---|---|
| SUPABASE_SERVICE_KEY | PRESENT |
| ENCRYPTION_KEY | PRESENT |
| JWT_SECRET | PRESENT |
| ELEVENLABS_API_KEY | PRESENT |
| DEEPGRAM_API_KEY | PRESENT |
| SHOTSTACK_API_KEY | PRESENT |
| SHOTSTACK_SANDBOX_KEY | **MISSING/EMPTY** |
| PEXELS_API_KEY | PRESENT |
| MUAPI_API_KEY | PRESENT |
| RUNWARE_API_KEY / _BOOKAISTUDIO | PRESENT |
| MINIMAX_API_KEY | PRESENT |
| OPENROUTER_API_KEY | PRESENT |
| OLLAMA_CLOUD_API_KEY | PRESENT |
| WAVESPEED_API_KEY | PRESENT |
| FISH_AUDIO_API_KEY | PRESENT |
| HUME_API_KEY / HUME_SECRET_KEY | PRESENT |
| APIFY_API_KEY | PRESENT |
| LAPTOP_RENDER_URL | PRESENT |
| **STRIPE_SECRET_KEY** | **PLACEHOLDER/EMPTY** (len 8) |
| **OPENAI_API_KEY** | **PLACEHOLDER/EMPTY** (len 8) |

### VPMS adapter blockers
- **STRIPE_SECRET_KEY is a placeholder** — any VPMS flow that touches billing/checkout via this backend will fail. Not a render blocker, but a monetization blocker.
- **OPENAI_API_KEY is a placeholder** — but the LLM chain is MiniMax → OpenRouter → Ollama Cloud, so rendering is not blocked.
- **SHOTSTACK_SANDBOX_KEY missing** — only matters if `SHOTSTACK_ENV=stage`; production (`v1`) key is present.
- **Container not currently running** (port 3200 closed at audit time) — adapter must start it.

---

## 3. Chronos — High-CPM Story Franchise

**Path:** `/opt/empire/apps/high-cpm-story-franchise/`

### Capability — STUBBED / BROKEN
- **`story_engine.py` is effectively a stub.** It does NOT actually call Fish Audio, Shotstack, or Postiz despite the start message claiming "Executing Fish Audio + Shotstack + Postiz pipeline...". It only:
  1. Sends a Telegram start notification,
  2. Appends an episode record to `series_state.json` (marked `status: 'complete'`),
  3. Sends a Telegram completion notification.
- **No real render, no narration, no publishing.** The pipeline is a notification + state-tracking shell.
- **`llm_router.py`** defines a provider chain (OpenRouter free, NVIDIA, Nous, AIHubMix, DeepSeek, MiniMax) but is **not called by story_engine.py** — it is standalone/unused in the current flow.

### Credentials
- `run_chronos.sh` requires `/opt/empire/.env.master` and validates `TELEGRAM_BOT_TOKEN`, `TELEGRAM_HOME_CHANNEL`, `SHOTSTACK_API_KEY`.
- **`/opt/empire/.env.master` does NOT exist** → `run_chronos.sh` fails its required-var check.
- **`cron.log` confirms crashes:** `KeyError: 'TELEGRAM_HOME_CHANNEL'` on every run (04:00, 10:00, 16:00, 22:00 slots). The engine has been failing at startup for every scheduled run.
- No local `.env` present (only `.env.example`).

### VPMS adapter blockers
- **Chronos is NOT a functional render worker.** It cannot produce video, narration, or posts. A VPMS adapter must NOT rely on it for actual output.
- **Hard blocker:** missing `/opt/empire/.env.master` (or equivalent env source) → crashes immediately.
- **No real render capability to expose** — would need a full rebuild of the pipeline (Fish TTS + Shotstack + Postiz) before it can serve VPMS.

---

## 4. MoneyPrint — MoneyPrinterTurbo

**Locations (two variants):**
- `/opt/empire/apps/MoneyPrinterTurbo-video-production/` (upstream fork)
- `/opt/empire/apps/MoneyPrinterTurbo-video-Extended/` (extended, has podcast_agents.py)

### Capability — VERIFIED (real, full pipeline)
- **MoneyPrinterTurbo is a real, complete video-generation pipeline** (`cli.py` stages: script → terms → audio → subtitle → materials → video). Supports Pexels/Pixabay/Coverr/local stock, Edge TTS (no key needed) + provider TTS (gemini:, mimo:, elevenlabs:, chatterbox:), subtitles, BGM.
- **`podcast_agents.py` (Extended)** — real orchestrator that submits jobs to the MPT API (`http://127.0.0.1:18082`) and polls tasks; supports `hybrid_shotstack: True` cloud render and Fish Audio narration (`fish:{FISH_AUDIO_VOICE_JOSEPH}`).
- **`moneyprinter-bridge.py`** (in avatar-webinar backend) — real HTTP microservice wrapping MPT services: `/stock/search`, `/stock/rank`, `/voice/generate` (7 providers), `/health`.

### Credentials
**Production variant (`config.toml`):**
| Credential | Status |
|---|---|
| pexels_api_keys | PRESENT |
| pixabay_api_keys | PRESENT |
| deepseek_api_key | PRESENT |
| llm_provider | set |
| openai_api_key | EMPTY |
| gemini_api_key | EMPTY |
| moonshot_api_key | EMPTY |
| twelvelabs_api_keys (Pegasus/Marengo) | **EMPTY** |
| sonilo_api_key | EMPTY |

**Extended variant (`.env`):**
| Credential | Status |
|---|---|
| MINIMAX_TOKENS_KEY | PRESENT |
| WAVESPEED_API_KEY | PRESENT |
| SHOTSTACK_API_KEY | PRESENT |
| FISH_AUDIO_API_KEY | PRESENT |
| openai_api_key / deepseek_api_key (config.toml) | EMPTY |

### VPMS adapter blockers
- **Core render works** (Pexels stock + Edge TTS + subtitle + video assembly) with keys present.
- **TwelveLabs (Pegasus/Marengo) is EMPTY** — semantic search/reorder of stock is disabled; falls back to keyword search. Not a hard blocker.
- **No LLM key in Extended config.toml** (openai/deepseek empty) — script generation may need an LLM key or a pre-supplied script.
- **Services not currently running** (ports 18082, 5100, 3300 closed at audit time) — adapter must start MPT API + bridge.
- **`moneyprinter-bridge.py`** expects MPT at `/opt/empire/workspaces/moneyprinter-original` and `moneyprinter-extended` — verify those paths exist before wiring the bridge.

---

## Summary of Blockers

| Worker | Render capability | Credential status | VPMS-usable? |
|---|---|---|---|
| **VMF** | ✅ Real (WaveSpeed, MuAPI, Runware, MiniMax H3, Shotstack, Creatomate, Fish) | ✅ All core keys present | ✅ **Yes** — best candidate. Avoid `siliconflow-*` (placeholder). |
| **Avatar Webinar** | ✅ Real (MuAPI talking-head, Shotstack compose) | ⚠️ STRIPE + OPENAI placeholders; sandbox key missing | ⚠️ **Render yes, billing no.** Start container (port 3200 down). |
| **Chronos** | ❌ **Stub** — notifications only, no real render | ❌ `/opt/empire/.env.master` missing → crashes | ❌ **No.** Needs full rebuild + env source. |
| **MoneyPrint** | ✅ Real (full pipeline + podcast_agents) | ⚠️ TwelveLabs empty; Extended LLM key empty | ⚠️ **Yes for stock+TTS render.** Start services (ports down); supply script/LLM key. |

**Top recommendation for a VPMS adapter:** route render jobs to **VMF** (fully wired + keyed). Use **MoneyPrint** for stock/TTS assembly and **Avatar Webinar** for talking-head renders (after starting the container and fixing the Stripe placeholder). **Do not route to Chronos** until it is rebuilt.
