# Worker API Documentation — VPMS Adapter Source Pack

**Status:** Read-only research compiled from on-disk source inspection (no code modified).
**Audience:** VPMS adapter authors writing `BaseWorkerAdapter` implementations for the three workers below.
**Sources:**
- VMF (Video Media Factory) — `apps/full-stack/90percent-Video-Media-Factory/apps/ai-media-factory/api/`
- Avatar Webinar — `apps/avatar-webinar/backend/` (container `avatar-webinar-api`, port `3200`)
- Chronos — `apps/high-cpm-story-franchise/run_chronos.sh` (CLI script, not HTTP)

This document maps each worker's *native* surface to the `vpms/adapters/base.py` contract
(`worker_id`, `base_url`, `health_check`, `get_capabilities`, `dispatch`, `get_status`,
`get_artifacts`, `cancel`). It complements the canonical spec in `docs/worker-contract.md`
by recording the actual quirks VPMS adapters must translate around.

---

## 1. VMF — Video Media Factory (Express/Node)

**Repo:** `apps/full-stack/90percent-Video-Media-Factory/apps/ai-media-factory/api/`
**Entrypoint:** `server.js` (2,398 lines). Registered prefix routers at the bottom of the file
`api/routes/render.pipeline.js`, `api/routes/ugc.js`, `api/routes/render.shotstack.js`,
`api/routes/render.creatomate.js`, `api/routes/copilot.js`, `api/routes/auth.js`, etc.
**Port:** `process.env.PORT || 4000`
**Public base URL:** `https://video.bookaistudio.com` (default `APP_BASE_URL`).

### 1.1 Health & capability discovery

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Returns `{status, app, timestamp, uptime, env}`. Anonymous. |
| GET | `/api/languages` | `[{code, name, voice_preset, is_active}]` from Supabase. 503 if Supabase unavailable. |
| GET | `/api/style-presets` | Style catalog for templates. |
| GET | `/api/dashboard/stats` | Aggregate counters over in-memory + Supabase `jobs`. |
| GET | `/api/analytics/overview` | 30-day job rollup; 503 without Supabase. |

### 1.2 The render pipeline (the adapter's main target)

VMF dispatches a real video render by POSTing internally to a separate
**render worker** at `${RENDER_SERVER_URL || RENDER_WORKER_URL || http://127.0.0.1:8016}/render/ugc`
(`server.js` lines 952–963, inside `runUgcRenderJob`). This is the only "real" long-running
backend that VPMS should treat as a true async job; the rest of `server.js` exposes scaffold
endpoints that pretend to be workers but do not actually call external services.

### 1.3 Submit a UGC render (the dispatch endpoint)

**`POST /api/ugc/render`** — `server.js:2001`

`requireAuth` middleware **is NOT** attached. Callers must be server-side trusted (no
`Authorization` header is checked at the route level). Supabase-backed write is gated only on
`requireSupabaseKey` (i.e., a service-role key must be configured or the route degrades to
in-memory mode).

Request body (any one of these shapes — see `buildUgcWorkerPayload` at `server.js:428`):

**Shape A — pre-planned clips** (preferred for VPMS):
```json
{
  "clips": [
    {"url": "https://...", "trim_start": 0, "trim_end": 5.0, "duration": 5.0}
  ],
  "audio_mode": "original" | "voiceover" | "silent",
  "voiceover_url": "https://...",
  "voiceover_text": "optional TTS fallback text",
  "voiceover_language": "en",
  "voiceover_voice": "voice-id",
  "background_music_url": "https://...",
  "background_music_volume": 0.15,
  "burn_captions": true,
  "captions": [{"text": "hi", "start": 0, "end": 2.5, "duration": 2.5}],
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "out_path": "/opt/empire/.../out.mp4",
  "project_id": "<uuid or omit; auto-resolved via resolveOrCreateUgcProjectId>",
  "version_id": "<uuid or null>"
}
```

**Shape B — scene list** (the planner path; voiceover is auto-built from scene narration):
```json
{
  "scenes": [
    {"url": "https://...", "trimStart": 0, "trimEnd": 5, "voiceover": "Hello world"}
  ],
  "aspectRatio": "9:16" | "16:9" | "1:1",
  "audio": {
    "narrationEnabled": true,
    "narrationVoice": "voice-id",
    "voiceoverLanguage": "en",
    "backgroundMusicUrl": "https://...",
    "masterLevel": 15,
    "duckOriginalAudio": false
  },
  "captions": {"enabled": true},
  "exportLabel": "my-render.mp4",
  "fps": 30,
  "project_id": "...",
  "version_id": "..."
}
```
Scene `url` resolution checks `url / sourceUrl / source_url / assetUrl / asset_url /
storage_path / storagePath / sourceLabel` — every one must be an http(s)/file URL or
absolute path. **If no scene has a resolvable URL, the route returns 400.**

Response **202 Accepted**:
```json
{
  "job_id": "<uuid>",
  "id": "<same uuid>",
  "job": {"id": "<uuid>", "status": "pending"},
  "asset": {"id": "<uuid>", "project_id": "...", "name": "...", "url": "/api/ugc/outputs/<id>", "storage_path": "...", "type": "video", "created_at": "..."},
  "preview_url": "/api/ugc/outputs/<id>",
  "download_url": "/api/ugc/outputs/<id>",
  "progress_url": "/api/jobs/<id>/progress",
  "events_url": "/api/jobs/<id>/events",
  "message": "..."
}
```

### 1.4 Job status polling (the `get_status` target)

**`GET /api/jobs/:id/progress`** — `server.js:1816`. Anonymous. Routes through
`getJobProgress(jobId)` which checks in-memory `memoryJobs` first, falls back to Supabase.

Response:
```json
{
  "id": "<uuid>",
  "status": "pending" | "running" | "completed" | "failed",
  "progress_percent": 0-100,
  "updated_at": "ISO-8601",
  "output_path": "/opt/empire/..." | null,
  "output_url": "/api/ugc/outputs/<id>" | null,
  "error": null | "message",
  "job": { ... full job row ... },
  "latest_event": { "id","job_id","percent","phase","message","status","output_path","output_url","error","created_at" },
  "asset": { ... } | null,
  "preview_url": "...",
  "download_url": "..."
}
```
**Status normalization** — `server.js:149-168` maps `queued→pending`, `running/processing→running`, `completed/done→completed`, `failed/error→failed`. VPMS adapter should accept any of these.

**`GET /api/jobs/:id/events`** — `server.js:1845`. SSE stream of `job_events` rows. Headers
`Content-Type: text/event-stream`. Each message is `data: <JSON>\n\n`. The stream emits historical
events on connect, then forwards new events. Closes when terminal status reached. Useful as
an alternative to polling (see `dispatch` progress events emitted by `insertJobEvent`,
`server.js:538`).

### 1.5 Artifacts (download)

**`GET /api/ugc/outputs/:jobId`** — `server.js:1936`. Streams the rendered MP4:
- If `output_path` is absolute, must resolve under `UGC_OUTPUT_DIR` (default
  `cwd/outputs/ugc`). Sends file via `res.sendFile`, 404 if missing, 400 if path
  escapes the sandbox.
- If a Supabase storage row exists, downloads via
  `supabase.storage.from(UGC_OUTPUT_BUCKET).download()` and forwards.
- If `output_url` is an http(s) URL, redirects.
- 404 if none of the above.

For VPMS artifact handling, prefer reading `output_url`/`download_url` from the status
response first; only fall back to this endpoint when those are missing.

### 1.6 Other relevant endpoints

| Method | Path | Use |
|---|---|---|
| GET | `/api/videos` | List videos (merged memory + Supabase UGC render rows). |
| GET | `/api/videos/:id` | Get one video by id (memory or job id). |
| POST | `/api/videos/generate` | **Scaffold only** — does NOT actually render. Returns 202 with `worker_status: "pending"` and a message saying "Full render worker integration is not connected". **Do NOT use as a VPMS dispatch target.** |
| POST | `/api/jobs` | Generic job creation; requires Supabase. Only `job_type: "dummy_proof"` triggers the in-process `spawnDummyWorker` stub. Other types just create a row. |
| GET | `/api/jobs` | Last 20 jobs from Supabase (or memory). |
| POST | `/api/jobs/:id/progress` | Worker-side progress emission. **Internal-only**; VPMS adapter should not POST to this from outside the worker trust boundary. |
| POST | `/api/ugc/render` | **The real dispatch endpoint.** |
| POST | `/api/webhooks/pipeline` | Shotstack webhook (worker → server). |
| POST | `/api/webhooks/creatomate` | Creatomate webhook. |
| POST | `/api/webhooks/shotstack` | Shotstack webhook (duplicate mount). |

### 1.7 Auth model & adapter notes

- `requireAuth` middleware (`api/middleware/requireAuth.js`) exists but is **not** wired into
  the UGC render or jobs routes in `server.js`. The UGC render route relies on
  `requireSupabaseKey` (server-capable key) for write paths.
- Supabase URL default: `https://nzhpsasfjfzixddooady.supabase.co`.
- Supabase key acceptance: any `sb_secret_*` or JWT with `role: service_role`.
- CORS: `app.use(cors())` — open by default.
- The `app.use("/api/renders", express.static("/opt/empire/storage/renders"))` mount at
  line 2144 means any file under that directory is publicly served at `/api/renders/...`.
- All static renders live under `process.env.VPS_STORAGE_ROOT || /opt/empire/storage/renders`.

### 1.8 Adapter contract mapping (cheat sheet)

| VPMS method | VMF call |
|---|---|
| `worker_id` | `"video-media-factory"` (matches `app: 'video-media-factory'` in health) |
| `base_url` | `process.env.VMF_API_URL || https://video.bookaistudio.com` |
| `health_check` | `GET /api/health` |
| `get_capabilities` | `GET /api/languages` + `GET /api/style-presets` (degraded to empty if Supabase down) |
| `dispatch` | `POST /api/ugc/render` (Shape A pre-planned clips) |
| `get_status` | `GET /api/jobs/{worker_job_id}/progress` |
| `get_artifacts` | `GET /api/ugc/outputs/{worker_job_id}` (binary stream) — alternatively read `output_url`/`preview_url` from status response |
| `cancel` | **NOT SUPPORTED.** VMF has no cancel endpoint. Adapter should raise `WorkerError("not_supported")` or implement best-effort via Supabase row update if accessible. |

---

## 2. Avatar Webinar backend (`avatar-webinar-api`, port 3200)

**Repo:** `apps/avatar-webinar/backend/`
**Entrypoint:** `server.js` (Express, helmet, CORS, rate-limit 200/15min).
**Port:** `process.env.PORT || 3200`
**Public base URL:** `https://avatar-webinar.bookaistudio.com`
**Auth:** All non-webhook routes use `requireAuth` middleware
(`middleware/auth.js`) which expects a Supabase Bearer JWT.
**CORS allow-list:** `https://avatar-webinar.bookaistudio.com`, `http://localhost:3000`, `http://localhost:5173`.
**Rate limit:** 200 req / 15 min per IP on `/api/*`.

### 2.1 Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{status: "ok", ts: ISO-8601}`. Anonymous. |
| GET | `/api/photo-video/output/:jobId/:file` | Static file serve for photo-video renders. |

### 2.2 Avatars (`/api/avatars`) — `routes/avatars.js`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/avatars` | yes | List current user's `avatar_profiles` (`id, name, provider, avatar_id, voice_clone_id, role, thumbnail_url, created_at`). |
| POST | `/api/avatars` | yes | Create profile. Required: `name, provider, avatar_id`. `provider` ∈ `{muapi, custom}`. Optional `voice_clone_id, role, thumbnail_url, api_key` (encrypted). |
| PUT | `/api/avatars/:id` | yes | Update fields. `api_key` re-encrypted on each call. |
| DELETE | `/api/avatars/:id` | yes | Delete profile. |

`avatar_id` is the public URL to the face photo (consumed by MuAPI OmniHuman in
`render-queue.js`); `voice_clone_id` is an ElevenLabs voice ID.

### 2.3 Renders (`/api/renders`) — `routes/renders.js`

All routes require `requireAuth`.

#### POST /api/renders/single — submit a single-avatar render job

Body:
```json
{
  "avatar_profile_id": "<uuid from /api/avatars>",
  "script": "Plain text narration",
  "energy": "calm" | "energetic" | "professional",
  "session_id": "<uuid or null>"
}
```
Returns **202** `{job_id, status: "queued"}`. Pipeline (in `jobs/render-queue.js`):
TTS via MuAPI ElevenLabs → OmniHuman talking head → optional MuAPI captions → optional MuAPI upscale.
Status stored in Supabase `render_jobs` and polled in-process every 5s via `setInterval`.

#### POST /api/renders/dual — submit a dual-avatar render job

Body:
```json
{
  "audio_url": "https://.../podcast.mp3",
  "avatar_profile_id_1": "<uuid>",
  "avatar_profile_id_2": "<uuid>",
  "speaker1_name": "Joseph",
  "speaker2_name": "Emma",
  "energy": "calm",
  "session_id": "<uuid or null>"
}
```
Pipeline: Deepgram diarize → behavior-tags → ElevenLabs TTS per speaker → MuAPI OmniHuman per avatar → Shotstack side-by-side composite.

#### POST /api/renders/podcast — full podcast → dual avatar pipeline

Body (extended dual):
```json
{
  "audio_url": "https://.../podcast.mp3",
  "avatar_profile_id_1": "<uuid>",
  "avatar_profile_id_2": "<uuid>",
  "speaker1_name": "...",
  "speaker2_name": "...",
  "energy": "calm" | "energetic" | "professional",
  "session_id": "<uuid or null>",
  "use_original_audio": false
}
```
Same as dual but designed for uploaded podcast audio (uses `Speaker_0`/`Speaker_1` instead of
`_1`/`_2`).

#### GET /api/renders/:id/status — poll render job status

Returns one row from `render_jobs`:
```json
{
  "id": "<uuid>",
  "type": "single" | "dual" | "podcast",
  "status": "queued" | "processing" | "done" | "failed",
  "output_url": "https://.../final.mp4" | null,
  "error_message": null | "string",
  "created_at": "ISO-8601",
  "completed_at": "ISO-8601" | null
}
```
**Important:** This endpoint is the canonical poll. Status states are not normalized to
VPMS vocabulary — adapter must map `done → completed`, `failed → failed`, `queued/processing → pending/running`.
404 if id unknown.

#### GET /api/renders — list recent jobs (optional filter `?session_id=...`)

### 2.4 Production (`/api/production`) — `routes/production.js` + `routes/podcast-scene-render.js`

This is the higher-level "Smart Production" API used by the existing podcast wizard.

#### POST /api/production/plan

Builds a plan from a transcript/source. Body:
```json
{
  "source_type": "recording" | "webinar" | "session",
  "source_id": "<uuid>",
  "production_type": "podcast_hybrid",
  "transcript": [{"speaker":"Host","text":"...","start_ms":0,"end_ms":5000}],
  "audio_url": "https://...",
  "settings": {"maxAvatarCostPerVideo": ..., "maxAvatarSeconds": ...}
}
```
Returns **201** `{job_id, status: "planned", plan: {...}}` with budget warnings if estimated cost exceeds limit.

#### POST /api/production/approve
Body `{job_id, force?: bool, approval_notes?: string}`. Moves job from `planned` → `approved`.
**403** if budget exceeded and `force` not passed.

#### POST /api/production/render
Body:
```json
{
  "job_id": "<uuid>",
  "avatar_image_url": "https://...",
  "avatar_2_image_url": "https://...",
  "audio_url": "https://...",
  "speaker1_name": "Host",
  "speaker2_name": "Co-Host",
  "brand_config": {},
  "webhook_url": "https://..."
}
```
**Synchronous render** (not async!) — `server.js` does not respond until `executeProductionPlan`
completes. Returns `{job_id, status: "done", final_video_url, actual_cost, savings, short_clips}`
or 5xx with error message.

#### GET /api/production/:id — get job + scenes

#### GET /api/production/:id/status — poll status

Returns:
```json
{
  "job_id": "<uuid>",
  "status": "planned" | "approved" | "rendering" | "done" | "failed",
  "progress": 0.0 - 1.0,
  "final_video_url": "https://..." | null,
  "error": null | "message"
}
```
`progress` is computed as `avatar_done / avatar_total` over scenes whose `visual_type` is
`omnihuman_avatar` or `infinitetalk`.

#### GET /api/production/:id/assets — get final video + per-scene render status + cost summary

#### PUT /api/production/:id/scene — override a scene's visual type

#### GET /api/production/templates — list templates (`TEMPLATES` from `smart-production.js`)

#### GET /api/production/providers — list provider availability (`getAvailableProviders`)

#### POST /api/production/podcast-scene-render (mounted under `/api/production/podcast-scene-render`)

This is the *legacy* podcast scene renderer — synchronous, no job polling. Body:
```json
{
  "title": "...",
  "audio_url": "https://.../podcast.mp3",
  "voice1_id": "elevenlabs-voice-id",
  "voice2_id": "elevenlabs-voice-id" | null,
  "avatar_image_url": "https://.../host.jpg",
  "avatar_2_image_url": "https://.../guest.jpg",
  "speaker1_name": "Host",
  "speaker2_name": "Guest"
}
```
**Validation:** requires `audio_url, voice1_id, avatar_image_url, avatar_2_image_url`.
**Auth:** `requireAuth`. Internally calls Deepgram → ElevenLabs re-voice → MuAPI OmniHuman
intro clips → Runware office background → ffmpeg concat. Returns **202** with `job_id` from
`production_jobs` and a `poll_url` of `/api/production/<id>/status`. Final output served at
`/uploads/brands/podcast-<jobId>-final.mp4`.

### 2.5 Photo-video (`/api/photo-video`) — `routes/photo-video.js`

#### POST /api/photo-video/render

Synchronous, ffmpeg-only, $0 cost. Body:
```json
{
  "image_url": "https://...",
  "image_2_url": "https://..." | null,
  "audio_url": "https://...",
  "title": "My Podcast",
  "speaker1": "Host",
  "speaker2": "Guest"
}
```
**Auth:** `requireAuth` (via `auth` middleware alias — same as `requireAuth`).
Returns `{success, job_id, video_url: "/api/photo-video/output/<jobId>/output.mp4", duration_sec, cost: 0, message}`.
Side-effect: stores result in `os.tmpdir()/photo-video/<jobId>/output.mp4`.

#### GET /api/photo-video/status/:jobId

In-memory map only (`router._jobs`). Returns `{status: "done", outputPath, publicUrl, duration}` or 404.

#### GET /api/photo-video/output/:jobId/:file

Static serve of the rendered file.

### 2.6 Copilot (`/api/copilot`) — `routes/copilot.js`

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/copilot` | Conversation endpoint. Body `{prompt: string ≤ 2000, session?}`. Returns `{type: "question"|"action", ...}` for conversational intake. |
| POST | `/api/copilot/execute` | Body `{platform, intent, filled_fields}`. Fires the actual pipeline once the form is filled. |
| GET | `/api/copilot/intents` | Returns `{platforms: {"video-media-factory": {label, description, intents[]}, "avatar-webinar": {...}}}` — useful for adapter discovery. |

### 2.7 Voices (`/api/voices`) — `routes/voices.js`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/voices/providers` | no | List voice providers. |
| GET | `/api/voices` | yes | List user's saved voices. |
| POST | `/api/voices/preview` | yes | Preview a voice. |
| POST | `/api/voices/tts` | yes | Generate TTS. |
| POST | `/api/voices/translate` | yes | Translate + TTS. |

### 2.8 Webhooks

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/webhooks/stripe` | Stripe events. |
| POST | `/api/webhooks/shotstack` | Shotstack render-complete callbacks. Mounted with **raw body** for signature verification. |

### 2.9 Adapter contract mapping (cheat sheet)

There are **two adapter strategies** — pick based on whether the integration needs pre-planning
approval or is fire-and-forget.

**Strategy A — fire-and-forget (recommended for VPMS):**
| VPMS method | Avatar Webinar call |
|---|---|
| `worker_id` | `"avatar-webinar"` |
| `base_url` | `process.env.AVATAR_WEBINAR_URL || https://avatar-webinar.bookaistudio.com` |
| `health_check` | `GET /health` |
| `get_capabilities` | `GET /api/copilot/intents` + `GET /api/production/providers` |
| `dispatch` (single avatar) | `POST /api/renders/single` (Shape: `{avatar_profile_id, script, energy, session_id}`) |
| `dispatch` (dual avatar) | `POST /api/renders/dual` (Shape: `{audio_url, avatar_profile_id_1, avatar_profile_id_2, ...}`) |
| `dispatch` (full podcast) | `POST /api/renders/podcast` (with `use_original_audio` flag) |
| `get_status` | `GET /api/renders/{worker_job_id}/status` |
| `get_artifacts` | Read `output_url` from status response (no separate artifact endpoint). |
| `cancel` | **NOT SUPPORTED** — render queue retries up to 3× then marks failed. Adapter should mark VPMS job `failed` when status flips to `failed`. |

**Strategy B — pre-planned with approval** (when caller needs budget gates):
| VPMS method | Avatar Webinar call |
|---|---|
| `dispatch` (submit plan) | `POST /api/production/plan` (returns `plan_id`, awaits approval) |
| pre-render approval gate | `POST /api/production/approve` with `{job_id, force: bool}` |
| execute the render | `POST /api/production/render` (synchronous; or use `POST /api/production/podcast-scene-render` for the legacy async flavor) |
| `get_status` | `GET /api/production/{job_id}/status` |
| `get_artifacts` | `GET /api/production/{job_id}/assets` (returns `final_video_url`, per-scene `render_url`, cost summary) |

**Auth note:** every non-health call needs `Authorization: Bearer <supabase-jwt>`. VPMS
will need to mint or hold a service-account JWT to call Avatar Webinar; that JWT must
have a real user record in the target Supabase (`avatar-webinar.bookaistudio.com` uses its own
Supabase instance — not shared with VMF).

---

## 3. Chronos — `run_chronos.sh` (CLI, not HTTP)

**Repo:** `apps/high-cpm-story-franchise/`
**Entrypoint:** `run_chronos.sh` (55-line bash wrapper).
**Underlying engine:** `story_engine.py` (113 lines, run synchronously).
**Trigger:** cron, 4× per day (04:00 / 10:00 / 16:00 / 22:00 local time).
**Credentials:** loaded from the global `/opt/empire/.env.master` via `env_loader.py`
(bash `source` is too brittle for that file's YAML-style lines).

### 3.1 Invocation

```bash
# Auto-pick next slot from series_state.json
/opt/empire/apps/high-cpm-story-franchise/run_chronos.sh

# Force a specific slot:
/opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 0  # 04:00 — Solar (High-Ticket Emergency Solar Generators)
/opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 1  # 10:00 — SaaS (B2B SaaS & Cloud Infrastructure)
/opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 2  # 16:00 — Recovery (Home Recovery, Saunas & Cold Plunges)
/opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 3  # 22:00 — E-Bikes (Premium E-Bikes & Micro-Mobility)
```

Standard cron install (already in place per `run_chronos.sh` header):
```
0 4  * * *  /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 0 >> /opt/empire/apps/high-cpm-story-franchise/cron.log 2>&1
0 10 * * *  /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 1 >> /opt/empire/apps/high-cpm-story-franchise/cron.log 2>&1
0 16 * * *  /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 2 >> /opt/empire/apps/high-cpm-story-franchise/cron.log 2>&1
0 22 * * *  /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh 3 >> /opt/empire/apps/high-cpm-story-franchise/cron.log 2>&1
```

### 3.2 Inputs

| Type | Source | Notes |
|---|---|---|
| Positional arg | `$1` | Optional integer `0..3` slot index. If empty, `story_engine.py` reads `series_state.json` and rotates `active_slot_index`. |
| Env: `TELEGRAM_BOT_TOKEN` | `.env.master` | **Required.** Exit 2 if missing. |
| Env: `TELEGRAM_HOME_CHANNEL` | `.env.master` | **Required.** Exit 2 if missing. |
| Env: `SHOTSTACK_API_KEY` | `.env.master` | **Required.** Exit 2 if missing. |
| Env: `FISH_AUDIO_API_KEY` | `.env.master` | Optional. Defaults to ''. |
| Env: `FISH_AUDIO_API_URL` | `.env.master` | Optional. Defaults to `https://api.fish.audio/v1`. |
| Env: `POSTIZ_API_KEY` | `.env.master` | Optional. |
| Env: `POSTIZ_API_URL` | `.env.master` | Optional. Defaults to `https://postiz.bookaistudio.com/api`. |
| Env: `POSTIZ_ENABLED` | `.env.master` | Optional. Default `'false'`. |
| File: `series_state.json` (cwd) | Persistent | `{'active_slot_index': int, 'episodes_history': [{episode, niche, series, slot, timestamp, status}]}`. Mutated in-place on each run. |

### 3.3 Outputs

| Channel | Content |
|---|---|
| `cron.log` (append, file) | stdout+stderr of the bash + python invocation. |
| Telegram: `TELEGRAM_HOME_CHANNEL` | Start: `⚡ ChronosStoryEngine Active (<slot> Slot)\n\nNiche: <niche>\nSeries: <series>\nEpisode: <ep_num>\n\nExecuting Fish Audio + Shotstack + Postiz pipeline...` End: `🎬 ChronosStoryEngine Episode Published\n\nSlot: <slot>\nSeries: <series> — Ep. <ep_num>\nNiche: <niche>\n\nNext scheduled run: <next slot> (<next niche>)` |
| `series_state.json` (overwrite) | Updated `active_slot_index = (slot_index + 1) % 4` and an appended `episodes_history` row with `status: "complete"`. |
| Exit code | `0` on success. `2` if required env vars missing. Other non-zero codes propagate from `story_engine.py` (currently only Telegram errors are caught and demoted to print, so non-zero exits from Python are unlikely). |

### 3.4 What `story_engine.py` actually does (the "pipeline" is a no-op stub)

Read lines 73–112 of `story_engine.py`: the function `execute_scheduled_niche_run` builds the
Telegram messages, updates `series_state.json`, and **sends two Telegram messages** (start +
completion). It does **NOT** actually call Fish Audio, Shotstack, or Postiz. The shell
header advertises a "Fish Audio + Shotstack + Postiz pipeline" but that pipeline is not
implemented in the current `story_engine.py`. The `POSTIZ_ENABLED` flag is read but never
gated on.

**VPMS implication:** Chronos today is a notification + state-tracking daemon, not a render
worker. The `dispatch` and `get_artifacts` adapter methods have nothing to call into — at best
VPMS can:
  - call `run_chronos.sh <slot>` to trigger an episode (and observe Telegram / cron.log for output)
  - read `series_state.json` for `episodes_history` (effectively the `get_status` surface)
  - infer `get_artifacts` from Telegram notifications (no machine-readable artifact URLs are emitted)

If Chronos needs to be a first-class worker in VPMS, the pipeline in `story_engine.py` would
need to be expanded to actually generate and publish a video per episode. Until then, treat
Chronos as an external schedule trigger rather than a render target.

### 3.5 Adapter contract mapping (cheat sheet)

| VPMS method | Chronos call |
|---|---|
| `worker_id` | `"chronos-story-engine"` |
| `base_url` | n/a (CLI). Adapter should expose `process.env.CHRONOS_SCRIPT_PATH || /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh` as the "endpoint". |
| `health_check` | `test -x /opt/empire/apps/high-cpm-story-franchise/run_chronos.sh && test -f /opt/empire/apps/high-cpm-story-franchise/story_engine.py` |
| `get_capabilities` | Parse `NICHES` list (4 slots, niche/series/products per slot). The list is hard-coded in `story_engine.py` lines 23–48 — there is no machine-readable external catalog. Adapter may want to vendor this list or read it via Python `ast.literal_eval`. |
| `dispatch` | `subprocess.run([str(script), str(slot)])`. No job id returned; adapter should generate its own `worker_job_id` and observe state via `series_state.json`. |
| `get_status` | Read `/opt/empire/apps/high-cpm-story-franchise/series_state.json` — look up the latest `episodes_history` row matching `slot == X`. Status is always `'complete'` once appended (no failure path recorded). |
| `get_artifacts` | **NO MACHINE-READABLE ARTIFACTS.** The Telegram completion message is the only artifact pointer. Adapter should return empty list and rely on operator notification. |
| `cancel` | **NOT SUPPORTED.** No way to kill an in-flight run beyond killing the process. |

---

## Cross-Worker Summary for VPMS Adapter Authors

| Concern | VMF | Avatar Webinar | Chronos |
|---|---|---|---|
| Transport | HTTP (Express, port 4000) | HTTP (Express, port 3200) | CLI bash script |
| Auth | None on `/api/ugc/render` (server-trusted). Supabase service key required in config. | Supabase JWT Bearer required on all non-webhook/non-health routes. | None (env-based) |
| Submit model | `POST /api/ugc/render` returns 202 + `job_id` | `POST /api/renders/*` returns 202 + `job_id`. `POST /api/production/render` is **synchronous**. | Subprocess invocation; no job id. |
| Status surface | `GET /api/jobs/:id/progress` (normalized status). SSE alternative at `/api/jobs/:id/events`. | `GET /api/renders/:id/status` (raw status). `GET /api/production/:id/status` (computed progress). | `series_state.json` only; always `complete` once appended. |
| Artifact surface | `GET /api/ugc/outputs/:jobId` streams MP4; or `output_url` from status. | `output_url` in `render_jobs` row. `final_video_url` in `production_jobs`. Static files under `/uploads/brands/`. | None (Telegram only). |
| Cancel | Not supported | Not supported (queue retries 3× then `failed`). | Not supported (kill the process). |
| Idempotency key | None in API surface (worker derives `crypto.randomUUID()`) | None in API surface | N/A |
| Webhook callback | `POST /api/webhooks/pipeline`, `/api/webhooks/shotstack`, `/api/webhooks/creatomate` (worker → server) | `POST /api/webhooks/shotstack` (server → Shotstack). Render queue does NOT support worker callbacks today. | None |
| Cost / budget | Not enforced at API | Enforced via `production/plan` + `approve {force}`. | Not enforced |
| Main gotcha | `api/videos/generate` is a SCAFFOLD only — no real worker. Only `api/ugc/render` and `api/jobs` (with `dummy_proof`) actually do work. | Synchronous `POST /api/production/render` will block the request thread until done (no internal queue). | "Pipeline" advertised by header is not implemented; only Telegram notifications + state file are emitted. |

---

## Gaps & Open Questions for the Adapter Team

1. **VMF cancellation** — no endpoint exists. Options: (a) document as unsupported; (b) cancel
   via the underlying Supabase row update (`jobs.status = 'cancelled'`); (c) build a thin
   `POST /api/jobs/:id/cancel` upstream patch (out of scope for VPMS).
2. **VMF auth** — the UGC render endpoint is server-trusted. For VPMS, treat it as such: do
   not try to mint a user JWT. Either run VPMS in the same trust boundary as VMF, or front
   VMF with a tiny gateway that does the auth translation.
3. **Avatar Webinar JWT** — VPMS will need to hold or mint a Supabase user JWT bound to the
   Avatar Webinar Supabase project. Confirm whether service-role JWTs are sufficient for
   `requireAuth` (they likely are not — `requireAuth` expects a user JWT, not service-role).
   If not, either provision a service-account user or wrap calls in a trusted proxy.
4. **Avatar Webinar synchronous render** — `POST /api/production/render` blocks until done.
   Decide whether VPMS should treat that as a "fire-and-forget" dispatch (the worker pattern)
   or skip it in favor of `POST /api/renders/podcast` (async via in-process queue).
5. **Chronos "artifacts"** — there are none on disk today. Decide whether VPMS should:
   (a) skip Chronos as a render worker and only treat it as a scheduler; (b) extend
   `story_engine.py` to write a per-episode artifacts manifest. This requires Joe's sign-off
   per the standing directive ("stop all building" without explicit go).
6. **Idempotency** — none of the three workers honor an idempotency key. VPMS adapter should
   either (a) generate UUIDs client-side and dedupe at the VPMS layer; (b) document that
   retries may produce duplicate jobs.
7. **Worker availability probing** — VMF exposes `/api/health` (anonymous, trivial). avatar-Webinar
   exposes `/health` (anonymous, trivial). Chronos has no liveness probe beyond the script
   being executable. Consider whether VPMS `health_check` should also verify that the
   corresponding `.env.master` keys are populated.