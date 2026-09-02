"""
VPMS Unit Tests — Event Ledger
"""

import pytest
from datetime import datetime, timezone
from vpms.core.event_ledger import EventLedger, JobEvent, EventType


class TestEventLedger:
    """Test the event ledger."""

    def setup_method(self):
        self.ledger = EventLedger()  # in-memory

    def test_append_creates_event(self):
        """Appending an event returns a JobEvent."""
        event = self.ledger.append(
            job_id="vpms_test123",
            event_type=EventType.JOB_CREATED,
            new_state="CREATED",
        )
        assert event.event_id.startswith("evt_")
        assert event.job_id == "vpms_test123"
        assert event.event_type == EventType.JOB_CREATED
        assert event.new_state == "CREATED"

    def test_append_with_metadata(self):
        """Events can carry metadata."""
        event = self.ledger.append(
            job_id="vpms_test123",
            event_type=EventType.WORKER_DISPATCHED,
            previous_state="DISPATCHING",
            new_state="ASSET_GENERATION",
            worker="vmf",
            metadata={"worker_job_id": "wrkj_abc123"},
        )
        assert event.worker == "vmf"
        assert event.extra_data["worker_job_id"] == "wrkj_abc123"

    def test_get_events_for_job(self):
        """get_events_for_job returns events in order."""
        for i in range(3):
            self.ledger.append(
                job_id="vpms_test123",
                event_type=EventType.STATE_TRANSITION,
                new_state=f"STATE_{i}",
            )
        # Add event for different job
        self.ledger.append(
            job_id="vpms_other",
            event_type=EventType.JOB_CREATED,
            new_state="CREATED",
        )

        events = self.ledger.get_events_for_job("vpms_test123")
        assert len(events) == 3
        assert events[0].new_state == "STATE_0"
        assert events[2].new_state == "STATE_2"

    def test_get_latest_event(self):
        """get_latest_event returns the most recent event."""
        self.ledger.append(
            job_id="vpms_test123", event_type=EventType.JOB_CREATED, new_state="CREATED"
        )
        self.ledger.append(
            job_id="vpms_test123", event_type=EventType.JOB_QUEUED, new_state="QUEUED"
        )
        latest = self.ledger.get_latest_event("vpms_test123")
        assert latest.event_type == EventType.JOB_QUEUED
        assert latest.new_state == "QUEUED"

    def test_get_latest_event_returns_none_for_unknown_job(self):
        """Unknown job returns None."""
        assert self.ledger.get_latest_event("vpms_unknown") is None

    def test_count_events(self):
        """count_events returns the number of events for a job."""
        for _ in range(5):
            self.ledger.append(
                job_id="vpms_test123",
                event_type=EventType.STATE_TRANSITION,
            )
        assert self.ledger.count_events("vpms_test123") == 5
        assert self.ledger.count_events("vpms_other") == 0


class TestJobEvent:
    """Test the JobEvent model."""

    def test_job_event_generates_id(self):
        """JobEvent auto-generates an event_id."""
        event = JobEvent(job_id="vpms_test", event_type=EventType.JOB_CREATED)
        assert event.event_id.startswith("evt_")
        assert len(event.event_id) == 20  # evt_ + 16 hex chars

    def test_job_event_has_timestamp(self):
        """JobEvent has an auto-generated UTC timestamp."""
        before = datetime.now(timezone.utc)
        event = JobEvent(job_id="vpms_test", event_type=EventType.JOB_CREATED)
        after = datetime.now(timezone.utc)
        assert before <= event.timestamp <= after

    def test_job_event_defaults_to_empty_metadata(self):
        """JobEvent defaults metadata to empty dict."""
        event = JobEvent(job_id="vpms_test", event_type=EventType.JOB_CREATED)
        assert event.extra_data == {}
