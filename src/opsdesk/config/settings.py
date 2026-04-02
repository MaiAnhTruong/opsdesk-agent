from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    app_name: str = "opsdesk-agent"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    database_url: str = "sqlite+pysqlite:///./opsdesk.db"
    database_auto_create: bool = True
    langgraph_checkpointer_dsn: str = ""
    tenant_id: str = "default"
    enable_langsmith: bool = False
    sla_escalation_cooldown_minutes: int = 60
    approval_timeout_hours: int = 24
    approval_reminder_hours: int = 6
    approval_reminder_cooldown_minutes: int = 240
    artifact_storage_root: str = "./opsdesk-objects"
    artifact_base_url: str = "http://localhost:8000/objects"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("OPSDESK_APP_NAME", "opsdesk-agent"),
        app_env=os.getenv("OPSDESK_APP_ENV", "development"),
        app_version=os.getenv("OPSDESK_APP_VERSION", "0.1.0"),
        api_prefix=os.getenv("OPSDESK_API_PREFIX", "/api"),
        database_url=os.getenv("OPSDESK_DATABASE_URL", "sqlite+pysqlite:///./opsdesk.db"),
        database_auto_create=os.getenv("OPSDESK_DATABASE_AUTO_CREATE", "true").lower() in {"1", "true", "yes"},
        langgraph_checkpointer_dsn=os.getenv("OPSDESK_LANGGRAPH_CHECKPOINTER_DSN", ""),
        tenant_id=os.getenv("OPSDESK_TENANT_ID", "default"),
        enable_langsmith=os.getenv("LANGSMITH_TRACING", "").lower() in {"1", "true", "yes"},
        sla_escalation_cooldown_minutes=int(os.getenv("OPSDESK_SLA_ESCALATION_COOLDOWN_MINUTES", "60")),
        approval_timeout_hours=int(os.getenv("OPSDESK_APPROVAL_TIMEOUT_HOURS", "24")),
        approval_reminder_hours=int(os.getenv("OPSDESK_APPROVAL_REMINDER_HOURS", "6")),
        approval_reminder_cooldown_minutes=int(os.getenv("OPSDESK_APPROVAL_REMINDER_COOLDOWN_MINUTES", "240")),
        artifact_storage_root=os.getenv("OPSDESK_ARTIFACT_STORAGE_ROOT", "./opsdesk-objects"),
        artifact_base_url=os.getenv("OPSDESK_ARTIFACT_BASE_URL", "http://localhost:8000/objects"),
    )
