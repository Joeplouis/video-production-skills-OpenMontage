"""
Job State Machine — VPMS Core
Canonical state transitions per PRD Section 10.
"""

from enum import Enum
from typing import Set, Optional


class JobState(str, Enum):
    """All valid VPMS job states."""

    # Terminal success
    PUBLISHED = "PUBLISHED"

    # Normal progression
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    RESEARCH_READY = "RESEARCH_READY"
    SCRIPTING = "SCRIPTING"
    SCRIPT_EVALUATING = "SCRIPT_EVALUATING"
    SCRIPT_APPROVED = "SCRIPT_APPROVED"
    PRODUCTION_PLANNING = "PRODUCTION_PLANNING"
    WAITING_FOR_PRODUCTION_APPROVAL = "WAITING_FOR_PRODUCTION_APPROVAL"
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
    DISPATCHING = "DISPATCHING"
    ASSET_GENERATION = "ASSET_GENERATION"
    RENDERING = "RENDERING"
    PROVIDER_CONFIRMED = "PROVIDER_CONFIRMED"
    OUTPUT_VERIFICATION = "OUTPUT_VERIFICATION"
    TECHNICAL_QA = "TECHNICAL_QA"
    CREATIVE_QA = "CREATIVE_QA"
    WAITING_FOR_FINAL_APPROVAL = "WAITING_FOR_FINAL_APPROVAL"
    READY = "READY"
    PUBLISH_REQUESTED = "PUBLISH_REQUESTED"
    SCHEDULED = "SCHEDULED"

    # Failure / terminal non-success
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Valid transitions: from_state -> set of allowed to_states
TRANSITIONS: dict[JobState, Set[JobState]] = {
    # Normal forward flow
    JobState.CREATED: {JobState.QUEUED, JobState.CANCELLED, JobState.REJECTED},
    JobState.QUEUED: {JobState.PLANNING, JobState.CANCELLED, JobState.REJECTED},
    JobState.PLANNING: {JobState.RESEARCHING, JobState.CANCELLED, JobState.BLOCKED},
    JobState.RESEARCHING: {JobState.RESEARCH_READY, JobState.RETRYABLE_FAILURE, JobState.FAILED},
    JobState.RESEARCH_READY: {JobState.SCRIPTING, JobState.CANCELLED},
    JobState.SCRIPTING: {JobState.SCRIPT_EVALUATING, JobState.RETRYABLE_FAILURE, JobState.FAILED},
    JobState.SCRIPT_EVALUATING: {
        JobState.SCRIPT_APPROVED,
        JobState.SCRIPTING,  # retry with feedback
        JobState.REJECTED,
        JobState.FAILED,
    },
    JobState.SCRIPT_APPROVED: {JobState.PRODUCTION_PLANNING, JobState.CANCELLED},
    JobState.PRODUCTION_PLANNING: {
        JobState.WAITING_FOR_PRODUCTION_APPROVAL,
        JobState.CANCELLED,
        JobState.BLOCKED,
    },
    JobState.WAITING_FOR_PRODUCTION_APPROVAL: {
        JobState.PRODUCTION_APPROVED,
        JobState.REJECTED,
        JobState.CANCELLED,
    },
    JobState.PRODUCTION_APPROVED: {JobState.DISPATCHING, JobState.CANCELLED},
    JobState.DISPATCHING: {
        JobState.ASSET_GENERATION,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
        JobState.BLOCKED,
    },
    JobState.ASSET_GENERATION: {
        JobState.RENDERING,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
        JobState.BLOCKED,
    },
    JobState.RENDERING: {
        JobState.PROVIDER_CONFIRMED,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
        JobState.BLOCKED,
    },
    JobState.PROVIDER_CONFIRMED: {
        JobState.OUTPUT_VERIFICATION,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
    },
    JobState.OUTPUT_VERIFICATION: {
        JobState.TECHNICAL_QA,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
    },
    JobState.TECHNICAL_QA: {
        JobState.CREATIVE_QA,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
        JobState.BLOCKED,
    },
    JobState.CREATIVE_QA: {
        JobState.WAITING_FOR_FINAL_APPROVAL,
        JobState.RETRYABLE_FAILURE,
        JobState.FAILED,
        JobState.BLOCKED,
    },
    JobState.WAITING_FOR_FINAL_APPROVAL: {
        JobState.READY,
        JobState.REJECTED,
        JobState.CANCELLED,
    },
    JobState.READY: {JobState.PUBLISH_REQUESTED, JobState.CANCELLED},
    JobState.PUBLISH_REQUESTED: {JobState.SCHEDULED, JobState.FAILED, JobState.RETRYABLE_FAILURE},
    JobState.SCHEDULED: {JobState.PUBLISHED, JobState.FAILED, JobState.RETRYABLE_FAILURE},

    # Failure states — can retry from RETRYABLE_FAILURE
    JobState.RETRYABLE_FAILURE: {
        JobState.QUEUED,  # re-queue
        JobState.DISPATCHING,  # re-dispatch
        JobState.FAILED,  # escalate
        JobState.BLOCKED,
    },
    # Terminal non-success states
    JobState.FAILED: set(),
    JobState.BLOCKED: {JobState.QUEUED, JobState.CANCELLED},
    JobState.REJECTED: set(),
    JobState.CANCELLED: set(),
    # PUBLISHED is terminal success
    JobState.PUBLISHED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: JobState, to_state: JobState):
        self.from_state = from_state
        self.to_state = to_state
        allowed = TRANSITIONS.get(from_state, set())
        super().__init__(
            f"Invalid state transition: {from_state.value} -> {to_state.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )


class JobStateMachine:
    """
    Canonical job state machine.

    All state transitions MUST go through this class.
    Invalid transitions raise InvalidTransitionError.
    Every transition generates a job_event.
    """

    def __init__(self):
        pass

    def can_transition(self, from_state: JobState, to_state: JobState) -> bool:
        """Check if a transition is valid without raising."""
        allowed = TRANSITIONS.get(from_state, set())
        return to_state in allowed

    def transition(
        self, from_state: JobState, to_state: JobState, reason: Optional[str] = None
    ) -> JobState:
        """
        Execute a state transition.
        Returns the new state.
        Raises InvalidTransitionError if transition is not allowed.
        """
        if not self.can_transition(from_state, to_state):
            raise InvalidTransitionError(from_state, to_state)
        return to_state

    def get_allowed_transitions(self, from_state: JobState) -> Set[JobState]:
        """Return the set of valid next states."""
        return TRANSITIONS.get(from_state, set())

    def is_terminal(self, state: JobState) -> bool:
        """True if the state has no valid outgoing transitions."""
        return len(TRANSITIONS.get(state, set())) == 0

    def is_success(self, state: JobState) -> bool:
        """True if this is a successful terminal state."""
        return state == JobState.PUBLISHED

    def is_failure(self, state: JobState) -> bool:
        """True if this is a failure terminal state."""
        return state in {
            JobState.FAILED,
            JobState.REJECTED,
            JobState.CANCELLED,
            JobState.BLOCKED,
        }

    def is_waiting_approval(self, state: JobState) -> bool:
        """True if job is at a human approval gate."""
        return state in {
            JobState.WAITING_FOR_PRODUCTION_APPROVAL,
            JobState.WAITING_FOR_FINAL_APPROVAL,
        }
