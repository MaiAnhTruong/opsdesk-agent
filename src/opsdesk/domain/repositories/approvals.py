from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import ApprovalDecision
from ..models import ApprovalRecord


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self.session.get(ApprovalRecord, approval_id)

    def list_for_case(self, case_id: str) -> list[ApprovalRecord]:
        stmt = select(ApprovalRecord).where(ApprovalRecord.case_id == case_id).order_by(ApprovalRecord.created_at.asc())
        return list(self.session.scalars(stmt))

    def list_expired_pending(self, *, limit: int = 100) -> list[ApprovalRecord]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.decision == ApprovalDecision.PENDING)
            .where(ApprovalRecord.expires_at.is_not(None))
            .where(ApprovalRecord.expires_at <= now)
            .order_by(ApprovalRecord.expires_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_pending_near_expiry(
        self,
        *,
        remind_before_hours: int,
        cooldown_minutes: int,
        limit: int = 100,
    ) -> list[ApprovalRecord]:
        now = datetime.now(timezone.utc)
        remind_before = now + timedelta(hours=remind_before_hours)
        cooldown_cutoff = now - timedelta(minutes=cooldown_minutes)
        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.decision == ApprovalDecision.PENDING)
            .where(ApprovalRecord.expires_at.is_not(None))
            .where(ApprovalRecord.expires_at <= remind_before)
            .where(ApprovalRecord.expires_at > now)
            .where(
                (ApprovalRecord.last_reminded_at.is_(None))
                | (ApprovalRecord.last_reminded_at <= cooldown_cutoff)
            )
            .order_by(ApprovalRecord.expires_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def decide(self, approval_id: str, decision: ApprovalDecision, *, reason: str | None = None) -> ApprovalRecord | None:
        record = self.get(approval_id)
        if record is None:
            return None
        record.decision = decision
        record.reason = reason
        record.decided_at = datetime.now(timezone.utc)
        return record

    def sync_from_state(self, state: dict[str, Any]) -> int:
        approvals = state.get("approvals", [])
        requested_by = state.get("requester", {}).get("actor_id", "system")
        for approval in approvals:
            record = self.session.get(ApprovalRecord, approval["approval_id"])
            approval_type = approval.get("approval_type", f"{state.get('workflow_type', 'unknown')}:default")
            if record is None:
                record = ApprovalRecord(
                    id=approval["approval_id"],
                    case_id=state["case_id"],
                    approval_type=approval_type,
                    requested_from_actor_id=approval["requested_from"]["actor_id"],
                    requested_by_actor_id=requested_by,
                )
                self.session.add(record)

            record.approval_type = approval_type
            record.requested_from_actor_id = approval["requested_from"]["actor_id"]
            record.requested_by_actor_id = requested_by
            record.decision = ApprovalDecision(approval["status"])
            record.reason = approval.get("decision_reason")
            expires_at = approval.get("expires_at")
            record.expires_at = datetime.fromisoformat(expires_at) if expires_at else None
            if record.decision in {ApprovalDecision.APPROVED, ApprovalDecision.DENIED, ApprovalDecision.EXPIRED} and record.decided_at is None:
                record.decided_at = datetime.now(timezone.utc)
        return len(approvals)
