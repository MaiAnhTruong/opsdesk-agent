from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..enums import CasePriority, CaseStatus, WorkflowType
from ..models import CaseRecord


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, case_id: str) -> CaseRecord | None:
        return self.session.get(CaseRecord, case_id)

    def update_external_ticket(self, case_id: str, external_ticket_id: str) -> CaseRecord | None:
        case = self.get(case_id)
        if case is None:
            return None
        case.external_ticket_id = external_ticket_id
        return case

    def update_assignment(
        self,
        case_id: str,
        *,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        status: str | None = None,
    ) -> CaseRecord | None:
        case = self.get(case_id)
        if case is None:
            return None

        if assigned_team is not None:
            case.assigned_team = assigned_team
        if assigned_operator_id is not None:
            case.assigned_operator_id = assigned_operator_id
        if status is not None:
            case.status = CaseStatus(status)
            self._update_terminal_timestamps(case, status)
        return case

    def count_cases(
        self,
        *,
        statuses: list[str] | None = None,
        workflow_types: list[str] | None = None,
        priorities: list[str] | None = None,
        channels: list[str] | None = None,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        has_external_ticket: bool | None = None,
        query: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(CaseRecord)
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            workflow_types=workflow_types,
            priorities=priorities,
            channels=channels,
            assigned_team=assigned_team,
            assigned_operator_id=assigned_operator_id,
            has_external_ticket=has_external_ticket,
            query=query,
        )
        return int(self.session.scalar(stmt) or 0)

    def list_cases(
        self,
        *,
        statuses: list[str] | None = None,
        workflow_types: list[str] | None = None,
        priorities: list[str] | None = None,
        channels: list[str] | None = None,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        has_external_ticket: bool | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CaseRecord]:
        stmt = select(CaseRecord)
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            workflow_types=workflow_types,
            priorities=priorities,
            channels=channels,
            assigned_team=assigned_team,
            assigned_operator_id=assigned_operator_id,
            has_external_ticket=has_external_ticket,
            query=query,
        )
        stmt = stmt.order_by(CaseRecord.updated_at.desc()).offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def list_active_cases(self, *, limit: int = 100) -> list[CaseRecord]:
        active_statuses = [
            CaseStatus.NEW.value,
            CaseStatus.TRIAGED.value,
            CaseStatus.WAITING_FOR_REQUESTER.value,
            CaseStatus.WAITING_FOR_APPROVAL.value,
            CaseStatus.PLANNED.value,
            CaseStatus.IN_PROGRESS.value,
            CaseStatus.PARTIALLY_COMPLETED.value,
        ]
        return self.list_cases(statuses=active_statuses, limit=limit)

    def upsert_from_state(self, state: dict[str, Any]) -> CaseRecord:
        case = self.get(state["case_id"])
        if case is None:
            case = CaseRecord(
                id=state["case_id"],
                tenant_id=state.get("tenant_id", "default"),
                channel=state.get("channel", "api"),
                workflow_type=WorkflowType(state.get("workflow_type", WorkflowType.UNKNOWN.value)),
                intent=state.get("intent", WorkflowType.UNKNOWN.value),
                priority=CasePriority(state.get("priority", CasePriority.NORMAL.value)),
                status=CaseStatus(state.get("status", CaseStatus.NEW.value)),
                current_stage=state.get("current_stage", "intake"),
                requester_id=state.get("requester", {}).get("actor_id", ""),
                requester_email=state.get("requester", {}).get("email", ""),
                title=state.get("title", "Employee request"),
            )
            self.session.add(case)

        case.tenant_id = state.get("tenant_id", case.tenant_id)
        case.channel = state.get("channel", case.channel)
        case.workflow_type = WorkflowType(state.get("workflow_type", case.workflow_type.value))
        case.intent = state.get("intent", case.intent)
        case.priority = CasePriority(state.get("priority", case.priority.value))
        case.status = CaseStatus(state.get("status", case.status.value))
        case.current_stage = state.get("current_stage", case.current_stage)
        case.requester_id = state.get("requester", {}).get("actor_id", case.requester_id)
        case.requester_email = state.get("requester", {}).get("email", case.requester_email)
        case.subject_employee_id = state.get("subject_employee", {}).get("actor_id")
        case.title = state.get("title", case.title)
        case.summary = self._summary_from_state(state)
        case.metadata_json = self._metadata_from_state(state)
        self._update_terminal_timestamps(case, case.status.value)
        return case

    @staticmethod
    def to_state_projection(case: CaseRecord) -> dict[str, Any]:
        return {
            "case_id": case.id,
            "tenant_id": case.tenant_id,
            "external_ticket_id": case.external_ticket_id,
            "channel": case.channel,
            "workflow_type": case.workflow_type.value,
            "intent": case.intent,
            "priority": case.priority.value,
            "status": case.status.value,
            "current_stage": case.current_stage,
            "subject_employee_id": case.subject_employee_id,
            "title": case.title,
            "summary": case.summary,
            "assigned_team": case.assigned_team,
            "assigned_operator_id": case.assigned_operator_id,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
            "requester": {
                "actor_id": case.requester_id,
                "actor_type": "employee",
                "email": case.requester_email,
                "display_name": case.requester_email,
            },
            **(case.metadata_json or {}),
        }

    @staticmethod
    def to_inbox_projection(case: CaseRecord) -> dict[str, Any]:
        projection = CaseRepository.to_state_projection(case)
        metadata = case.metadata_json or {}
        approvals = metadata.get("approvals", [])
        pending_actions = metadata.get("pending_actions", [])
        results_by_id = {
            result["action_id"]: result
            for result in metadata.get("action_results", [])
            if isinstance(result, dict) and result.get("action_id")
        }
        requester_updates = metadata.get("requester_updates", [])
        sla = metadata.get("sla", {})
        return {
            **projection,
            "pending_approval_count": sum(1 for approval in approvals if approval.get("status") == "pending"),
            "open_action_count": sum(
                1
                for action in pending_actions
                if results_by_id.get(action.get("action_id"), {}).get("status", "pending") in {"pending", "failed"}
            ),
            "breach_risk": sla.get("breach_risk", "low"),
            "last_requester_update": requester_updates[-1] if requester_updates else None,
        }

    @staticmethod
    def _summary_from_state(state: dict[str, Any]) -> str:
        updates = state.get("requester_updates", [])
        if updates:
            return str(updates[-1])
        return str(state.get("latest_user_message", state.get("title", "Employee request")))

    @staticmethod
    def _metadata_from_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "thread_id": state.get("thread_id"),
            "latest_user_message": state.get("latest_user_message"),
            "normalized_request": state.get("normalized_request", {}),
            "extracted_entities": state.get("extracted_entities", {}),
            "missing_fields": state.get("missing_fields", []),
            "plan_steps": state.get("plan_steps", []),
            "pending_actions": state.get("pending_actions", []),
            "action_results": state.get("action_results", []),
            "approvals": state.get("approvals", []),
            "requester_updates": state.get("requester_updates", []),
            "operator_notes": state.get("operator_notes", []),
            "knowledge_citations": state.get("knowledge_citations", []),
            "policy_citations": state.get("policy_citations", []),
            "sla": state.get("sla", {}),
            "last_error": state.get("last_error"),
        }

    @staticmethod
    def _apply_filters(
        stmt,
        *,
        statuses: list[str] | None = None,
        workflow_types: list[str] | None = None,
        priorities: list[str] | None = None,
        channels: list[str] | None = None,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        has_external_ticket: bool | None = None,
        query: str | None = None,
    ):
        if statuses:
            stmt = stmt.where(CaseRecord.status.in_(statuses))
        if workflow_types:
            stmt = stmt.where(CaseRecord.workflow_type.in_(workflow_types))
        if priorities:
            stmt = stmt.where(CaseRecord.priority.in_(priorities))
        if channels:
            stmt = stmt.where(CaseRecord.channel.in_(channels))
        if assigned_team:
            stmt = stmt.where(CaseRecord.assigned_team == assigned_team)
        if assigned_operator_id:
            stmt = stmt.where(CaseRecord.assigned_operator_id == assigned_operator_id)
        if has_external_ticket is True:
            stmt = stmt.where(CaseRecord.external_ticket_id.is_not(None))
        elif has_external_ticket is False:
            stmt = stmt.where(CaseRecord.external_ticket_id.is_(None))
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    CaseRecord.id.ilike(pattern),
                    CaseRecord.external_ticket_id.ilike(pattern),
                    CaseRecord.requester_email.ilike(pattern),
                    CaseRecord.title.ilike(pattern),
                    CaseRecord.summary.ilike(pattern),
                    CaseRecord.metadata_json["latest_user_message"].as_string().ilike(pattern),
                )
            )
        return stmt

    @staticmethod
    def _update_terminal_timestamps(case: CaseRecord, status: str) -> None:
        now = datetime.now(timezone.utc)
        if status == CaseStatus.RESOLVED.value and case.resolved_at is None:
            case.resolved_at = now
        if status == CaseStatus.CLOSED.value:
            if case.resolved_at is None:
                case.resolved_at = now
            if case.closed_at is None:
                case.closed_at = now
