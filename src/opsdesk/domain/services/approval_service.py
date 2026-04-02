from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...storage import get_sessionmaker
from ..enums import ApprovalDecision
from ..repositories import ApprovalRepository, AuditLogRepository, CaseEventRepository


@dataclass
class ApprovalService:
    session_factory: sessionmaker[Session]

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

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._session_scope() as session:
            record = ApprovalRepository(session).get(approval_id)
            if record is None:
                return None
            return self._serialize(record)

    def list_for_case(self, case_id: str) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            records = ApprovalRepository(session).list_for_case(case_id)
            return [self._serialize(record) for record in records]

    def list_expired_pending(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            records = ApprovalRepository(session).list_expired_pending(limit=limit)
            return [self._serialize(record) for record in records]

    def list_pending_near_expiry(
        self,
        *,
        remind_before_hours: int,
        cooldown_minutes: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            records = ApprovalRepository(session).list_pending_near_expiry(
                remind_before_hours=remind_before_hours,
                cooldown_minutes=cooldown_minutes,
                limit=limit,
            )
            return [self._serialize(record) for record in records]

    def record_reminder(self, approval_id: str, *, actor_id: str, reason: str | None = None) -> dict[str, Any] | None:
        with self._session_scope() as session:
            repository = ApprovalRepository(session)
            record = repository.get(approval_id)
            if record is None:
                return None
            if record.decision != ApprovalDecision.PENDING:
                return None

            record.last_reminded_at = datetime.now(timezone.utc)
            summary = f"Approval reminder sent for {approval_id}."
            payload = {"approval_id": approval_id, "reason": reason}
            AuditLogRepository(session).create(
                case_id=record.case_id,
                event_type="approval_reminder",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=record.case_id,
                event_type="approval_reminder",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return self._serialize(record)

    def decide(self, approval_id: str, *, approved: bool, actor_id: str, reason: str | None = None) -> dict[str, Any] | None:
        with self._session_scope() as session:
            repository = ApprovalRepository(session)
            existing = repository.get(approval_id)
            if existing is None:
                return None
            if existing.decision != ApprovalDecision.PENDING:
                raise ValueError(f"Approval {approval_id} has already been decided.")

            decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.DENIED
            record = repository.decide(approval_id, decision, reason=reason)

            summary = f"Approval {approval_id} set to {decision.value}."
            AuditLogRepository(session).create(
                case_id=record.case_id,
                event_type="approval_decision",
                actor_id=actor_id,
                summary=summary,
                payload={"approval_id": approval_id, "decision": decision.value, "reason": reason},
            )
            CaseEventRepository(session).create(
                case_id=record.case_id,
                event_type="approval_decision",
                actor_id=actor_id,
                summary=summary,
                payload={"approval_id": approval_id, "decision": decision.value, "reason": reason},
            )
            return self._serialize(record)

    @staticmethod
    def _serialize(record) -> dict[str, Any]:
        return {
            "approval_id": record.id,
            "case_id": record.case_id,
            "approval_type": record.approval_type,
            "requested_from_actor_id": record.requested_from_actor_id,
            "requested_by_actor_id": record.requested_by_actor_id,
            "decision": record.decision.value,
            "reason": record.reason,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "last_reminded_at": record.last_reminded_at.isoformat() if record.last_reminded_at else None,
            "decided_at": record.decided_at.isoformat() if record.decided_at else None,
        }


def create_approval_service() -> ApprovalService:
    return ApprovalService(session_factory=get_sessionmaker())
