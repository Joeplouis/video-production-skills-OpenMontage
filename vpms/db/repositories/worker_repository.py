"""
VPMS Worker Repository — Database operations for workers.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from vpms.db.models import WorkerRegistry, WorkerCapability, WorkerJob


class WorkerRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_worker(self, worker_id: str) -> Optional[WorkerRegistry]:
        """Get a worker by ID."""
        stmt = select(WorkerRegistry).where(WorkerRegistry.worker_id == worker_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_workers(
        self,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list[WorkerRegistry]:
        """List workers with optional filters."""
        stmt = select(WorkerRegistry).where(WorkerRegistry.is_active == True)
        if status:
            stmt = stmt.where(WorkerRegistry.status == status)
        if visibility:
            stmt = stmt.where(WorkerRegistry.visibility == visibility)
        return list(self._session.execute(stmt).scalars().all())

    def update_health(
        self, worker_id: str, health_status: str
    ) -> Optional[WorkerRegistry]:
        """Update worker health status."""
        worker = self.get_worker(worker_id)
        if worker:
            worker.health_status = health_status
            worker.last_health_check = datetime.now(timezone.utc)
            self._session.flush()
        return worker


class CapabilityRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_capability(
        self, worker_id: str, capability: str
    ) -> Optional[WorkerCapability]:
        """Get a specific capability."""
        stmt = select(WorkerCapability).where(
            and_(
                WorkerCapability.worker_id == worker_id,
                WorkerCapability.capability == capability,
                WorkerCapability.is_active == True,
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_for_worker(self, worker_id: str) -> list[WorkerCapability]:
        """List all capabilities for a worker."""
        stmt = select(WorkerCapability).where(
            and_(
                WorkerCapability.worker_id == worker_id,
                WorkerCapability.is_active == True,
            )
        )
        return list(self._session.execute(stmt).scalars().all())

    def find_dispatchable(
        self, capability: str, visibility: str = "internal"
    ) -> list[WorkerCapability]:
        """Find dispatchable capabilities (verified + healthy)."""
        stmt = select(WorkerCapability).where(
            and_(
                WorkerCapability.capability == capability,
                WorkerCapability.is_active == True,
                WorkerCapability.visibility == visibility,
                WorkerCapability.code_present == True,
                WorkerCapability.credential_verified == True,
                WorkerCapability.integration_verified == True,
                WorkerCapability.healthy == True,
            )
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_all(
        self,
        capability: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list[WorkerCapability]:
        """List all capabilities."""
        stmt = select(WorkerCapability).where(WorkerCapability.is_active == True)
        if capability:
            stmt = stmt.where(WorkerCapability.capability == capability)
        if visibility:
            stmt = stmt.where(WorkerCapability.visibility == visibility)
        return list(self._session.execute(stmt).scalars().all())

    def upsert(
        self,
        worker_id: str,
        capability: str,
        **fields,
    ) -> WorkerCapability:
        """Insert or update a capability."""
        existing = self.get_capability(worker_id, capability)
        if existing:
            for key, value in fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            self._session.flush()
            return existing
        else:
            cap = WorkerCapability(
                worker_id=worker_id,
                capability=capability,
                **fields,
            )
            self._session.add(cap)
            self._session.flush()
            return cap
