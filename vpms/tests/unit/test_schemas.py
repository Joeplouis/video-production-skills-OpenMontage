"""
VPMS Unit Tests — API Schemas
"""

import pytest
from pydantic import ValidationError
from vpms.api.schemas import (
    ContentJobRequest,
    VideoJobRequest,
    JobStatusResponse,
    ApprovalRequest,
    CancelRequest,
)


class TestContentJobRequest:
    """Test ContentJobRequest schema validation."""

    def test_valid_request(self):
        """Valid request passes."""
        req = ContentJobRequest(
            source_app="podcast-factory",
            request_type="podcast_episode",
            content={"topic": "AI agents", "audience": "SMB owners"},
            production={"mode": "podcast_hybrid", "speakers": 2},
            idempotency_key="podcast-001-2024",
            priority=5,
        )
        assert req.source_app == "podcast-factory"
        assert req.priority == 5

    def test_missing_required_fields(self):
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            ContentJobRequest()  # missing source_app, request_type, content

    def test_priority_bounds(self):
        """Priority must be 1-10."""
        req = ContentJobRequest(
            source_app="test",
            request_type="test",
            content={},
            priority=1,
        )
        assert req.priority == 1

        with pytest.raises(ValidationError):
            ContentJobRequest(
                source_app="test",
                request_type="test",
                content={},
                priority=11,  # out of bounds
            )


class TestVideoJobRequest:
    """Test VideoJobRequest schema validation."""

    def test_valid_video_job(self):
        """Valid video job passes."""
        req = VideoJobRequest(
            source_app="bookfactory",
            request_type="book_trailer",
            content={"title": "My Book", "description": "A great book"},
            budget={"maximum_usd": 5.0},
        )
        assert req.request_type == "book_trailer"
        assert req.budget["maximum_usd"] == 5.0

    def test_default_priority(self):
        """Default priority is 5."""
        req = VideoJobRequest(
            source_app="test",
            request_type="test",
            content={},
        )
        assert req.priority == 5


class TestApprovalRequest:
    """Test ApprovalRequest schema validation."""

    def test_approved_decision(self):
        """APPROVED is valid."""
        req = ApprovalRequest(
            decision="APPROVED",
            approved_by="admin@example.com",
            notes="Looks good",
        )
        assert req.decision == "APPROVED"

    def test_rejected_decision(self):
        """REJECTED is valid."""
        req = ApprovalRequest(
            decision="REJECTED",
            approved_by="admin@example.com",
            notes="Needs revision",
        )
        assert req.decision == "REJECTED"

    def test_invalid_decision(self):
        """Invalid decision is rejected."""
        with pytest.raises(ValidationError):
            ApprovalRequest(decision="MAYBE")  # not APPROVED or REJECTED


class TestCancelRequest:
    """Test CancelRequest schema validation."""

    def test_cancel_with_reason(self):
        """Cancel with reason passes."""
        req = CancelRequest(reason="User requested cancellation")
        assert req.reason == "User requested cancellation"

    def test_cancel_without_reason(self):
        """Cancel without reason passes (reason is optional)."""
        req = CancelRequest()
        assert req.reason is None
