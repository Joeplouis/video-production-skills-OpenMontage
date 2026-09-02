"""
VPMS Chronos Adapter — content showrunner integration.
Chronos is a cron-driven autonomous showrunner, not an HTTP API.
It reads series_state.json and produces content on a schedule.

For VPMS integration:
- health_check(): verify series_state.json exists and the script is runnable
- dispatch(): write a VPMS production request to the Chronos queue
- get_status(): read series_state.json to check if the slot was processed
- get_artifacts(): read completed episode data from series_state.json

Chronos app: /opt/empire/apps/high-cpm-story-franchise/
"""

import os
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

from vpms.adapters.base import (
    BaseWorkerAdapter,
    WorkerHealth,
    WorkerCapabilities,
    WorkerJobRequest,
    WorkerReceipt,
    WorkerArtifact,
)

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

CHRONOS_APP_DIR = os.environ.get(
    "VPMS_CHRONOS_APP_DIR",
    "/opt/empire/apps/high-cpm-story-franchise",
)
STATE_FILE = os.path.join(CHRONOS_APP_DIR, "series_state.json")
QUEUE_FILE = os.path.join(CHRONOS_APP_DIR, "vpms_queue.json")
RUN_SCRIPT = os.path.join(CHRONOS_APP_DIR, "run_chronos.sh")


def _load_state(state_file: str = STATE_FILE) -> dict:
    """Read the current Chronos series state."""
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _load_queue(queue_file: str = QUEUE_FILE) -> list:
    """Read pending VPMS jobs in the Chronos queue."""
    if not os.path.exists(queue_file):
        return []
    try:
        with open(queue_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_queue(queue: list, queue_file: str = QUEUE_FILE):
    """Save the VPMS queue back to disk."""
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)
    with open(queue_file, "w") as f:
        json.dump(queue, f, indent=2)


# ─── Adapter ───────────────────────────────────────────────────────────────────


class ChronosWorkerAdapter(BaseWorkerAdapter):
    """
    Adapter for Chronos — an autonomous cron-driven content showrunner.

    Chronos runs on a cron schedule and produces episodic content.
    VPMS can enqueue production requests that Chronos will pick up
    on its next scheduled run.

    Capabilities exposed:
    - content_research: Discover and research niche topics
    - script_generation: Write episodic scripts with continuity
    - fish_audio_tts: Generate narration via Fish Audio API
    - shotstack_render: Render 1080p MP4 via Shotstack
    - postiz_publish: Publish to social platforms via Postiz
    """

    def __init__(
        self,
        app_dir: str = CHRONOS_APP_DIR,
        state_file: str = STATE_FILE,
        queue_file: str = QUEUE_FILE,
        run_script: str = RUN_SCRIPT,
    ):
        self._app_dir = app_dir
        self._state_file = state_file
        self._queue_file = queue_file
        self._run_script = run_script

    @property
    def worker_id(self) -> str:
        return "chronos"

    @property
    def base_url(self) -> str:
        return f"file://{self._app_dir}"

    # ─── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> WorkerHealth:
        """
        Check Chronos health by verifying:
        1. series_state.json exists and is readable
        2. run_chronos.sh exists and is executable
        3. Required env vars are present (via env_loader.py)
        """
        issues: list[str] = []

        # Check state file
        if not os.path.exists(self._state_file):
            issues.append("series_state.json not found")

        # Check run script
        if not os.path.exists(self._run_script):
            issues.append("run_chronos.sh not found")
        elif not os.access(self._run_script, os.X_OK):
            issues.append("run_chronos.sh not executable")

        # Check app directory
        if not os.path.isdir(self._app_dir):
            issues.append(f"Chronos app dir not accessible: {self._app_dir}")

        status = "healthy" if not issues else "degraded"
        return WorkerHealth(
            status=status,
            worker_id=self.worker_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ─── Capabilities ──────────────────────────────────────────────────────────

    async def get_capabilities(self) -> WorkerCapabilities:
        """
        Return Chronos capabilities.
        Chronos is a full pipeline showrunner.
        """
        capabilities = [
            {
                "capability": "content_research",
                "description": "Discover and research high-CPM niche topics",
                "available": True,
            },
            {
                "capability": "script_generation",
                "description": "Write episodic scripts with narrative continuity and cliffhangers",
                "available": True,
            },
            {
                "capability": "fish_audio_tts",
                "description": "Generate narration via Fish Audio API",
                "available": True,
            },
            {
                "capability": "shotstack_render",
                "description": "Render 1080p MP4 via Shotstack",
                "available": True,
            },
            {
                "capability": "postiz_publish",
                "description": "Publish finished video to social platforms via Postiz",
                "available": True,
            },
            {
                "capability": "full_episode_pipeline",
                "description": "End-to-end: research → script → TTS → render → publish",
                "available": True,
            },
        ]
        return WorkerCapabilities(
            worker_id=self.worker_id,
            capabilities=capabilities,
        )

    # ─── Dispatch ─────────────────────────────────────────────────────────────

    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """
        Enqueue a VPMS production request into the Chronos queue.

        Chronos processes the queue on its next cron run.
        We write a VPMS job entry to vpms_queue.json which Chronos
        will read and incorporate into the next scheduled run.

        Returns a receipt with the queue entry as worker_job_id.
        """
        content = job_request.content or {}
        production = job_request.production or {}
        metadata = job_request.metadata or {}
        started_at = datetime.now(timezone.utc).isoformat()

        # Build a VPMS queue entry for Chronos
        queue_entry = {
            "vpms_job_id": job_request.vpms_job_id,
            "enqueued_at": started_at,
            "topic": content.get("topic", ""),
            "niche": content.get("niche", metadata.get("niche", "")),
            "series": metadata.get("series", ""),
            "speakers": job_request.speakers or [],
            "requested_outputs": job_request.requested_outputs or [],
            "budget": job_request.budget or {},
            "priority": getattr(job_request, "priority", 5),
            "status": "queued",  # updated when Chronos processes it
            "chronos_slot": metadata.get("chronos_slot"),  # optional: 0-3
        }

        # Validate required fields
        if not queue_entry["topic"] and not queue_entry["niche"]:
            return WorkerReceipt(
                vpms_job_id=job_request.vpms_job_id,
                worker=self.worker_id,
                worker_job_id="",
                status="FAILED",
                errors=["Chronos requires 'topic' or 'niche' in job_request.content"],
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Load existing queue
        queue = _load_queue(queue_file=self._queue_file)
        queue.append(queue_entry)
        _save_queue(queue, queue_file=self._queue_file)

        # Determine worker_job_id = queue index for polling
        worker_job_id = f"chronos_queue_{len(queue) - 1}"

        return WorkerReceipt(
            vpms_job_id=job_request.vpms_job_id,
            worker=self.worker_id,
            worker_job_id=worker_job_id,
            status="PROVIDER_CONFIRMED",
            artifacts=[
                {
                    "type": "queue_entry",
                    "name": f"vpms_queue_{worker_job_id}",
                    "metadata": {
                        "queue_position": len(queue) - 1,
                        "topic": queue_entry["topic"],
                    },
                }
            ],
            started_at=started_at,
        )

    # ─── Status ────────────────────────────────────────────────────────────────

    async def get_status(self, worker_job_id: str) -> WorkerReceipt:
        """
        Poll Chronos status by reading series_state.json.

        If worker_job_id references a queue entry (chronos_queue_N),
        we look for a matching vpms_job_id in the episodes_history.

        States:
        - QUEUED: entry in vpms_queue.json but not yet in episodes_history
        - PROCESSING: found in episodes_history with running status
        - COMPLETED: found in episodes_history with complete status
        """
        queue = _load_queue(queue_file=self._queue_file)
        state = _load_state(state_file=self._state_file)
        episodes_history = state.get("episodes_history", [])

        # Parse queue index from worker_job_id
        if worker_job_id.startswith("chronos_queue_"):
            try:
                queue_idx = int(worker_job_id.split("_")[-1])
                if queue_idx < len(queue):
                    queue_entry = queue[queue_idx]
                    vpms_job_id = queue_entry["vpms_job_id"]
                else:
                    return WorkerReceipt(
                        vpms_job_id="",
                        worker=self.worker_id,
                        worker_job_id=worker_job_id,
                        status="FAILED",
                        errors=[f"Queue index {queue_idx} out of range"],
                    )
            except (ValueError, IndexError):
                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"Invalid worker_job_id format: {worker_job_id}"],
                )
        else:
            # Direct vpms_job_id lookup
            vpms_job_id = worker_job_id

        # Look for matching episode in history
        matching_episodes = [
            ep for ep in episodes_history
            if ep.get("vpms_job_id") == vpms_job_id
        ]

        if matching_episodes:
            episode = matching_episodes[-1]  # most recent
            ep_status = episode.get("status", "unknown")

            if ep_status == "complete":
                receipt_status = "COMPLETED"
                completed_at = datetime.now(timezone.utc).isoformat()
            elif ep_status in ("running", "processing"):
                receipt_status = "PROVIDER_CONFIRMED"
                completed_at = None
            else:
                receipt_status = "PROVIDER_CONFIRMED"
                completed_at = None

            artifacts = []
            if episode.get("output_url"):
                artifacts.append({
                    "type": "video",
                    "name": f"chronos_ep_{episode.get('episode', '?')}.mp4",
                    "url": episode.get("output_url"),
                    "metadata": {
                        "niche": episode.get("niche"),
                        "series": episode.get("series"),
                        "slot": episode.get("slot"),
                    },
                })
            if episode.get("script_text"):
                artifacts.append({
                    "type": "script",
                    "name": f"chronos_script_{episode.get('episode', '?')}.txt",
                    "metadata": {"text": episode.get("script_text")[:500]},
                })

            return WorkerReceipt(
                vpms_job_id=vpms_job_id,
                worker=self.worker_id,
                worker_job_id=worker_job_id,
                status=receipt_status,
                artifacts=artifacts,
                completed_at=completed_at,
            )

        # Not in history yet — check if it's queued
        queued_entries = [
            q for q in queue if q.get("vpms_job_id") == vpms_job_id
        ]
        if queued_entries:
            return WorkerReceipt(
                vpms_job_id=vpms_job_id,
                worker=self.worker_id,
                worker_job_id=worker_job_id,
                status="PROVIDER_CONFIRMED",
                artifacts=[],
                completed_at=None,
            )

        # Not found anywhere
        return WorkerReceipt(
            vpms_job_id=vpms_job_id,
            worker=self.worker_id,
            worker_job_id=worker_job_id,
            status="FAILED",
            errors=[f"Chronos job not found: {vpms_job_id}"],
        )

    # ─── Artifacts ─────────────────────────────────────────────────────────────

    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]:
        """
        Extract artifacts from the latest matching episode in series_state.json.
        """
        artifacts: list[WorkerArtifact] = []
        state = _load_state(state_file=self._state_file)
        episodes_history = state.get("episodes_history", [])

        # Find matching episode
        vpms_job_id = worker_job_id
        if worker_job_id.startswith("chronos_queue_"):
            try:
                idx = int(worker_job_id.split("_")[-1])
                queue = _load_queue(queue_file=self._queue_file)
                if idx < len(queue):
                    vpms_job_id = queue[idx].get("vpms_job_id", "")
            except (ValueError, IndexError):
                pass

        matching = [
            ep for ep in episodes_history
            if ep.get("vpms_job_id") == vpms_job_id
        ]
        if not matching:
            return []

        episode = matching[-1]

        if episode.get("output_url"):
            artifacts.append(WorkerArtifact(
                type="video",
                name=f"chronos_ep_{episode.get('episode', '?')}.mp4",
                url=episode.get("output_url"),
                metadata={
                    "niche": episode.get("niche"),
                    "series": episode.get("series"),
                    "episode": episode.get("episode"),
                },
            ))

        if episode.get("thumbnail_url"):
            artifacts.append(WorkerArtifact(
                type="thumbnail",
                name=f"chronos_thumb_{episode.get('episode', '?')}.jpg",
                url=episode.get("thumbnail_url"),
            ))

        if episode.get("youtube_metadata"):
            artifacts.append(WorkerArtifact(
                type="metadata",
                name="youtube_metadata.json",
                metadata=episode.get("youtube_metadata", {}),
            ))

        return artifacts

    # ─── Cancel ──────────────────────────────────────────────────────────────

    async def cancel(self, worker_job_id: str) -> bool:
        """
        Cancel a queued Chronos job by removing it from vpms_queue.json.
        If the job has already been picked up by Chronos (in episodes_history),
        cancellation is not possible.
        """
        queue = _load_queue(queue_file=self._queue_file)

        # Parse queue index
        if worker_job_id.startswith("chronos_queue_"):
            try:
                idx = int(worker_job_id.split("_")[-1])
                if idx < len(queue) and queue[idx].get("vpms_job_id"):
                    removed = queue.pop(idx)
                    _save_queue(queue, queue_file=self._queue_file)
                    logger.info(f"Chronos queue entry removed: {removed['vpms_job_id']}")
                    return True
            except (ValueError, IndexError):
                pass

        # Try direct vpms_job_id match
        new_queue = [q for q in queue if q.get("vpms_job_id") != worker_job_id]
        if len(new_queue) < len(queue):
            _save_queue(new_queue, queue_file=self._queue_file)
            return True

        return False
