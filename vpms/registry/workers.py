"""
Worker Registry Service — VPMS
"""

from typing import Optional
from sqlalchemy.orm import Session

from vpms.db.repositories.worker_repository import WorkerRepository


class WorkerRegistryService:
    """Service for managing the worker registry."""

    def __init__(self, session: Session):
        self._repo = WorkerRepository(session)

    def list_workers(
        self,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list:
        """List all active workers."""
        return self._repo.list_workers(status=status, visibility=visibility)

    def get_worker(self, worker_id: str) -> Optional[object]:
        """Get a specific worker."""
        return self._repo.get_worker(worker_id)

    def update_health(self, worker_id: str, health_status: str) -> Optional[object]:
        """Update worker health status."""
        return self._repo.update_health(worker_id, health_status)

    def is_available(self, worker_id: str) -> bool:
        """Check if a worker is available."""
        worker = self._repo.get_worker(worker_id)
        if not worker:
            return False
        return (
            worker.status == "AVAILABLE"
            and worker.health_status == "HEALTHY"
            and worker.is_active
        )
