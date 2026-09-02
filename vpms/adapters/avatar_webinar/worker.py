"""
VPMS Avatar Webinar Adapter — podcast/video production with AI avatars.
Translates between VPMS WorkerJobRequest and Avatar Webinar's Smart Production API.

Avatar Webinar runs at: http://localhost:3200 (Node Express API)
Health: GET /health (no auth)
Production: POST /api/production/render-from-script (Supabase JWT auth) — one-call
Status: GET /api/production/:id/status (Supabase JWT auth)
Assets: GET /api/production/:id/assets (Supabase JWT auth)

Auth: Supabase JWT. VPMS uses a service-role key to mint user tokens.
Set VPMS_AVATAR_WEBINAR_SUPABASE_URL and VPMS_AVATAR_WEBINAR_SERVICE_KEY env vars.
"""

import os
import httpx
import jwt
import time
from datetime import datetime, timezone
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

# ─── Auth ───────────────────────────────────────────────────────────────────────

_AVATAR_WEBINAR_SUPABASE_URL = os.environ.get(
    "VPMS_AVATAR_WEBINAR_SUPABASE_URL", ""
).rstrip("/")
_AVATAR_WEBINAR_SERVICE_KEY = os.environ.get(
    "VPMS_AVATAR_WEBINAR_SERVICE_KEY", ""
).strip()

# Cache for minted JWTs
_cached_token: Optional[str] = None
_token_expiry: float = 0


def _mint_vpms_jwt() -> Optional[str]:
    """
    Mint a short-lived JWT for VPMS to act as a user in Avatar Webinar.
    Uses Supabase service-role key to create a user token.
    """
    global _cached_token, _token_expiry

    # Return cached token if still valid (> 30s remaining)
    if _cached_token and time.time() < (_token_expiry - 30):
        return _cached_token

    if not _AVATAR_WEBINAR_SUPABASE_URL or not _AVATAR_WEBINAR_SERVICE_KEY:
        logger.warning(
            "VPMS_AVATAR_WEBINAR_SUPABASE_URL or VPMS_AVATAR_WEBINAR_SERVICE_KEY not set"
        )
        return None

    try:
        # Supabase Auth: create a mock user session for VPMS
        # We create a time-limited token using the anon key approach
        anon_key = _AVATAR_WEBINAR_SERVICE_KEY

        # Build a minimal JWT with the required claims for Supabase verification
        payload = {
            "iss": _AVATAR_WEBINAR_SUPABASE_URL,
            "sub": "vpms-system-user",
            "email": "vpms@bookaistudio.com",
            "role": "authenticated",
            "aud": "authenticated",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,  # 5 min
        }

        # Sign with HS256 — works because Supabase accepts HS256 by default
        # for service-role tokens. We use the service key as secret.
        token = jwt.encode(payload, _AVATAR_WEBINAR_SERVICE_KEY, algorithm="HS256")
        _cached_token = token
        _token_expiry = payload["exp"]
        return token

    except Exception as e:
        logger.error(f"Failed to mint Avatar Webinar JWT: {e}")
        return None


def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    token = _mint_vpms_jwt()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ─── Adapter ───────────────────────────────────────────────────────────────────


class AvatarWebinarWorkerAdapter(BaseWorkerAdapter):
    """
    Adapter for Avatar Webinar Smart Production Engine.

    Capabilities:
    - podcast_production: Script → avatar video with hybrid rendering
    - render_from_script: One-call endpoint (best for VPMS integration)

    Avatar Webinar handles two-person podcast production:
    - Takes a script with SPEAKER1/SPEAKER2/HOST/GUEST markers
    - Generates TTS audio per segment
    - Renders avatar videos for talking segments
    - Assembles final 1080p MP4
    """

    def __init__(self, base_url: str = "http://localhost:3200"):
        self._base_url = base_url.rstrip("/")

    @property
    def worker_id(self) -> str:
        return "avatar-webinar"

    @property
    def base_url(self) -> str:
        return self._base_url

    # ─── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> WorkerHealth:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{self._base_url}/health")
                resp.raise_for_status()
                data = resp.json()
                return WorkerHealth(
                    status=data.get("status", "ok"),
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.HTTPStatusError:
                return WorkerHealth(
                    status="unhealthy",
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.RequestError:
                return WorkerHealth(
                    status="unreachable",
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

    # ─── Capabilities ──────────────────────────────────────────────────────────

    async def get_capabilities(self) -> WorkerCapabilities:
        """
        Return Avatar Webinar capabilities.
        Tries to call the providers endpoint for live data.
        """
        capabilities = [
            {
                "capability": "podcast_production",
                "description": "Full podcast production: plan → approve → render",
                "available": True,
            },
            {
                "capability": "render_from_script",
                "description": "One-call render from script text (best for VPMS)",
                "available": True,
            },
        ]

        # Try to get live provider list
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/api/production/providers/list",
                    headers=_auth_headers(),
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    providers = data.get("providers", [])
                    capabilities[0]["providers"] = [p["name"] for p in providers]
                    capabilities[1]["providers"] = [p["name"] for p in providers]
            except Exception:
                pass

        return WorkerCapabilities(
            worker_id=self.worker_id,
            capabilities=capabilities,
        )

    # ─── Dispatch ─────────────────────────────────────────────────────────────

    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """
        Dispatch to Avatar Webinar.

        VPMS sends:
        - script: dict with segments or full script_text
        - speakers: list of {name, voice_id, avatar_image_url}
        - output: dict with resolution, aspect_ratio

        We use /api/production/render-from-script (one-call, best VPMS fit).
        """
        production_type = job_request.production_type or "podcast_hybrid"
        started_at = datetime.now(timezone.utc).isoformat()

        # Extract from job_request
        script_data = job_request.script or {}
        speakers = job_request.speakers or []
        output_config = job_request.output or {}
        metadata = job_request.metadata or {}

        # Determine if we have a full script_text or structured segments
        script_text = script_data.get("script_text") or script_data.get("full_script") or ""
        segments = script_data.get("segments", [])

        if not script_text and not segments:
            return WorkerReceipt(
                vpms_job_id=job_request.vpms_job_id,
                worker=self.worker_id,
                worker_job_id="",
                status="FAILED",
                errors=["Avatar Webinar requires script_text or segments in job_request.script"],
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Build render-from-script payload
        # Avatar Webinar requires: script_text, voice1_id, avatar_image_url
        # Optional: voice2_id, avatar_2_image_url, speaker1_name, speaker2_name
        speaker1 = speakers[0] if len(speakers) > 0 else {}
        speaker2 = speakers[1] if len(speakers) > 1 else {}

        # Use provided avatar images or fall back to brand default
        avatar_image_url = (
            speaker1.get("avatar_image_url")
            or output_config.get("avatar_image_url")
            or metadata.get("avatar_image_url")
            or ""
        )
        avatar_2_image_url = (
            speaker2.get("avatar_image_url")
            or output_config.get("avatar_2_avatar_image_url")
            or metadata.get("avatar_2_image_url")
            or ""
        )

        # Voice IDs
        voice1_id = speaker1.get("voice_id") or metadata.get("voice1_id") or "21m00Tcm4TlvDq8ikWAM"
        voice2_id = speaker2.get("voice_id") or metadata.get("voice2_id") or voice1_id

        # Use script_text if provided, otherwise reconstruct from segments
        if not script_text and segments:
            lines = []
            for seg in segments:
                speaker_label = seg.get("speaker", "HOST")
                text = seg.get("text", "")
                if speaker_label.upper() in ("HOST", "SPEAKER1"):
                    lines.append(f"HOST: {text}")
                elif speaker_label.upper() in ("GUEST", "SPEAKER2"):
                    lines.append(f"GUEST: {text}")
                else:
                    lines.append(f"HOST: {text}")
            script_text = "\n".join(lines)

        payload = {
            "title": metadata.get("title", f"VPMS Production {job_request.vpms_job_id}"),
            "script_text": script_text,
            "voice1_id": voice1_id,
            "voice2_id": voice2_id,
            "avatar_image_url": avatar_image_url,
            "avatar_2_image_url": avatar_2_image_url,
            "speaker1_name": speaker1.get("name", "Host"),
            "speaker2_name": speaker2.get("name", "Guest"),
            "production_type": production_type,
            "brand_config": output_config.get("brand_config", {}),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/api/production/render-from-script",
                    json=payload,
                    headers=_auth_headers(),
                )

                if resp.status_code == 202:
                    # Accepted — job is queued
                    data = resp.json()
                    aw_job_id = data.get("job_id", "")
                    return WorkerReceipt(
                        vpms_job_id=job_request.vpms_job_id,
                        worker=self.worker_id,
                        worker_job_id=aw_job_id,
                        status="PROVIDER_CONFIRMED",
                        artifacts=[
                            {
                                "type": "podcast_production",
                                "name": f"podcast_{aw_job_id}",
                                "metadata": {"poll_url": data.get("poll_url")},
                            }
                        ],
                        estimated_cost=data.get("estimated_cost", 0.0),
                        started_at=started_at,
                    )

                elif resp.status_code == 401:
                    return WorkerReceipt(
                        vpms_job_id=job_request.vpms_job_id,
                        worker=self.worker_id,
                        worker_job_id="",
                        status="FAILED",
                        errors=["Avatar Webinar auth failed — check VPMS_AVATAR_WEBINAR_SUPABASE_URL / SERVICE_KEY"],
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )

                else:
                    body = resp.text[:200]
                    return WorkerReceipt(
                        vpms_job_id=job_request.vpms_job_id,
                        worker=self.worker_id,
                        worker_job_id="",
                        status="FAILED",
                        errors=[f"Avatar Webinar HTTP {resp.status_code}: {body}"],
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )

            except httpx.HTTPStatusError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id="",
                    status="FAILED",
                    errors=[f"Avatar Webinar HTTP {e.response.status_code}: {e.response.text[:200]}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.RequestError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id="",
                    status="FAILED",
                    errors=[f"Avatar Webinar connection error: {str(e)}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

    # ─── Status ────────────────────────────────────────────────────────────────

    async def get_status(self, worker_job_id: str) -> WorkerReceipt:
        """
        Poll Avatar Webinar /api/production/:id/status.
        Maps Avatar Webinar status to VPMS receipt status.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/api/production/{worker_job_id}/status",
                    headers=_auth_headers(),
                )
                resp.raise_for_status()
                data = resp.json()

                aw_status = data.get("status", "")
                progress = data.get("progress", 0)
                final_url = data.get("final_video_url")

                # Map Avatar Webinar status -> VPMS receipt status
                if aw_status == "done":
                    receipt_status = "COMPLETED"
                    completed_at = datetime.now(timezone.utc).isoformat()
                elif aw_status == "failed":
                    receipt_status = "FAILED"
                    completed_at = datetime.now(timezone.utc).isoformat()
                elif aw_status in ("rendering", "queued", "planned", "approved"):
                    receipt_status = "PROVIDER_CONFIRMED"
                    completed_at = None
                else:
                    receipt_status = "PROVIDER_CONFIRMED"
                    completed_at = None

                artifacts = []
                if final_url:
                    artifacts.append({
                        "type": "video",
                        "name": f"podcast_final_{worker_job_id}.mp4",
                        "url": final_url,
                        "metadata": {"progress": progress},
                    })

                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status=receipt_status,
                    artifacts=artifacts,
                    completed_at=completed_at,
                )

            except httpx.HTTPStatusError:
                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"Avatar Webinar status HTTP {resp.status_code if 'resp' in dir() else 'unknown'}"],
                )
            except httpx.RequestError as e:
                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"Avatar Webinar status connection error: {str(e)}"],
                )

    # ─── Artifacts ─────────────────────────────────────────────────────────────

    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]:
        """
        Get final video and clips from Avatar Webinar.
        Calls /api/production/:id/assets for full manifest.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/api/production/{worker_job_id}/assets",
                    headers=_auth_headers(),
                )
                resp.raise_for_status()
                data = resp.json()

                artifacts = []

                # Final video
                final_url = data.get("final_video_url")
                if final_url:
                    artifacts.append(WorkerArtifact(
                        type="video",
                        name=f"podcast_final_{worker_job_id}.mp4",
                        url=final_url,
                        metadata=data.get("metadata", {}),
                    ))

                # Short clips
                for i, clip in enumerate(data.get("short_clips", [])):
                    artifacts.append(WorkerArtifact(
                        type="clip",
                        name=clip.get("name", f"clip_{i+1}.mp4"),
                        url=clip.get("url"),
                        metadata=clip,
                    ))

                # Scene-level artifacts
                for scene in data.get("scenes", []):
                    render_url = scene.get("render_url")
                    if render_url:
                        artifacts.append(WorkerArtifact(
                            type="scene_video",
                            name=f"scene_{scene.get('scene_index', '?')}_{scene.get('visual_type', 'unknown')}.mp4",
                            url=render_url,
                            metadata={
                                "visual_type": scene.get("visual_type"),
                                "provider": scene.get("provider"),
                                "render_status": scene.get("render_status"),
                            },
                        ))

                # Cost summary
                cost_summary = data.get("cost_summary", {})

                return artifacts

            except httpx.RequestError:
                return []

    # ─── Cancel ──────────────────────────────────────────────────────────────

    async def cancel(self, worker_job_id: str) -> bool:
        """
        Cancel an Avatar Webinar render.
        Avatar Webinar has no cancel endpoint — log and return False.
        """
        logger.warning(
            f"Avatar Webinar cancel requested for {worker_job_id} — "
            "Avatar Webinar has no cancel endpoint"
        )
        return False
