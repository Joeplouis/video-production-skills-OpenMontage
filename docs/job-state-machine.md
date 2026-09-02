# VPMS Job State Machine

## Overview

The VPMS job state machine (`vpms/core/state_machine.py`) is the **canonical authority** on job lifecycle state. All transitions go through `JobManager.transition_state()`, which:

1. Validates the transition against the `TRANSITIONS` map
2. Raises `InvalidTransitionError` if the transition is not allowed
3. Returns the new state for the caller to persist
4. Emits a `job_events` record for every transition

**Key rule**: No code may mutate `job.status` directly. All transitions must pass through `JobManager`.

**Key rule**: Workers cannot go `DISPATCHING → COMPLETE`. They go `DISPATCHING → ASSET_GENERATION → RENDERING → PROVIDER_CONFIRMED` (via worker receipt).

---

## All States

### Normal Progression

| State | Description |
|---|---|
| `CREATED` | Job record exists, not yet queued |
| `QUEUED` | Job accepted, waiting to be processed |
| `PLANNING` | Production planning in progress |
| `RESEARCHING` | Content research in progress |
| `RESEARCH_READY` | Research complete, ready for scripting |
| `SCRIPTING` | Script writing in progress |
| `SCRIPT_EVALUATING` | Script under independent review |
| `SCRIPT_APPROVED` | Script approved by evaluator |
| `PRODUCTION_PLANNING` | Production plan being prepared |
| `WAITING_FOR_PRODUCTION_APPROVAL` | Awaiting human production gate |
| `PRODUCTION_APPROVED` | Production plan approved |
| `DISPATCHING` | Job dispatched to worker |
| `ASSET_GENERATION` | Worker is generating assets |
| `RENDERING` | Worker is rendering output |
| `PROVIDER_CONFIRMED` | Provider confirmed asset ready |
| `OUTPUT_VERIFICATION` | Verifying output integrity |
| `TECHNICAL_QA` | Automated technical QA |
| `CREATIVE_QA` | Automated creative QA |
| `WAITING_FOR_FINAL_APPROVAL` | Awaiting human final approval |
| `READY` | Job complete, ready for publish |
| `PUBLISH_REQUESTED` | Publish requested |
| `SCHEDULED` | Publish scheduled |
| `PUBLISHED` | Published (terminal success) |

### Failure / Non-Success Terminal States

| State | Description |
|---|---|
| `RETRYABLE_FAILURE` | Failed but eligible for retry |
| `FAILED` | Permanent failure (terminal) |
| `BLOCKED` | Blocked, can retry or cancel |
| `REJECTED` | Rejected at approval gate (terminal) |
| `CANCELLED` | Cancelled by user (terminal) |

---

## Valid Transitions

### Normal Forward Flow

```
CREATED → QUEUED → PLANNING → RESEARCHING → RESEARCH_READY
  → SCRIPTING → SCRIPT_EVALUATING → SCRIPT_APPROVED
  → PRODUCTION_PLANNING → WAITING_FOR_PRODUCTION_APPROVAL
  → PRODUCTION_APPROVED → DISPATCHING
  → ASSET_GENERATION → RENDERING → PROVIDER_CONFIRMED
  → OUTPUT_VERIFICATION → TECHNICAL_QA → CREATIVE_QA
  → WAITING_FOR_FINAL_APPROVAL → READY
  → PUBLISH_REQUESTED → SCHEDULED → PUBLISHED
```

### Approval Gates

- `WAITING_FOR_PRODUCTION_APPROVAL` → `PRODUCTION_APPROVED` (approve) or `REJECTED` (reject) or `CANCELLED`
- `WAITING_FOR_FINAL_APPROVAL` → `READY` (approve) or `REJECTED` or `CANCELLED`

### Cancellation Path

Any non-terminal state can transition to `CANCELLED` (except `REJECTED`, `FAILED`, `CANCELLED`, `PUBLISHED`).

### Retry Path

`RETRYABLE_FAILURE` → `QUEUED` (re-queue) or `DISPATCHING` (re-dispatch) or `FAILED` (escalate) or `BLOCKED`.

### Block Path

`PLANNING`, `DISPATCHING`, `ASSET_GENERATION`, `RENDERING`, `PROVIDER_CONFIRMED`, `TECHNICAL_QA`, `CREATIVE_QA` can transition to `BLOCKED`.

---

## Transition Rules (Code Reference)

```python
# vpms/core/state_machine.py

TRANSITIONS: dict[JobState, Set[JobState]] = {
    JobState.CREATED: {JobState.QUEUED, JobState.CANCELLED},
    JobState.QUEUED: {JobState.PLANNING, JobState.CANCELLED},
    JobState.PLANNING: {JobState.RESEARCHING, JobState.CANCELLED, JobState.BLOCKED},
    JobState.RESEARCHING: {JobState.RESEARCH_READY, JobState.RETRYABLE_FAILURE, JobState.FAILED},
    # ... (see source for full map)
    JobState.RETRYABLE_FAILURE: {JobState.QUEUED, JobState.DISPATCHING, JobState.FAILED, JobState.BLOCKED},
    JobState.FAILED: set(),         # terminal
    JobState.REJECTED: set(),        # terminal
    JobState.CANCELLED: set(),      # terminal
    JobState.PUBLISHED: set(),      # terminal
}
```

---

## Worker Receipt Requirement

Workers must NOT return `COMPLETED` directly. The required path:

1. Worker accepts job → VPMS state: `DISPATCHING`
2. Worker sends receipt with status `PROVIDER_CONFIRMED` → VPMS state: `PROVIDER_CONFIRMED`
3. Worker sends receipt with status `COMPLETED` → VPMS state: `READY` (after QA + approval)

This is enforced by `vpms/core/dispatcher.py:process_receipt()`.

---

## Test Evidence

See `vpms/tests/unit/test_state_machine.py` for all transition tests:

- Valid transitions: CREATED→QUEUED, DISPATCHING→ASSET_GENERATION, etc.
- Invalid transitions: CREATED→READY (no skip), DISPATCHING→READY (requires receipt)
- Terminal states: CANCELLED→QUEUED raises `InvalidTransitionError`
- Helper methods: `can_transition()`, `get_allowed_transitions()`, `is_terminal()`, `is_success()`, `is_failure()`, `is_waiting_approval()`
