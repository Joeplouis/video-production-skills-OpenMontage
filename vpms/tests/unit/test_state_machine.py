"""
VPMS Unit Tests — State Machine
"""

import pytest
from vpms.core.state_machine import JobState, JobStateMachine, InvalidTransitionError


class TestJobStateMachine:
    """Test the job state machine transitions."""

    def setup_method(self):
        self.sm = JobStateMachine()

    # ─── Valid Transitions ────────────────────────────────────────────────────────

    def test_created_to_queued(self):
        """CREATED -> QUEUED is valid."""
        new_state = self.sm.transition(JobState.CREATED, JobState.QUEUED)
        assert new_state == JobState.QUEUED

    def test_created_to_cancelled(self):
        """CREATED -> CANCELLED is valid."""
        new_state = self.sm.transition(JobState.CREATED, JobState.CANCELLED)
        assert new_state == JobState.CANCELLED

    def test_dispatching_to_asset_generation(self):
        """DISPATCHING -> ASSET_GENERATION is valid."""
        new_state = self.sm.transition(JobState.DISPATCHING, JobState.ASSET_GENERATION)
        assert new_state == JobState.ASSET_GENERATION

    def test_asset_generation_to_rendering(self):
        """ASSET_GENERATION -> RENDERING is valid."""
        new_state = self.sm.transition(JobState.ASSET_GENERATION, JobState.RENDERING)
        assert new_state == JobState.RENDERING

    def test_rendering_to_provider_confirmed(self):
        """RENDERING -> PROVIDER_CONFIRMED is valid."""
        new_state = self.sm.transition(JobState.RENDERING, JobState.PROVIDER_CONFIRMED)
        assert new_state == JobState.PROVIDER_CONFIRMED

    def test_provider_confirmed_to_output_verification(self):
        """PROVIDER_CONFIRMED -> OUTPUT_VERIFICATION is valid."""
        new_state = self.sm.transition(
            JobState.PROVIDER_CONFIRMED, JobState.OUTPUT_VERIFICATION
        )
        assert new_state == JobState.OUTPUT_VERIFICATION

    def test_output_verification_to_technical_qa(self):
        """OUTPUT_VERIFICATION -> TECHNICAL_QA is valid."""
        new_state = self.sm.transition(
            JobState.OUTPUT_VERIFICATION, JobState.TECHNICAL_QA
        )
        assert new_state == JobState.TECHNICAL_QA

    def test_technical_qa_to_creative_qa(self):
        """TECHNICAL_QA -> CREATIVE_QA is valid."""
        new_state = self.sm.transition(JobState.TECHNICAL_QA, JobState.CREATIVE_QA)
        assert new_state == JobState.CREATIVE_QA

    def test_creative_qa_to_waiting_for_final_approval(self):
        """CREATIVE_QA -> WAITING_FOR_FINAL_APPROVAL is valid."""
        new_state = self.sm.transition(
            JobState.CREATIVE_QA, JobState.WAITING_FOR_FINAL_APPROVAL
        )
        assert new_state == JobState.WAITING_FOR_FINAL_APPROVAL

    def test_waiting_final_approval_to_ready(self):
        """WAITING_FOR_FINAL_APPROVAL -> READY is valid."""
        new_state = self.sm.transition(
            JobState.WAITING_FOR_FINAL_APPROVAL, JobState.READY
        )
        assert new_state == JobState.READY

    def test_ready_to_publish_requested(self):
        """READY -> PUBLISH_REQUESTED is valid."""
        new_state = self.sm.transition(JobState.READY, JobState.PUBLISH_REQUESTED)
        assert new_state == JobState.PUBLISH_REQUESTED

    def test_publish_requested_to_scheduled(self):
        """PUBLISH_REQUESTED -> SCHEDULED is valid."""
        new_state = self.sm.transition(JobState.PUBLISH_REQUESTED, JobState.SCHEDULED)
        assert new_state == JobState.SCHEDULED

    def test_scheduled_to_published(self):
        """SCHEDULED -> PUBLISHED is valid."""
        new_state = self.sm.transition(JobState.SCHEDULED, JobState.PUBLISHED)
        assert new_state == JobState.PUBLISHED

    # ─── Failure States ─────────────────────────────────────────────────────────

    def test_retryable_failure_can_retry(self):
        """RETRYABLE_FAILURE can retry via QUEUED."""
        new_state = self.sm.transition(JobState.RETRYABLE_FAILURE, JobState.QUEUED)
        assert new_state == JobState.QUEUED

    def test_dispatching_to_retryable_failure(self):
        """DISPATCHING -> RETRYABLE_FAILURE is valid."""
        new_state = self.sm.transition(
            JobState.DISPATCHING, JobState.RETRYABLE_FAILURE
        )
        assert new_state == JobState.RETRYABLE_FAILURE

    # ─── Invalid Transitions ────────────────────────────────────────────────────

    def test_created_to_ready_is_invalid(self):
        """CREATED -> READY is NOT valid (no skip)."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            self.sm.transition(JobState.CREATED, JobState.READY)
        assert "CREATED" in str(exc_info.value)
        assert "READY" in str(exc_info.value)

    def test_dispatching_to_complete_is_invalid(self):
        """DISPATCHING -> READY is NOT valid (requires receipt)."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            self.sm.transition(JobState.DISPATCHING, JobState.READY)
        assert "DISPATCHING" in str(exc_info.value)

    def test_created_to_published_is_invalid(self):
        """CREATED -> PUBLISHED is NOT valid (terminal skip)."""
        with pytest.raises(InvalidTransitionError):
            self.sm.transition(JobState.CREATED, JobState.PUBLISHED)

    def test_cancelled_is_terminal(self):
        """CANCELLED is terminal — no transitions allowed."""
        with pytest.raises(InvalidTransitionError):
            self.sm.transition(JobState.CANCELLED, JobState.QUEUED)

    def test_failed_is_terminal(self):
        """FAILED is terminal."""
        with pytest.raises(InvalidTransitionError):
            self.sm.transition(JobState.FAILED, JobState.QUEUED)

    def test_rejected_is_terminal(self):
        """REJECTED is terminal."""
        with pytest.raises(InvalidTransitionError):
            self.sm.transition(JobState.REJECTED, JobState.QUEUED)

    def test_published_is_terminal(self):
        """PUBLISHED is terminal."""
        with pytest.raises(InvalidTransitionError):
            self.sm.transition(JobState.PUBLISHED, JobState.READY)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def test_can_transition_returns_bool(self):
        """can_transition returns True/False without raising."""
        assert self.sm.can_transition(JobState.CREATED, JobState.QUEUED) is True
        assert self.sm.can_transition(JobState.CREATED, JobState.READY) is False

    def test_get_allowed_transitions(self):
        """get_allowed_transitions returns valid next states."""
        allowed = self.sm.get_allowed_transitions(JobState.CREATED)
        assert JobState.QUEUED in allowed
        assert JobState.CANCELLED in allowed
        assert JobState.READY not in allowed

    def test_is_terminal(self):
        """is_terminal identifies terminal states."""
        assert self.sm.is_terminal(JobState.CANCELLED) is True
        assert self.sm.is_terminal(JobState.FAILED) is True
        assert self.sm.is_terminal(JobState.PUBLISHED) is True
        assert self.sm.is_terminal(JobState.CREATED) is False
        assert self.sm.is_terminal(JobState.QUEUED) is False

    def test_is_success(self):
        """is_success identifies successful terminal states."""
        assert self.sm.is_success(JobState.PUBLISHED) is True
        assert self.sm.is_success(JobState.READY) is False
        assert self.sm.is_success(JobState.FAILED) is False

    def test_is_failure(self):
        """is_failure identifies failure terminal states."""
        assert self.sm.is_failure(JobState.FAILED) is True
        assert self.sm.is_failure(JobState.REJECTED) is True
        assert self.sm.is_failure(JobState.CANCELLED) is True
        assert self.sm.is_failure(JobState.PUBLISHED) is False

    def test_is_waiting_approval(self):
        """is_waiting_approval identifies approval gates."""
        assert self.sm.is_waiting_approval(JobState.WAITING_FOR_PRODUCTION_APPROVAL) is True
        assert self.sm.is_waiting_approval(JobState.WAITING_FOR_FINAL_APPROVAL) is True
        assert self.sm.is_waiting_approval(JobState.READY) is False
