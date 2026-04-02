from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLogRecord


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, case_id: str, event_type: str, actor_id: str, summary: str, payload: dict[str, Any]) -> AuditLogRecord:
        record = AuditLogRecord(
            id=uuid4().hex,
            case_id=case_id,
            event_type=event_type,
            actor_id=actor_id,
            summary=summary,
            payload=payload,
        )
        self.session.add(record)
        return record

    def list_for_case(self, case_id: str, *, limit: int = 200) -> list[AuditLogRecord]:
        stmt = (
            select(AuditLogRecord)
            .where(AuditLogRecord.case_id == case_id)
            .order_by(AuditLogRecord.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))
