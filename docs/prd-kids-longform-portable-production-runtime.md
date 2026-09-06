# PRD — Kids Long-Form Portable Production Runtime

**Status:** Proposed build specification
**Component name:** `kids_longform_movie`
**System:** VPMS + OpenMontage
**Primary goal:** Produce repeatable full-length, character-driven kids animation episodes using a portable production runtime that can be deployed on any compatible compute environment without changing application code.

---

## 1. Product Goal

Build a new VPMS/OpenMontage system component that can take one or more fully prepared kids-movie episode packages and execute the entire production workflow on a temporary or permanent compute target.

The production runtime MUST NOT be tied to any specific GPU model, cloud vendor, rental provider, workstation, VPS, or machine topology.

The same production package and orchestration logic must be able to run on:

- a single compatible GPU machine;
- a multi-GPU machine;
- a remote GPU rental;
- a private GPU server;
- a cloud VM;
- a local workstation for development/testing;
- future compute providers that implement the same deployment and worker contracts.

Hardware selection is a deployment-time decision. The runtime discovers available resources and schedules work accordingly.

The initial business target is a weekly kids channel capable of producing full-length ~30-minute character-driven animated movies. The software must also support shorter and longer episode durations without architecture changes.

---

## 2. Non-Negotiable Architecture Rules

1. **Do not replace or gut OpenMontage.** Preserve its existing pipelines, skills, Backlot, checkpoints, Remotion composer, HyperFrames integration, FFmpeg tooling, character-animation pipeline, provider knowledge, artifact handling, and approval flow.
2. **Do not create a second universal provider platform.** Existing VMF/provider infrastructure remains available through adapters where appropriate.
3. **Do not hardcode hardware.** No GPU model names, provider names, machine counts, or fixed VRAM assumptions may appear in scheduling logic.
4. **Do not require Joseph's laptop.** A production batch must continue to completion while the user's laptop is powered off.
5. **Do not make one model generate the entire movie.** Production is shot-based and capability-routed.
6. **Do not let the same agent generate and grade the same artifact.** Follow Harness / Diagram Loop Engineering.
7. **Do not claim success without evidence.** Every worker job must return receipts, artifacts, timings, status, and errors.
8. **Do not require reinstallation each production session.** The runtime must support a reproducible container/image and persistent/shared model storage.
9. **Do not make story generation consume paid production compute unnecessarily.** Scripts, story bibles, shot plans, voices, and reusable references should be prepared before production execution when possible.
10. **All long-running work must be resumable.** A failed or terminated compute session must not require restarting the entire episode.

---

## 3. System Boundary

### VPMS owns

- batch creation;
- episode/job state;
- scheduling;
- worker/capability registry;
- shot routing;
- retries;
- checkpoints;
- artifact ledger;
- receipts;
- approvals;
- cost/runtime accounting;
- production status;
- final readiness state.

### Chronos / Story Intelligence owns

- series bible;
- episode premise;
- story arc;
- lesson/learning intent;
- age/tone constraints;
- dialogue;
- scene intent;
- continuity from prior episodes.

Chronos outputs story artifacts. It does not render video.

### OpenMontage owns

- production intelligence;
- scene/shot planning;
- character-animation pipeline;
- deterministic local animation where appropriate;
- style/playbook application;
- Backlot approvals;
- Remotion/HyperFrames composition;
- FFmpeg assembly;
- subtitles/graphics/audio composition where already supported;
- final production artifact organization.

### Motion / visual workers

Workers are capability providers, not orchestrators. Initial adapters should support:

- **Forge-compatible image worker** — canonical character stills, poses, expressions, backgrounds, keyframes, LoRA inference when configured;
- **FramePack-compatible worker** — image-to-long-motion, continuous character/environment movement;
- **H3 LongMedia-compatible worker** — audio-aware motion, reference-conditioned motion, dialogue/lip-sync, multi-clip/camera-controlled performance;
- **OpenMontage deterministic character worker** — rig/pose/action-timeline animation;
- **VMF adapter/fallback worker** — existing media generation/provider capabilities where requested.

The design MUST allow future workers to be added without changing the `kids_longform_movie` pipeline contract.

---

## 4. High-Level Flow

```text
PERMANENT CONTROL / PREPARATION ENVIRONMENT

Series Bible
    |
Chronos / Story Planner
    |
Episode Script
    |
Independent Story Evaluator
    |
Scene Plan
    |
Shot Manifest
    |
Character / Location / Voice References
    |
Production Package READY
    |
    v
PORTABLE PRODUCTION RUNTIME
    |
Runtime Preflight + Hardware Discovery
    |
Capability Registry
    |
VPMS Scheduler
    |
Shot Classifier / Router
    |
+----------------+----------------+----------------+----------------+
|                |                |                |                |
Deterministic    Continuous       Dialogue /       Other / Existing
Animation        Motion           Performance      VMF Capability
|                |                |                |
OpenMontage      FramePack        H3 LongMedia     Adapter
|                |                |                |
+----------------+----------------+----------------+----------------+
                         |
                    Shot Artifacts
                         |
                  Technical Shot QA
                         |
                Continuity Evaluation
                         |
                  OpenMontage Assembly
                         |
                   Audio / SFX / BGM
                         |
                    Captions / Graphics
                         |
                    Technical Final QA
                         |
                 Independent Creative QA
                         |
                    Human Approval
                         |
                       FINAL
```

---

## 5. Production Package Contract

The production runtime receives a complete, self-describing batch package.

Suggested layout:

```text
production-batch/
  batch.json
  series/
    series-bible.json
    world-bible.json
    style-bible.json
  characters/
    <character_id>/
      character.json
      references/
      poses/
      expressions/
      rig/
  locations/
    <location_id>/
  voices/
  music/
  performances/
  episodes/
    <episode_id>/
      episode.json
      script.json
      scene-plan.json
      shot-manifest.json
      audio/
      references/
  outputs/
  receipts/
  qa/
```

### `batch.json`

Minimum fields:

```json
{
  "batch_id": "kids-batch-001",
  "profile": "kids_longform_movie",
  "episode_ids": ["episode-001"],
  "priority": 5,
  "deadline_seconds": null,
  "quality_policy": "production",
  "retry_policy": "controlled",
  "compute_policy": "auto",
  "allow_fallback_workers": true,
  "requested_outputs": ["master_video", "thumbnail", "metadata", "qa_report"]
}
```

No compute vendor, GPU model, or GPU count belongs in the episode content contract.

---

## 6. Series, Character, and Episode Memory

### Series Bible

Required fields:

- `series_id`
- title
- audience age range
- tone
- world rules
- storytelling rules
- educational/learning policy
- recurring themes
- prohibited content/rules
- continuity policy
- visual style ID
- audio/music style

### Character Bible

Required fields:

- `character_id`
- canonical name
- role
- personality
- visual description
- palette
- clothing/accessories
- body proportions
- master reference assets
- voice ID
- expressions
- poses/actions
- rig ID if available
- LoRA/reference configuration if available
- continuity rules
- forbidden changes

### Episode Bible

Required fields:

- `episode_id`
- `series_id`
- target duration
- premise
- lesson/theme
- beginning
- conflict
- escalation
- climax
- resolution
- character arcs
- locations
- continuity from previous episode
- continuity required for future episode

These artifacts are persistent and reused. New episodes must not recreate canonical characters from scratch.

---

## 7. Shot Manifest — Core Production Contract

The shot manifest is the contract between story/planning and production workers.

Each shot MUST have a stable ID.

Example:

```json
{
  "episode_id": "episode-001",
  "scene_id": "scene-012",
  "shot_id": "shot-047",
  "start_ms": 804000,
  "duration_ms": 12000,
  "characters": ["milo-v1", "luna-v1"],
  "action": "Milo and Luna walk toward the glowing cave entrance.",
  "dialogue": [],
  "camera": {
    "framing": "wide",
    "movement": "slow_tracking"
  },
  "location_id": "crystal-cave-exterior-v1",
  "continuity": {
    "previous_shot_id": "shot-046",
    "next_shot_id": "shot-048",
    "must_preserve": ["clothing", "backpack", "lighting_direction"]
  },
  "references": {
    "characters": ["characters/milo-v1/master.png", "characters/luna-v1/master.png"],
    "environment": "locations/crystal-cave-exterior-v1/master.png"
  },
  "audio": [],
  "production_request": {
    "required_capabilities": ["continuous_character_motion"],
    "preferred_capabilities": ["image_to_long_video"],
    "forbidden_capabilities": [],
    "quality_tier": "production"
  }
}
```

The planner may express capability needs. It MUST NOT hardcode a specific machine.

---

## 8. Shot Classification and Routing

Implement a deterministic routing layer based on shot requirements and live worker capabilities.

Initial capability classes:

### A. `deterministic_character_animation`
Use for:

- simple dialogue blocking;
- reactions;
- idle motion;
- pose transitions;
- reusable walk/run cycles;
- repeated character actions;
- shots where deterministic continuity is more important than generative novelty.

Preferred worker family: OpenMontage character-animation / HyperFrames / Remotion.

### B. `continuous_character_motion`
Use for:

- walking;
- running;
- dancing;
- exploring;
- continuous environment interaction;
- longer non-dialogue motion.

Initial worker family: FramePack-compatible adapter.

### C. `audio_aware_character_performance`
Use for:

- speaking;
- singing;
- lip-sync;
- emotional dialogue performance;
- audio-timed body/facial motion;
- reference-performance redubbing.

Initial worker family: H3 LongMedia-compatible adapter.

### D. `character_keyframe_generation`
Use for:

- canonical stills;
- keyframes;
- expressions;
- poses;
- location/background creation.

Initial worker family: Forge-compatible adapter.

### E. `general_media_generation`
Use existing VMF/provider capabilities as fallback or when the production request calls for them.

Routing score should consider:

- required capability match;
- worker health;
- worker availability;
- memory fit;
- estimated runtime;
- queue depth;
- quality history;
- continuity history;
- retry history;
- estimated monetary cost;
- production deadline;
- explicitly configured policy.

---

## 9. Portable Compute Runtime

### Requirement

Production software must run from a reproducible deployment artifact, preferably an OCI-compatible container image plus mounted model/artifact storage.

### Runtime responsibilities

On startup:

1. load configuration;
2. discover CPU/RAM/storage;
3. discover accelerator devices;
4. discover available VRAM per accelerator when applicable;
5. detect installed model assets;
6. detect installed production engines;
7. register each available worker capability;
8. run health checks;
9. verify writable artifact storage;
10. verify required episode package assets;
11. report `READY` only after preflight passes.

### Forbidden behavior

- no hardcoded CUDA device count;
- no assumption of a specific GPU family;
- no assumption that GPU index `0` is the only worker;
- no assumption all accelerators are identical;
- no machine-specific absolute paths in production manifests;
- no cloud-provider SDK calls inside shot workers;
- no production failure merely because a preferred worker is unavailable when a compatible fallback exists.

### Compute target abstraction

Create a `ComputeTarget` / runtime descriptor such as:

```json
{
  "target_id": "runtime-01",
  "platform": "linux",
  "containerized": true,
  "cpu_threads": 24,
  "ram_bytes": 274877906944,
  "accelerators": [
    {
      "device_id": "gpu-0",
      "backend": "cuda",
      "memory_bytes": 34359738368,
      "status": "available"
    }
  ],
  "storage": {
    "models_path": "/models",
    "work_path": "/work",
    "output_path": "/output"
  }
}
```

This is an example shape only. Scheduling code must not depend on the example values.

---

## 10. Worker Contract

All production workers expose a common adapter contract:

```text
GET  /health
GET  /capabilities
POST /jobs
GET  /jobs/:workerJobId
GET  /jobs/:workerJobId/artifacts
POST /jobs/:workerJobId/cancel
```

### Worker capability response

```json
{
  "worker_id": "framepack-worker-01",
  "status": "healthy",
  "runtime": "local_gpu",
  "capabilities": [
    "image_to_long_video",
    "continuous_character_motion"
  ],
  "resources": {
    "accelerator_required": true,
    "min_vram_bytes": null,
    "recommended_vram_bytes": null,
    "concurrency": 1
  }
}
```

Do not advertise capabilities that have not passed integration verification.

### Worker receipt

Every completed worker job returns:

```json
{
  "vpms_job_id": "vpms_...",
  "episode_id": "episode-001",
  "shot_id": "shot-047",
  "worker_id": "framepack-worker-01",
  "worker_job_id": "worker-...",
  "status": "SUCCEEDED",
  "engine": "framepack",
  "model": "configured-runtime-model",
  "seed": 31337,
  "started_at": "...",
  "completed_at": "...",
  "duration_seconds": 123.4,
  "estimated_cost": null,
  "actual_cost": null,
  "artifacts": ["..."],
  "errors": []
}
```

---

## 11. Batch, Episode, and Shot State Machines

### Batch states

```text
CREATED
-> VALIDATING
-> READY
-> DEPLOYING
-> PREFLIGHT
-> RUNNING
-> ASSEMBLING
-> QA
-> WAITING_FOR_APPROVAL
-> COMPLETE
```

Failure/interrupt states:

```text
BLOCKED
RETRYABLE_FAILURE
FAILED
CANCELLED
INTERRUPTED
```

### Episode states

```text
PREPARED
-> SHOTS_QUEUED
-> GENERATING
-> SHOT_QA
-> ASSEMBLING
-> FINAL_QA
-> WAITING_FOR_APPROVAL
-> READY
```

### Shot states

```text
CREATED
-> QUEUED
-> ASSIGNED
-> GENERATING
-> VERIFYING
-> QA
-> ACCEPTED
```

Alternate terminal/intermediate states:

```text
RETRY_PENDING
REJECTED
FAILED
BLOCKED
CANCELLED
```

Every transition MUST write an append-only event to the VPMS event ledger.

---

## 12. Checkpoint / Resume Requirements

A production session may terminate at any time. The system must resume without regenerating accepted work.

Persist after every meaningful boundary:

- batch validation;
- episode validation;
- shot dispatch;
- worker receipt;
- artifact verification;
- shot QA;
- accepted shot;
- assembly milestone;
- final QA;
- approval.

On restart:

1. load batch state;
2. reconcile receipts with artifact storage;
3. mark missing/incomplete worker jobs for retry;
4. preserve all accepted shots;
5. rebuild only missing or rejected work;
6. resume assembly when prerequisites are complete.

No accepted shot may be regenerated automatically unless explicitly invalidated.

---

## 13. Audio-First Timing

For dialogue-driven animation, audio timing should be locked before expensive motion generation whenever possible.

Each dialogue element should carry:

- speaker ID;
- audio artifact path;
- start time;
- end time;
- duration;
- emotion/performance tag;
- language;
- voice ID.

Example:

```json
{
  "speaker_id": "milo-v1",
  "audio": "audio/milo-shot-048.wav",
  "start_ms": 250,
  "end_ms": 4550,
  "emotion": "excited"
}
```

Audio-aware workers receive the authoritative audio artifact and shot timing rather than generating timing from text alone.

---

## 14. Reusable Series Asset Library

Weekly throughput depends on reuse.

The component must support persistent versioned assets for:

- character masters;
- rigs;
- LoRAs/reference configs;
- expression libraries;
- pose libraries;
- action cycles;
- common performance clips;
- voices;
- locations;
- props;
- backgrounds;
- music themes;
- SFX;
- title/opening/closing assets;
- transitions;
- subtitle styles;
- camera presets.

Every episode references versioned asset IDs rather than copying anonymous prompts.

Example:

```text
milo-v1
milo-rig-v2
milo-voice-v1
forest-clearing-v3
series-main-theme-v1
```

---

## 15. Backlot Approval Gates

Do not wait until final render for human review.

Required configurable gates:

1. story approval;
2. character/canon approval;
3. storyboard/keyframe approval;
4. short motion-proof approval for new character/style combinations;
5. rough-cut approval;
6. final approval.

For routine weekly episodes using already approved series assets, earlier gates may be configured to auto-pass based on policy, but final approval remains explicit unless changed by the owner.

---

## 16. QA Harness — Independent Evaluators

The same worker/agent that creates an artifact cannot be the final evaluator of that artifact.

### Story Evaluator

Checks:

- age suitability;
- narrative coherence;
- lesson/theme integrity;
- character consistency;
- forbidden-content rules;
- scene coverage;
- pacing.

Failure routes back to Story Writer/Chronos.

### Technical Shot Evaluator

Checks:

- file exists;
- decode succeeds;
- duration tolerance;
- resolution/aspect;
- audio presence when required;
- black/frozen/corrupt frames;
- missing sections;
- obvious generation failure.

Failure routes to responsible production worker.

### Character Continuity Evaluator

Checks:

- identity;
- colors;
- proportions;
- clothing/accessories;
- key props;
- environment continuity;
- shot-to-shot continuity.

Failure routes to keyframe worker, motion worker, or planner according to cause.

### Creative Episode Evaluator

Checks:

- story readability;
- pacing;
- visual variety;
- character acting;
- dialogue support;
- music/SFX balance;
- continuity;
- child-viewer engagement;
- publishability.

Evaluator reports findings. It does not silently edit its own evaluated work.

---

## 17. Assembly

OpenMontage remains the assembly intelligence.

Final timeline assembly must support:

- ordered shot placement from shot manifest;
- exact shot durations;
- dialogue/narration tracks;
- ambient SFX;
- background music;
- music ducking;
- transitions;
- subtitles/captions;
- title/opening/closing sequences;
- credits if configured;
- Remotion/HyperFrames rendering where appropriate;
- FFmpeg final mux/encode;
- deterministic rebuild from manifest.

Assembly must be reproducible from stored manifests and accepted shot artifacts.

---

## 18. VPMS API Integration

Reuse the existing Phase 1 API rather than introducing a competing top-level API.

The new profile must be creatable through existing job creation semantics, for example:

```json
{
  "source_app": "kids-channel",
  "request_type": "kids_longform_movie",
  "content": {
    "series_id": "milo-adventures",
    "episode_ids": ["episode-001"],
    "production_package": "artifact://kids-batch-001"
  },
  "production": {
    "mode": "kids_longform_movie",
    "aspect_ratio": "16:9",
    "resolution": "1080p",
    "compute_policy": "auto"
  },
  "requested_outputs": ["long_video", "thumbnail", "metadata", "qa_report"],
  "idempotency_key": "kids-batch-001"
}
```

Add profile-specific endpoints only if the existing API cannot express required behavior. Prefer extending schemas over parallel APIs.

---

## 19. Deployment / Portability Contract

The component must provide a documented production launch path similar to:

```text
1. obtain production runtime image/source
2. mount model store
3. mount/download production package
4. provide environment configuration/secrets
5. run preflight
6. start VPMS batch runtime
7. produce artifacts
8. upload/sync receipts and outputs
9. stop runtime
```

Required configuration must come from environment/config files, never edited source code.

Recommended configuration groups:

```text
VPMS_*
STORAGE_*
MODEL_STORE_*
WORKER_*
FORGE_*
FRAMEPACK_*
H3_*
VMF_*
OPENMONTAGE_*
```

Secrets must never be written into production manifests or committed files.

---

## 20. Model Storage and Preflight

Before starting expensive production work, preflight must verify:

- required model files exist;
- checksums/version metadata are available where feasible;
- character references exist;
- required LoRAs/configs exist when requested;
- audio files exist;
- output disk has adequate free capacity;
- rendering tools are executable;
- all required workers pass health checks.

The runtime must fail fast before generation if required assets are missing.

Model and series asset storage should be independently mountable/persistent so production environments can be ephemeral.

---

## 21. Scheduling and Resource Management

Implement a scheduler that supports one or many available accelerator devices without application changes.

Scheduler must:

- query live workers;
- maintain worker leases;
- assign only compatible shots;
- respect worker concurrency;
- avoid duplicate generation;
- detect worker loss;
- requeue retryable work;
- prioritize critical-path shots;
- avoid leaving compatible devices idle while runnable work exists;
- allow different engines to share a compute target when safe;
- throttle when memory pressure or worker health degrades.

Do not implement distributed model-parallelism unless a specific engine requires it. Initial parallelism is job-level/shot-level parallelism.

---

## 22. Performance and Cost Telemetry

Every production run must collect enough evidence to make the next compute decision from measured data.

Record per worker/job:

- queue wait;
- setup/model-load time;
- generation time;
- output duration;
- output resolution;
- peak memory if observable;
- retries;
- failure reason;
- QA pass/fail;
- compute target ID;
- engine/model/version;
- monetary cost if available.

Derived metrics:

- generated video seconds per wall-clock hour;
- accepted video seconds per wall-clock hour;
- retry rate;
- QA rejection rate;
- cost per accepted finished minute;
- engine utilization;
- end-to-end episode completion time.

The system must not assume production capacity before benchmarking the selected compute target.

---

## 23. P0 Implementation Scope

### P0-A — Profile and schemas

- add `kids_longform_movie` pipeline/profile;
- add Series Bible schema;
- add Character Bible schema;
- add Episode Bible schema;
- add Scene Plan schema if missing/insufficient;
- add Shot Manifest schema;
- add Production Package schema;
- add Worker Receipt fields needed for shot-level production.

### P0-B — Portable runtime

- runtime preflight;
- hardware/resource discovery;
- compute-target descriptor;
- model-store abstraction;
- artifact-store abstraction;
- no provider-specific scheduling logic.

### P0-C — Worker adapters

Implement adapters with common contracts for:

- OpenMontage character animation;
- Forge-compatible keyframe generation;
- FramePack-compatible long motion;
- H3 LongMedia-compatible audio-aware motion;
- VMF integration/fallback.

Each adapter must have capability discovery, health, submit, poll/status, artifacts, cancel, receipts, and error mapping.

### P0-D — Scheduler

- shot queue;
- capability matching;
- worker leases;
- concurrency enforcement;
- retry/requeue;
- idempotency;
- restart reconciliation.

### P0-E — QA harness

- technical shot evaluator;
- character continuity evaluator contract;
- final technical evaluator;
- independent creative evaluator contract;
- route failures to responsible specialist.

### P0-F — Assembly

- assemble accepted shots from manifest;
- mix audio/music/SFX;
- subtitles;
- render final master;
- artifact registration;
- final QA;
- human approval.

---

## 24. P1 Scope

- automatic compute-provider launch/termination adapters;
- advanced runtime prediction based on historical benchmarks;
- cost-aware provisioning recommendations;
- dynamic worker role rebalancing;
- automatic reuse detection for recurring character performances;
- shot similarity/cache reuse;
- production dashboard for batch/episode/shot visualization;
- multi-language dubbing/localization;
- automatic derivative shorts/trailers;
- thumbnail/metadata pipeline;
- publishing integration.

P1 compute-provider integrations must remain plugins/adapters. They may never leak provider-specific logic into the production profile.

---

## 25. Harness / Diagram Loop Engineering Roles

Copilot must implement this system using separated responsibilities.

### Architecture Controller

Owns contracts, boundaries, schemas, naming, and integration consistency. Does not implement all workers.

### Runtime / Scheduler Specialist

Owns resource discovery, worker registration, queue, leases, retries, resume.

### Production Package Specialist

Owns series/episode/shot schemas and validators.

### Worker Adapter Specialists

Separate implementation responsibility for Forge, FramePack, H3, OpenMontage, and VMF adapters.

### Assembly Specialist

Owns manifest-driven Remotion/HyperFrames/FFmpeg assembly.

### Testing Specialist

Owns unit, contract, restart, failure, portability, and integration tests.

### Independent Evaluator

Reviews implementation evidence and acceptance criteria. Does not implement the code being evaluated.

Failures are routed back to the responsible specialist.

---

## 26. Required Tests

### Contract tests

- production package validates;
- shot manifest validates;
- worker capabilities validate;
- worker receipts validate;
- unknown worker can register via standard contract;
- incompatible worker is never assigned an incompatible shot.

### Portability tests

The exact same synthetic production package must execute in at least two different runtime configurations without source-code changes. Differences may be configuration/environment only.

Tests must prove:

- one accelerator configuration works;
- multiple accelerator configuration works;
- CPU-only preflight reports unsupported GPU tasks cleanly rather than crashing;
- worker absence triggers fallback/blocking according to policy;
- no device/vendor name is required in episode manifests.

### Restart tests

Interrupt after:

- several accepted shots;
- active worker job;
- before assembly;
- during assembly.

After restart, accepted artifacts must be preserved and only incomplete work resumed.

### Failure tests

- corrupted video artifact;
- worker timeout;
- lost worker;
- insufficient disk;
- missing model;
- failed QA;
- repeated shot failure;
- unavailable preferred engine;
- artifact upload failure.

### End-to-end synthetic test

```text
create kids_longform_movie job
-> validate production package
-> register mock workers
-> classify shots
-> dispatch jobs
-> collect receipts
-> QA shots
-> assemble episode
-> final QA
-> human approval
-> READY
```

---

## 27. Definition of Done — Component Build

The component is NOT complete because files/classes exist.

P0 is complete only when evidence proves:

1. `kids_longform_movie` is a valid VPMS/OpenMontage production profile.
2. A production package containing a series, characters, one episode, scenes, and shots validates.
3. Runtime preflight discovers resources without hardcoded hardware.
4. At least three distinct production capability classes can register as workers through the shared contract.
5. The scheduler routes different shot types to compatible workers.
6. A worker failure can be retried/requeued without losing accepted shots.
7. The runtime survives restart and resumes from persisted state.
8. OpenMontage can assemble accepted mock/real shot artifacts into a final episode timeline.
9. Technical QA produces evidence.
10. Independent evaluator results are persisted separately from generator output.
11. Human approval moves the episode to `READY`.
12. The exact same test production package runs under at least two different compute configurations using configuration changes only.
13. No scheduling or story schema contains a hardcoded GPU model, cloud provider, or fixed machine count.
14. Existing OpenMontage pipelines and tests remain functional.

---

## 28. First Real Production Qualification

After P0 passes synthetic tests, qualify the system progressively using real kids-animation assets.

Recommended qualification sequence:

```text
short pilot
-> verify character continuity
-> verify audio timing
-> verify worker routing
-> verify restart/retry
-> verify assembly

medium episode
-> measure real throughput
-> measure QA rejection rate
-> measure runtime/cost
-> validate reusable series assets

full-length episode
-> choose compute target based on measured evidence
-> run production batch
-> produce final master
-> record benchmark
```

The compute environment for the first full-length production is intentionally NOT specified in this PRD. It will be selected after the system is built and benchmark evidence is available.

---

## 29. Copilot Build Instruction

Before writing code:

1. read `docs/current-state-audit.md`;
2. read `docs/ARCHITECTURE.md`;
3. read `docs/api-contracts.md`;
4. read `docs/capability-registry.md`;
5. read `docs/job-state-machine.md`;
6. inspect `pipeline_defs/character-animation.yaml`;
7. inspect existing schemas, tool registry, checkpoint system, Remotion composer, Backlot, tests, and any existing worker adapters;
8. produce a written implementation map showing what already exists and what is genuinely missing;
9. reuse existing code and contracts wherever possible;
10. implement additively.

Do not start by replacing OpenMontage orchestration, provider selectors, checkpoints, Backlot, Remotion, HyperFrames, VMF, or existing VPMS APIs.

### Required implementation report

Create `KIDS_LONGFORM_P0_COMPLETION_REPORT.md` containing:

- files changed;
- architecture decisions;
- schemas added/extended;
- adapters implemented;
- runtime discovery evidence;
- scheduler evidence;
- portability evidence;
- restart evidence;
- QA evidence;
- tests executed with exact commands;
- passing/failing counts;
- known limitations;
- next recommended production qualification step.

No completion claim is valid without this evidence.
