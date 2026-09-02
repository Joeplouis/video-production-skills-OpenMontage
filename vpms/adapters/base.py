"""
VPMS Worker Adapter Contract — Base Interface
Defines the canonical interface all worker adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class WorkerHealth(BaseModel):
    """Worker health response."""

    status: str  # healthy, unhealthy
    worker_id: str
    timestamp: str


class WorkerCapabilities(BaseModel):
    """Worker capabilities response."""

    worker_id: str
    capabilities: list[dict]


class WorkerJobRequest(BaseModel):
    """VPMS -> Worker job request."""

    vpms_job_id: str
    worker: str
    production_type: str
    script: Optional[dict] = None
    scene_plan: Optional[list] = None
    brand: Optional[dict] = None
    speakers: Optional[list] = None
    output: Optional[dict] = None
    requested_outputs: Optional[list] = None
    budget: Optional[dict] = None
    metadata: Optional[dict] = None


class WorkerReceipt(BaseModel):
    """
    Worker receipt — proof of work.
    Must be produced for every meaningful worker operation.
    """

    vpms_job_id: str
    worker: str
    worker_job_id: str
    status: str  # PENDING, PROVIDER_CONFIRMED, COMPLETED, FAILED
    provider: Optional[str] = None
    model: Optional[str] = None
    artifacts: list[dict] = []
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    started_at: str
    completed_at: Optional[str] = None
    errors: list[str] = []


class WorkerArtifact(BaseModel):
    """Worker artifact metadata."""

    type: str
    name: str
    url: Optional[str] = None
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    checksum: Optional[str] = None
    metadata: dict = {}


class BaseWorkerAdapter(ABC):
    """
    Abstract base class for worker adapters.

    All adapters must implement:
    - health_check() -> WorkerHealth
    - get_capabilities() -> WorkerCapabilities
    - dispatch(job_request: WorkerJobRequest) -> WorkerReceipt
    - get_status(worker_job_id: str) -> WorkerReceipt
    - get_artifacts(worker_job_id: str) -> list[WorkerArtifact]
    - cancel(worker_job_id: str) -> bool
    """

    @property
    @abstractmethod
    def worker_id(self) -> str:
        """Unique worker identifier."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL of the worker service."""
        pass

    @abstractmethod
    async def health_check(self) -> WorkerHealth:
        """Check if the worker is healthy."""
        pass

    @abstractmethod
    async def get_capabilities(self) -> WorkerCapabilities:
        """Get the worker's capabilities."""
        pass

    @abstractmethod
    async def dispatch(self, job_request: WorkerJobRequest) -> WorkerReceipt:
        """Dispatch a job to the worker."""
        pass

    @abstractmethod
    async def get_status(self, worker_job_id: str) -> WorkerReceipt:
        """Get job status from the worker."""
        pass

    @abstractmethod
    async def get_artifacts(self, worker_job_id: str) -> list[WorkerArtifact]:
        """Get artifacts from the worker."""
        pass

    @abstractmethod
    async def cancel(self, worker_job_id: str) -> bool:
        """Cancel a job on the worker."""
        pass
