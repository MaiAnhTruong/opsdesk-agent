from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CaseArtifactRecord


class CaseArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, artifact_id: str) -> CaseArtifactRecord | None:
        return self.session.get(CaseArtifactRecord, artifact_id)

    def create(
        self,
        *,
        case_id: str,
        artifact_type: str,
        visibility: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
        upload_token: str,
        uploaded_by_actor_id: str,
    ) -> CaseArtifactRecord:
        record = CaseArtifactRecord(
            id=uuid4().hex,
            case_id=case_id,
            artifact_type=artifact_type,
            visibility=visibility,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            upload_token=upload_token,
            status="pending_upload",
            uploaded_by_actor_id=uploaded_by_actor_id,
        )
        self.session.add(record)
        return record

    def list_for_case(self, case_id: str) -> list[CaseArtifactRecord]:
        stmt = select(CaseArtifactRecord).where(CaseArtifactRecord.case_id == case_id).order_by(CaseArtifactRecord.created_at.asc())
        return list(self.session.scalars(stmt))

    def mark_uploaded(self, artifact_id: str, *, checksum: str | None = None) -> CaseArtifactRecord | None:
        record = self.get(artifact_id)
        if record is None:
            return None
        record.status = "available"
        record.checksum = checksum
        record.uploaded_at = datetime.now(timezone.utc)
        return record
