"""
VPMS Artifact Repository — Database operations for artifacts.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from vpms.db.models import Artifact, Approval, QAReport, WorkerJob


class ArtifactRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        job_id: str,
        artifact_type: str,
        name: str,
        worker_job_id: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        checksum: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Artifact:
        """Register an artifact."""
        artifact = Artifact(
            job_id=job_id,
            artifact_type=artifact_type,
            name=name,
            worker_job_id=worker_job_id,
            url=url,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            checksum=checksum,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            metadata=metadata or {},
        )
        self._session.add(artifact)
        self._session.flush()
        return artifact

    def list_for_job(self, job_id: str) -> list[Artifact]:
        """List all artifacts for a job."""
        stmt = select(Artifact).where(Artifact.job_id == job_id)
        return list(self._session.execute(stmt).scalars().all())


class ApprovalRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        job_id: str,
        approval_type: str,
        decision: str,
        approved_by: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Approval:
        """Record an approval decision."""
        approval = Approval(
            job_id=job_id,
            approval_type=approval_type,
            decision=decision,
            approved_by=approved_by,
            notes=notes,
            metadata=metadata or {},
        )
        self._session.add(approval)
        self._session.flush()
        return approval

    def list_for_job(self, job_id: str) -> list[Approval]:
        """List all approvals for a job."""
        stmt = select(Approval).where(Approval.job_id == job_id)
        return list(self._session.execute(stmt).scalars().all())


class QAReportRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(
        self,
        job_id: str,
        qa_type: str,
        scores: dict,
        issues: list,
        required_fixes: list,
        decision: str,
        metadata: Optional[dict] = None,
    ) -> QAReport:
        """Create a QA report."""
        report = QAReport(
            job_id=job_id,
            qa_type=qa_type,
            scores=scores,
            issues=issues,
            required_fixes=required_fixes,
            decision=decision,
            metadata=metadata or {},
        )
        self._session.add(report)
        self._session.flush()
        return report

    def list_for_job(self, job_id: str) -> list[QAReport]:
        """List all QA reports for a job."""
        stmt = select(QAReport).where(QAReport.job_id == job_id)
        return list(self._session.execute(stmt).scalars().all())
