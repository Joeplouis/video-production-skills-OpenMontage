"""
VPMS VMF Adapter — Video Media Factory integration.
Translates between VPMS WorkerJobRequest and VMF pipeline API.

VMF runs at: http://localhost:4100 (Node Express API)
Health: GET /api/health (no auth)
Pipeline: POST /api/pipeline/generate (JWT Bearer auth)
Status:  GET /api/pipeline/status/:jobId (JWT Bearer auth)
UGC:     POST /api/ugc/batch (JWT Bearer auth)
"""

import os
import httpx
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


def _get_auth_token() -> str:
    """
    Read VMF JWT token from environment.
    Set VPMS_VMF_JWT_TOKEN to a valid JWT from VMF's JWT_SECRET.
    """
    token = os.environ.get("VPMS_VMF_JWT_TOKEN", "").strip()
    if not token:
        logger.warning("VPMS_VMF_JWT_TOKEN not set — VMF calls requiring auth will fail")
    return token


def _headers() -> dict:
    """Build request headers including auth when available."""
    token = _get_auth_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ─── Adapter ───────────────────────────────────────────────────────────────────


class VMFWorkerAdapter(BaseWorkerAdapter):
    """
    Adapter for the Video Media Factory (VMF) pipeline API.

    Capabilities:
    - pipeline_video: Full LLM-script → TTS → image/video → Shotstack render
    - ugc_batch: Bulk UGC clip generation via Creatomate
    """

    def __init__(self, base_url: str = "http://localhost:4100"):
        self._base_url = base_url.rstrip("/")

    @property
    def worker_id(self) -> str:
        return "vmf"

    @property
    def base_url(self) -> str:
        return self._base_url

    # ─── Health ────────────────────────────────────────────────────────────────

    async def health_check(self) -> WorkerHealth:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{self._base_url}/api/health")
                resp.raise_for_status()
                data = resp.json()
                return WorkerHealth(
                    status=data.get("status", "ok"),
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.HTTPStatusError as e:
                return WorkerHealth(
                    status="unhealthy",
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.RequestError as e:
                return WorkerHealth(
                    status="unreachable",
                    worker_id=self.worker_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

    # ─── Capabilities ──────────────────────────────────────────────────────────

    async def get_capabilities(self) -> WorkerCapabilities:
        """Return VMF capabilities. Requires auth for full capability list."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/api/providers",
                    headers={"x-source-app": "vpms"},
                    timeout=10.0,
                )
                resp.raise_for_status()
                providers = resp.json().get("providers", [])
                capabilities = [
                    {
                        "capability": "pipeline_video",
                        "description": "LLM-script → TTS → assets → Shotstack render pipeline",
                        "providers": [p["id"] for p in providers if p.get("type") == "video"],
                        "available": True,
                    },
                    {
                        "capability": "ugc_batch",
                        "description": "Bulk UGC video generation via Creatomate",
                        "providers": ["creatomate"],
                        "available": True,
                    },
                ]
            except Exception:
                capabilities = [
                    {
                        "capability": "pipeline_video",
                        "description": "LLM-script → TTS → assets → Shotstack render pipeline",
                        "providers": [],
                        "available": False,
                    },
                ]

        return WorkerCapabilities(
            worker_id=self.worker_id,
            capabilities=capabilities,
        )

    # ─── Dispatch ─────────────────────────────────────────────────────────────

    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """
        Dispatch a job to VMF.

        For podcast/video pipeline:
          POST /api/pipeline/generate
          Body: { topic, tone, platform, style_preset, language_output, voice_id, use_runware }

        For UGC batch:
          POST /api/ugc/batch
          Body: { template_id, items[], webhook_url }

        Falls back to pipeline_video if no specific handler matches.
        """
        production_type = job_request.production_type or "pipeline_video"

        if production_type == "ugc_batch":
            return await self._dispatch_ugc(job_request)
        else:
            return await self._dispatch_pipeline(job_request)

    async def _dispatch_pipeline(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """Dispatch to VMF /api/pipeline/generate."""
        content = job_request.content or {}
        metadata = job_request.metadata or {}

        # Build VMF pipeline payload
        payload = {
            "topic": content.get("topic", "VPMS managed production"),
            "tone": metadata.get("tone", "conversational"),
            "platform": metadata.get("platform", "youtube"),
            "style_preset": metadata.get("style_preset", "storytelling"),
            "language_output": metadata.get("language_output", "en"),
            "voice_id": metadata.get("voice_id", "21m00Tcm4TlvDq8ikWAM"),
            "use_runware": metadata.get("use_runware", True),
            "use_muapi": metadata.get("use_muapi", False),
        }

        started_at = datetime.now(timezone.utc).isoformat()
        worker_job_id = f"vmf_pending_{job_request.vpms_job_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/api/pipeline/generate",
                    json=payload,
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()

                # VMF returns { job_id, status, render_id, scenes_count, ... }
                vmf_job_id = data.get("job_id", "")
                # VMF may return render_id immediately
                render_id = data.get("render_id", "")

                artifacts = []
                if render_id:
                    artifacts.append({
                        "type": "render",
                        "name": f"shotstack_render_{render_id}",
                        "url": None,
                        "metadata": {"render_id": render_id},
                    })

                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=vmf_job_id,
                    status="PROVIDER_CONFIRMED",
                    artifacts=artifacts,
                    started_at=started_at,
                )

            except httpx.HTTPStatusError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF HTTP {e.response.status_code}: {e.response.text[:200]}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.RequestError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF connection error: {str(e)}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

    async def _dispatch_ugc(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """Dispatch to VMF /api/ugc/batch."""
        metadata = job_request.metadata or {}

        payload = {
            "template_id": metadata.get("template_id", ""),
            "items": metadata.get("items", []),
            "webhook_url": metadata.get("webhook_url", ""),
        }

        started_at = datetime.now(timezone.utc).isoformat()
        worker_job_id = f"vmf_ugc_pending_{job_request.vpms_job_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/api/ugc/batch",
                    json=payload,
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                vmf_job_id = data.get("batch_id", "")

                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=vmf_job_id,
                    status="PROVIDER_CONFIRMED",
                    started_at=started_at,
                )
            except httpx.HTTPStatusError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF UGC HTTP {e.response.status_code}: {e.response.text[:200]}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except httpx.RequestError as e:
                return WorkerReceipt(
                    vpms_job_id=job_request.vpms_job_id,
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF UGC connection error: {str(e)}"],
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )

    # ─── Status ────────────────────────────────────────────────────────────────

    async def get_status(self, worker_job_id: str) -> WorkerReceipt:
        """
        Poll VMF /api/pipeline/status/:jobId for job status.
        Maps VMF status to VPMS receipt status.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/api/pipeline/status/{worker_job_id}",
                    headers=_headers(),
                )
                resp.raise_for_status()
                data = resp.json()

                # VMF returns: { id, status, phase, phase_pct, result: { shotstack_render_id, ... } }
                vmf_status = data.get("status", "")
                phase = data.get("phase", "")
                result = data.get("result", {})

                # Map VMF status -> VPMS receipt status
                if vmf_status == "completed":
                    receipt_status = "COMPLETED"
                    completed_at = datetime.now(timezone.utc).isoformat()
                elif vmf_status == "failed":
                    receipt_status = "FAILED"
                    completed_at = datetime.now(timezone.utc).isoformat()
                elif vmf_status in ("running", "pending"):
                    receipt_status = "PROVIDER_CONFIRMED"
                    completed_at = None
                else:
                    receipt_status = "PROVIDER_CONFIRMED"
                    completed_at = None

                artifacts = []
                render_id = result.get("shotstack_render_id") if isinstance(result, dict) else None
                if render_id:
                    artifacts.append({
                        "type": "render",
                        "name": f"shotstack_render_{render_id}",
                        "metadata": {"render_id": render_id, "phase": phase},
                    })

                return WorkerReceipt(
                    vpms_job_id="",  # not in VMF response — caller must correlate
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status=receipt_status,
                    artifacts=artifacts,
                    completed_at=completed_at,
                )

            except httpx.HTTPStatusError as e:
                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF status HTTP {e.response.status_code}"],
                )
            except httpx.RequestError as e:
                return WorkerReceipt(
                    vpms_job_id="",
                    worker=self.worker_id,
                    worker_job_id=worker_job_id,
                    status="FAILED",
                    errors=[f"VMF status connection error: {str(e)}"],
                )

    # ─── Artifacts ────────────────────────────────────────────────────────────

    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]:
        """
        Get final rendered video artifacts from VMF.
        Calls /api/pipeline/status/:jobId and extracts render URL.
        """
        status_receipt = await self.get_status(worker_job_id)
        artifacts = []

        for art in status_receipt.artifacts:
            artifacts.append(WorkerArtifact(
                type=art.get("type", "video"),
                name=art.get("name", "unknown"),
                url=art.get("url"),
                metadata=art.get("metadata", {}),
            ))

        # Also try the renders static endpoint if VMF has rendered output
        if status_receipt.status == "COMPLETED":
            async with httpx.AsyncClient(timeout=15.0) as client:
                try:
                    # Try renders directory listing for the job
                    resp = await client.get(
                        f"{self._base_url}/api/renders/{worker_job_id}",
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        render_data = resp.json()
                        for item in render_data.get("renders", []):
                            artifacts.append(WorkerArtifact(
                                type="video",
                                name=item.get("name", "render.mp4"),
                                url=item.get("url"),
                                metadata={"render_id": worker_job_id},
                            ))
                except Exception:
                    pass  # Static render listing is optional

        return artifacts

    # ─── Cancel ──────────────────────────────────────────────────────────────

    async def cancel(self, worker_job_id: str) -> bool:
        """Cancel a VMF pipeline job. VMF does not have a cancel endpoint — log and return False."""
        logger.warning(f"VMF cancel requested for {worker_job_id} — VMF has no cancel endpoint")
        return False
