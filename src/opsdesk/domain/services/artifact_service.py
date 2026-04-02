from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...storage import ObjectStorageService, create_object_storage_service, get_sessionmaker
from ..repositories import AuditLogRepository, CaseArtifactRepository, CaseEventRepository, CaseRepository


@dataclass
class ArtifactService:
    session_factory: sessionmaker[Session]
    object_storage: ObjectStorageService

    @contextmanager
    def _session_scope(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_case_artifacts(self, case_id: str) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            if CaseRepository(session).get(case_id) is None:
                return []
            artifacts = CaseArtifactRepository(session).list_for_case(case_id)
            return [self._serialize(artifact) for artifact in artifacts]

    def issue_upload(
        self,
        case_id: str,
        *,
        actor_id: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        visibility: str,
        artifact_type: str,
    ) -> dict[str, Any]:
        upload_spec = self.object_storage.build_upload_spec(case_id=case_id, file_name=file_name)
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return {}

            artifact = CaseArtifactRepository(session).create(
                case_id=case_id,
                artifact_type=artifact_type,
                visibility=visibility,
                file_name=file_name,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_key=upload_spec.storage_key,
                upload_token=upload_spec.upload_token,
                uploaded_by_actor_id=actor_id,
            )
            payload = {
                "artifact_id": artifact.id,
                "file_name": file_name,
                "visibility": visibility,
                "artifact_type": artifact_type,
                "storage_key": upload_spec.storage_key,
            }
            summary = f"Artifact upload issued for {file_name}."
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="artifact_upload_requested",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="artifact_upload_requested",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            serialized = self._serialize(artifact)
            serialized["upload"] = {
                "storage_key": upload_spec.storage_key,
                "upload_token": upload_spec.upload_token,
                "upload_url": upload_spec.upload_url,
                "download_url": upload_spec.download_url,
                "expires_at": upload_spec.expires_at,
                "method": upload_spec.method,
            }
            return serialized

    def complete_upload(
        self,
        case_id: str,
        artifact_id: str,
        *,
        actor_id: str,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return {}

            artifact = CaseArtifactRepository(session).get(artifact_id)
            if artifact is None or artifact.case_id != case_id:
                return {}

            artifact = CaseArtifactRepository(session).mark_uploaded(artifact_id, checksum=checksum)
            if artifact is None:
                return {}

            payload = {
                "artifact_id": artifact.id,
                "file_name": artifact.file_name,
                "visibility": artifact.visibility,
                "download_url": self.object_storage.build_download_url(artifact.storage_key),
            }
            summary = f"Artifact upload completed for {artifact.file_name}."
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="artifact_upload_completed",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="artifact_upload_completed",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return self._serialize(artifact)

    def get_artifact(self, case_id: str, artifact_id: str) -> dict[str, Any]:
        with self._session_scope() as session:
            artifact = CaseArtifactRepository(session).get(artifact_id)
            if artifact is None or artifact.case_id != case_id:
                return {}
            return self._serialize(artifact)

    def _serialize(self, artifact) -> dict[str, Any]:
        return {
            "artifact_id": artifact.id,
            "case_id": artifact.case_id,
            "artifact_type": artifact.artifact_type,
            "visibility": artifact.visibility,
            "file_name": artifact.file_name,
            "content_type": artifact.content_type,
            "size_bytes": artifact.size_bytes,
            "storage_key": artifact.storage_key,
            "status": artifact.status,
            "checksum": artifact.checksum,
            "uploaded_by_actor_id": artifact.uploaded_by_actor_id,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
            "uploaded_at": artifact.uploaded_at.isoformat() if artifact.uploaded_at else None,
            "download_url": self.object_storage.build_download_url(artifact.storage_key),
        }


def create_artifact_service(object_storage: ObjectStorageService | None = None) -> ArtifactService:
    return ArtifactService(
        session_factory=get_sessionmaker(),
        object_storage=object_storage or create_object_storage_service(),
    )
