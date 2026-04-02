from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import ActionStatus, ApprovalMode, RiskLevel
from ..models import CaseActionRecord


class ActionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_case(self, case_id: str) -> list[CaseActionRecord]:
        stmt = select(CaseActionRecord).where(CaseActionRecord.case_id == case_id).order_by(CaseActionRecord.sequence_no.asc())
        return list(self.session.scalars(stmt))

    def sync_from_state(self, state: dict[str, Any]) -> int:
        actions = state.get("pending_actions", [])
        results_by_id = {
            result["action_id"]: result
            for result in state.get("action_results", [])
            if isinstance(result, dict) and result.get("action_id")
        }
        for index, action in enumerate(actions, start=1):
            record = self.session.get(CaseActionRecord, action["action_id"])
            if record is None:
                record = CaseActionRecord(
                    id=action["action_id"],
                    case_id=state["case_id"],
                    sequence_no=index,
                    action_type=action["action_type"],
                    target_system=action["target_system"],
                    target_resource=action.get("target_resource", ""),
                    risk_level=RiskLevel(action["risk_level"]),
                    approval_mode=ApprovalMode(action["approval_mode"]),
                    idempotency_key=action["idempotency_key"],
                )
                self.session.add(record)

            result = results_by_id.get(action["action_id"], {})
            record.sequence_no = index
            record.action_type = action["action_type"]
            record.target_system = action["target_system"]
            record.target_resource = action.get("target_resource", "")
            record.risk_level = RiskLevel(action["risk_level"])
            record.approval_mode = ApprovalMode(action["approval_mode"])
            record.status = ActionStatus(result.get("status", ActionStatus.PENDING.value))
            record.idempotency_key = action["idempotency_key"]
            record.request_payload = action.get("payload", {})
            record.result_payload = result or None
            record.error_code = result.get("error_code")
            record.error_detail = result.get("summary") if result.get("status") == ActionStatus.FAILED.value else None
        return len(actions)
