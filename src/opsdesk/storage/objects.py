from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from ..config import Settings, get_settings


@dataclass(frozen=True)
class UploadSpec:
    storage_key: str
    upload_token: str
    upload_url: str
    download_url: str
    expires_at: str
    method: str = "PUT"


@dataclass
class ObjectStorageService:
    root: Path
    base_url: str

    def build_upload_spec(self, *, case_id: str, file_name: str) -> UploadSpec:
        cleaned_name = self._sanitize_file_name(file_name)
        artifact_id = uuid4().hex
        storage_key = f"cases/{case_id}/{artifact_id}/{cleaned_name}"
        upload_token = uuid4().hex
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        upload_url = f"{self.base_url.rstrip('/')}/{storage_key}?upload_token={upload_token}"
        download_url = f"{self.base_url.rstrip('/')}/{storage_key}"
        return UploadSpec(
            storage_key=storage_key,
            upload_token=upload_token,
            upload_url=upload_url,
            download_url=download_url,
            expires_at=expires_at,
        )

    def build_download_url(self, storage_key: str) -> str:
        return f"{self.base_url.rstrip('/')}/{storage_key}"

    @staticmethod
    def _sanitize_file_name(file_name: str) -> str:
        raw_name = file_name.strip() or "artifact.bin"
        return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw_name)


def create_object_storage_service(settings: Settings | None = None) -> ObjectStorageService:
    resolved_settings = settings or get_settings()
    return ObjectStorageService(
        root=Path(resolved_settings.artifact_storage_root),
        base_url=resolved_settings.artifact_base_url,
    )
