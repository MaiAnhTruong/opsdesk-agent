from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CaseCommentRecord


class CaseCommentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        case_id: str,
        author_actor_id: str,
        visibility: str,
        body: str,
    ) -> CaseCommentRecord:
        record = CaseCommentRecord(
            id=uuid4().hex,
            case_id=case_id,
            author_actor_id=author_actor_id,
            visibility=visibility,
            body=body,
        )
        self.session.add(record)
        return record

    def list_for_case(self, case_id: str) -> list[CaseCommentRecord]:
        stmt = select(CaseCommentRecord).where(CaseCommentRecord.case_id == case_id).order_by(CaseCommentRecord.created_at.asc())
        return list(self.session.scalars(stmt))
