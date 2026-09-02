# VPMS Capability Registry

## Overview

The VPMS capability registry tracks what each worker can do, and how verified that capability is. The goal: VPMS must refuse normal production dispatch to a capability that is not sufficiently verified.

## Two Registry Tables

### 1. Worker Registry (`vpms.worker_registry`)

Tracks workers themselves:

| Field | Type | Description |
|---|---|---|
| `worker_id` | string (PK) | Unique worker identifier (e.g., `vmf`, `avatar-webinar`) |
| `name` | string | Human-readable name |
| `base_url` | string | Worker's HTTP base URL (null = not HTTP-accessible) |
| `status` | string | `AVAILABLE`, `UNAVAILABLE`, `DRAINING` |
| `visibility` | string | `internal` or `public` |
| `health_status` | string | `HEALTHY`, `UNHEALTHY`, `UNKNOWN` |
| `last_health_check` | datetime | When health was last checked |
| `max_concurrency` | int | Max simultaneous jobs |
| `current_load` | int | Current job count |
| `is_active` | bool | Whether the worker is active |

### 2. Capability Registry (`vpms.worker_capabilities`)

Tracks capabilities per worker:

| Field | Type | Description |
|---|---|---|
| `worker_id` | string (FK) | Which worker provides this capability |
| `capability` | string | Capability identifier (e.g., `avatar-video`, `faceless-video`) |
| `code_present` | bool | Worker code exists and is deployed for this capability |
| `credential_verified` | bool | API keys/credentials are validated and active |
| `integration_verified` | bool | Integration tests pass in test environment |
| `production_verified` | bool | Verified in production environment (Phase 2+) |
| `healthy` | bool | Passing periodic health checks |
| `estimated_cost` | decimal | Estimated cost per job |
| `average_latency_seconds` | decimal | Average job completion time |
| `max_concurrency` | int | Max simultaneous jobs for this capability |
| `visibility` | string | `internal` or `public` |
| `is_active` | bool | Whether the capability is active |

## Dispatch Eligibility

A capability is **dispatchable** (can receive normal production work) only when all four Phase 1 verification flags are `True`:

```python
def is_dispatchable(self) -> bool:
    return (
        self.code_present
        and self.credential_verified
        and self.integration_verified
        and self.healthy
    )
```

**Note**: `production_verified` is NOT required for Phase 1 dispatch. It is a Phase 2 flag for production hardening.

If any required flag is `False`, `Dispatcher.dispatch()` raises `ValueError` and refuses to dispatch.

## Code Reference

- `vpms/registry/workers.py` — `WorkerRegistryService`
- `vpms/registry/capabilities.py` — `CapabilityRegistryService`
- `vpms/db/repositories/worker_repository.py` — `WorkerRepository`, `CapabilityRepository`
- `vpms/db/models.py` — `WorkerRegistry`, `WorkerCapability` SQLAlchemy models

## Phase 2 Registered Workers

Migration `vpms/db/migrations/002_register_phase2_workers.sql` registers workers and capabilities.

### Worker Registry

| worker_id | name | base_url | max_concurrency | health_status | is_active |
|---|---|---|---|---|---|
| `chronos` | Chronos Content Showrunner | NULL (file-based) | 1 | UNKNOWN | true |
| `avatar-webinar` | Avatar Webinar | `http://localhost:3200` | 3 | UNKNOWN | true |
| `vmf` | Video Media Factory | `http://localhost:4100` | 5 | UNKNOWN | true |
| `moneyprint` | MoneyPrint Faceless | — | — | — | **false** (Phase 3) |

### Chronos Capabilities

| capability | code_present | credential_verified | integration_verified | healthy |
|---|---|---|---|---|
| `content_research` | ✅ | ✅ | ✅ | ❌ |
| `script_generation` | ✅ | ✅ | ✅ | ❌ |
| `fish_audio_tts` | ✅ | ✅ | ✅ | ❌ |
| `shotstack_render` | ✅ | ✅ | ✅ | ❌ |
| `postiz_publish` | ✅ | ✅ | ✅ | ❌ |
| `full_episode_pipeline` | ✅ | ✅ | ❌ | ❌ |

### Avatar Webinar Capabilities

| capability | code_present | credential_verified | integration_verified | healthy |
|---|---|---|---|---|
| `podcast_production` | ✅ | ❌ | ❌ | ❌ |
| `render_from_script` | ✅ | ❌ | ❌ | ❌ |
| `podcast_hybrid` | ✅ | ❌ | ❌ | ❌ |
| `avatar_talking_head` | ✅ | ❌ | ❌ | ❌ |

### VMF Capabilities

| capability | code_present | credential_verified | integration_verified | healthy |
|---|---|---|---|---|
| `pipeline_video` | ✅ | ❌ | ❌ | ❌ |
| `ugc_batch` | ✅ | ❌ | ❌ | ❌ |
| `image_generation` | ✅ | ✅ | ✅ | ✅ |
| `video_generation` | ✅ | ✅ | ✅ | ✅ |

`image_generation` and `video_generation` on VMF are already dispatchable (VMs already has real credentials configured for Wavespeed/MuAPI/Runware). `mock_video_render` has been deactivated.

## Dispatch Eligibility Status

The only currently dispatchable Phase 2 capabilities are:
- `vmf.image_generation` ✅
- `vmf.video_generation` ✅

`render_from_script` (Avatar Webinar) and `full_episode_pipeline` (Chronos) require credential and integration verification before production dispatch. This is the correct Phase 2 state — adapters are built and wired, credentials are pending configuration.

## Updating Verification Flags

Use `CapabilityRegistryService.update_verification()`:

```python
cap_service = CapabilityRegistryService(session)
cap_service.update_verification(
    worker_id="vmf",
    capability="mock_video_render",
    production_verified=True,  # Promote to production-ready
)
```

## Finding Dispatchable Capabilities

```python
cap_service = CapabilityRegistryService(session)
dispatchable = cap_service.find_dispatchable(
    capability="mock_video_render",
    visibility="internal",
)
# Returns list of WorkerCapability records that can accept production work
```
