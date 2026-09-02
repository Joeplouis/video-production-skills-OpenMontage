"""
Capability Registry Service — VPMS
"""

from typing import Optional
from sqlalchemy.orm import Session

from vpms.db.repositories.worker_repository import CapabilityRepository


class CapabilityRegistryService:
    """Service for managing the capability registry."""

    def __init__(self, session: Session):
        self._repo = CapabilityRepository(session)

    def list_all(
        self,
        capability: Optional[str] = None,
        visibility: Optional[str] = None,
    ) -> list:
        """List all capabilities."""
        return self._repo.list_all(capability=capability, visibility=visibility)

    def get_capability(self, worker_id: str, capability: str) -> Optional[object]:
        """Get a specific capability."""
        return self._repo.get_capability(worker_id, capability)

    def find_dispatchable(
        self, capability: str, visibility: str = "internal"
    ) -> list:
        """
        Find capabilities that can accept production dispatch.
        A capability is dispatchable only when all verification flags are true.
        """
        return self._repo.find_dispatchable(capability, visibility)

    def can_dispatch(self, worker_id: str, capability: str) -> bool:
        """Check if a specific capability is dispatchable."""
        cap = self._repo.get_capability(worker_id, capability)
        if not cap:
            return False
        return cap.is_dispatchable()

    def update_verification(
        self,
        worker_id: str,
        capability: str,
        code_present: Optional[bool] = None,
        credential_verified: Optional[bool] = None,
        integration_verified: Optional[bool] = None,
        production_verified: Optional[bool] = None,
        healthy: Optional[bool] = None,
    ) -> Optional[object]:
        """Update verification flags for a capability."""
        fields = {}
        if code_present is not None:
            fields["code_present"] = code_present
        if credential_verified is not None:
            fields["credential_verified"] = credential_verified
        if integration_verified is not None:
            fields["integration_verified"] = integration_verified
        if production_verified is not None:
            fields["production_verified"] = production_verified
        if healthy is not None:
            fields["healthy"] = healthy

        return self._repo.upsert(worker_id, capability, **fields)
