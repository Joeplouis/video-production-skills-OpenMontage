"""
VPMS Integration Tests — API + Database
Tests the full API flow with real database.
"""

import os
import pytest
from datetime import datetime, timezone

# Set test database URL
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://empire:empire_pass_2026@localhost:5435/affiliates_autopilot"
)

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from vpms.main import app
from vpms.db.session import engine, SessionLocal
from vpms.db.models import Base


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db_session():
    """Get a database session for the test module."""
    # Run migration
    with engine.begin() as conn:
        # Check if vpms schema exists
        result = conn.execute(
            text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'vpms'")
        ).fetchone()

        if not result:
            # Run migration
            from pathlib import Path
            migration_path = Path(__file__).parent.parent.parent / "db" / "migrations" / "001_create_vpms_schema.sql"
            if migration_path.exists():
                conn.execute(text(migration_path.read_text()))
                conn.commit()

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client():
    """Get a FastAPI test client."""
    return TestClient(app)


# ─── Health Tests ─────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Test the health endpoint."""

    def test_root_health(self, client):
        """GET /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_api_health(self, client):
        """GET /api/v1/health returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ─── Job Creation Tests ───────────────────────────────────────────────────────


class TestContentJobCreation:
    """Test content job creation endpoint."""

    def test_create_content_job(self, client):
        """POST /api/v1/content/jobs creates a job and returns immediately."""
        response = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {
                    "topic": "How AI agents help small businesses",
                    "audience": "SMB owners",
                },
                "production": {
                    "mode": "podcast_hybrid",
                    "speakers": 2,
                    "aspect_ratio": "16:9",
                },
                "requested_outputs": ["long_video", "shorts", "thumbnail"],
                "budget": {"maximum_usd": 5.0},
                "idempotency_key": "test-content-job-001",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("vpms_")
        assert data["status"] == "QUEUED"
        assert "created_at" in data

    def test_idempotent_content_job(self, client):
        """Same idempotency key returns existing job."""
        idempotency_key = "test-idempotent-001"

        # First request
        r1 = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Idempotency Test"},
                "idempotency_key": idempotency_key,
            },
        )
        assert r1.status_code == 201
        job_id_1 = r1.json()["job_id"]

        # Second request with same key
        r2 = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Different topic"},
                "idempotency_key": idempotency_key,
            },
        )
        assert r2.status_code == 201
        job_id_2 = r2.json()["job_id"]

        # Same job returned
        assert job_id_1 == job_id_2


class TestVideoJobCreation:
    """Test video job creation endpoint."""

    def test_create_video_job(self, client):
        """POST /api/v1/video/jobs creates a job."""
        response = client.post(
            "/api/v1/video/jobs",
            json={
                "source_app": "bookfactory",
                "request_type": "book_trailer",
                "content": {
                    "title": "The AI Revolution",
                    "description": "A compelling book trailer",
                },
                "production": {
                    "aspect_ratio": "16:9",
                    "resolution": "1080p",
                },
                "budget": {"maximum_usd": 3.0},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "QUEUED"


# ─── Job Retrieval Tests ──────────────────────────────────────────────────────


class TestJobRetrieval:
    """Test job retrieval endpoints."""

    def test_get_job_detail(self, client):
        """GET /api/v1/jobs/:id returns job details."""
        # Create a job first
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Retrieval Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        # Get details
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job_id
        assert data["job_type"] == "content"
        assert data["status"] == "QUEUED"

    def test_get_job_status(self, client):
        """GET /api/v1/jobs/:id/status returns lightweight status."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Status Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "QUEUED"
        assert "created_at" in data

    def test_get_job_events(self, client):
        """GET /api/v1/jobs/:id/events returns event history."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Events Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/events")
        assert response.status_code == 200
        events = response.json()
        assert len(events) >= 2  # JOB_CREATED + JOB_QUEUED
        event_types = [e["event_type"] for e in events]
        assert "JOB_CREATED" in event_types
        assert "JOB_QUEUED" in event_types

    def test_get_nonexistent_job(self, client):
        """GET /api/v1/jobs/:id returns 404 for unknown job."""
        response = client.get("/api/v1/jobs/vpms_nonexistent12345")
        assert response.status_code == 404


# ─── Cancel Tests ─────────────────────────────────────────────────────────────


class TestJobCancellation:
    """Test job cancellation."""

    def test_cancel_queued_job(self, client):
        """POST /api/v1/jobs/:id/cancel cancels a job."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Cancel Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        response = client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            json={"reason": "Test cancellation"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "CANCELLED"
        assert "cancelled" in data["message"].lower()

    def test_cancel_cancelled_job_fails(self, client):
        """Cancelling an already-cancelled job fails."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Double Cancel Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        # First cancel
        client.post(f"/api/v1/jobs/{job_id}/cancel")

        # Second cancel should fail
        response = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert response.status_code == 400


# ─── Approval Tests ───────────────────────────────────────────────────────────


class TestJobApproval:
    """Test job approval endpoints."""

    def test_approval_at_final_gate(self, client):
        """Job must be at an approval gate to approve."""
        # Create job and manually transition to WAITING_FOR_FINAL_APPROVAL
        # (in real flow this happens through the state machine)
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Approval Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        # This should fail because job is at QUEUED, not at an approval gate
        response = client.post(
            f"/api/v1/jobs/{job_id}/approve",
            json={"decision": "APPROVED", "approved_by": "test@example.com"},
        )
        assert response.status_code == 400

    def test_reject_job(self, client):
        """POST /api/v1/jobs/:id/reject rejects a job."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Reject Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        response = client.post(
            f"/api/v1/jobs/{job_id}/reject",
            json={
                "decision": "REJECTED",
                "approved_by": "test@example.com",
                "notes": "Does not meet quality standards",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "REJECTED"


# ─── Worker Registry Tests ───────────────────────────────────────────────────


class TestWorkerRegistry:
    """Test worker registry endpoints."""

    def test_list_workers(self, client):
        """GET /api/v1/workers returns registered workers."""
        response = client.get("/api/v1/workers")
        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert "total" in data
        # Seeded workers should exist (moneyprint is Phase 3, excluded)
        assert data["total"] >= 3  # chronos, avatar-webinar, vmf

    def test_filter_workers_by_status(self, client):
        """GET /api/v1/workers?status=AVAILABLE filters workers."""
        response = client.get("/api/v1/workers?status=AVAILABLE")
        assert response.status_code == 200
        data = response.json()
        for worker in data["workers"]:
            assert worker["status"] == "AVAILABLE"


# ─── Capability Registry Tests ───────────────────────────────────────────────


class TestCapabilityRegistry:
    """Test capability registry endpoints."""

    def test_list_capabilities(self, client):
        """GET /api/v1/capabilities returns all capabilities."""
        response = client.get("/api/v1/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert "capabilities" in data
        assert "total" in data

    def test_capability_has_verification_flags(self, client):
        """Capabilities include verification flags."""
        response = client.get("/api/v1/capabilities")
        assert response.status_code == 200
        data = response.json()
        if data["total"] > 0:
            cap = data["capabilities"][0]
            assert "code_present" in cap
            assert "credential_verified" in cap
            assert "integration_verified" in cap
            assert "production_verified" in cap
            assert "healthy" in cap


# ─── Artifacts Tests ─────────────────────────────────────────────────────────


class TestJobArtifacts:
    """Test job artifacts endpoint."""

    def test_get_empty_artifacts(self, client):
        """GET /api/v1/jobs/:id/artifacts returns empty list for new job."""
        create_resp = client.post(
            "/api/v1/content/jobs",
            json={
                "source_app": "vpms-internal",
                "request_type": "podcast_episode",
                "content": {"topic": "Artifacts Test"},
            },
        )
        job_id = create_resp.json()["job_id"]

        response = client.get(f"/api/v1/jobs/{job_id}/artifacts")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["artifacts"] == []
        assert data["total"] == 0
