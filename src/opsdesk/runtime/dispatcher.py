from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.types import Command

from ..connectors import ConnectorRegistry, DomainToolExecutor, build_default_connector_registry, build_default_domain_tool_executor
from ..config import Settings, get_settings
from ..domain.enums import CaseStatus, RuntimeStage
from ..domain.services import (
    CaseService,
    NotificationService,
    SlaService,
    TicketSyncService,
    create_case_service,
    create_notification_service,
    create_sla_service,
    create_ticket_sync_service,
)
from ..policy import PolicyEngine, build_policy_engine
from ..storage.checkpoints import CheckpointerHandle, build_checkpointer
from .graph import build_case_graph
from .nodes.execute import execute_pending_actions, resolve_case_status
from .nodes.permissions import _build_cancelled_results
from .state import CaseState


@dataclass
class CaseGraphDispatcher:
    graph: Any
    checkpointer: CheckpointerHandle
    connector_registry: ConnectorRegistry
    case_service: CaseService
    notification_service: NotificationService
    sla_service: SlaService
    ticket_sync_service: TicketSyncService
    policy_engine: PolicyEngine
    domain_tool_executor: DomainToolExecutor

    def run_case(self, initial_state: CaseState) -> dict[str, Any]:
        try:
            result = self.graph.invoke(initial_state, config=self._config(initial_state["thread_id"]))
        except Exception as exc:
            failed_state = self.sla_service.refresh_state(self._failed_state(initial_state, str(exc)))
            self.case_service.persist_graph_state(failed_state, event_type="case_run_failed")
            self.ticket_sync_service.sync_case(failed_state)
            self.notification_service.notify_requester(failed_state)
            raise
        result = self.sla_service.refresh_state(result)
        self.case_service.persist_graph_state(result, event_type="case_run")
        self.ticket_sync_service.sync_case(result)
        self.notification_service.notify_requester(result)
        return result

    def resume_case(self, case_id: str, resume_value: Any) -> dict[str, Any]:
        try:
            result = self.graph.invoke(Command(resume=resume_value), config=self._config(case_id))
        except Exception as exc:
            failed_state = self.get_case_state(case_id) or {"case_id": case_id, "thread_id": case_id}
            failed_state = self.sla_service.refresh_state(self._failed_state(failed_state, str(exc)))
            self.case_service.persist_graph_state(failed_state, event_type="case_resume_failed")
            self.ticket_sync_service.sync_case(failed_state)
            self.notification_service.notify_requester(failed_state)
            raise
        result = self.sla_service.refresh_state(result)
        self.case_service.persist_graph_state(result, event_type="case_resume")
        self.ticket_sync_service.sync_case(result)
        self.notification_service.notify_requester(result)
        return result

    def retry_case(
        self,
        case_id: str,
        *,
        actor_id: str,
        action_ids: list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        state = self.get_case_state(case_id)
        if not state:
            raise KeyError(case_id)

        if state.get("status") not in {CaseStatus.FAILED.value, CaseStatus.PARTIALLY_COMPLETED.value}:
            raise ValueError(f"Case {case_id} is not retryable from status {state.get('status')}.")

        retry_actions = self._select_retry_actions(state, action_ids=action_ids)
        if not retry_actions:
            raise ValueError(f"No retryable actions found for case {case_id}.")

        retry_action_ids = {action["action_id"] for action in retry_actions}
        preserved_results = [
            result
            for result in state.get("action_results", [])
            if isinstance(result, dict) and result.get("action_id") not in retry_action_ids
        ]

        operator_notes = list(state.get("operator_notes", []))
        operator_notes.append(
            note
            or f"Retry requested by {actor_id} for {len(retry_actions)} failed action(s)."
        )
        requester_updates = list(state.get("requester_updates", []))
        requester_updates.append(f"Retrying {len(retry_actions)} failed action(s).")

        retry_state = {
            **state,
            "pending_actions": retry_actions,
            "action_results": [],
            "operator_notes": operator_notes,
            "requester_updates": requester_updates,
            "status": CaseStatus.IN_PROGRESS.value,
            "current_stage": RuntimeStage.EXECUTION.value,
            "last_error": None,
        }

        retry_result = execute_pending_actions(retry_state, self.domain_tool_executor.execute_action)
        merged_results = preserved_results + retry_result["action_results"]

        updated_state = self.sla_service.refresh_state(
            {
                **state,
                "pending_actions": state.get("pending_actions", []),
                "action_results": merged_results,
                "status": resolve_case_status(merged_results),
                "current_stage": retry_result["current_stage"],
                "requester_updates": retry_result["requester_updates"],
                "knowledge_citations": retry_result["knowledge_citations"],
                "operator_notes": operator_notes,
                "last_error": None,
            }
        )
        self.case_service.persist_graph_state(updated_state, event_type="case_retry", actor_id=actor_id)
        self.ticket_sync_service.sync_case(updated_state, actor_id=actor_id)
        self.notification_service.notify_requester(updated_state, actor_id=actor_id)
        return updated_state

    def expire_case_approval(
        self,
        case_id: str,
        *,
        approval_id: str,
        actor_id: str = "system",
        reason: str | None = None,
    ) -> dict[str, Any]:
        state = self.get_case_state(case_id)
        if not state:
            raise KeyError(case_id)

        matched_approval = None
        updated_approvals = []
        for approval in state.get("approvals", []):
            updated_approval = dict(approval)
            if approval["approval_id"] == approval_id and approval["status"] == "pending":
                updated_approval["status"] = "expired"
                updated_approval["decision_reason"] = reason or "Approval expired before a decision was recorded."
                matched_approval = updated_approval
            updated_approvals.append(updated_approval)

        if matched_approval is None:
            raise ValueError(f"Approval {approval_id} is not pending for case {case_id}.")

        requester_updates = list(state.get("requester_updates", []))
        requester_updates.append("A required approval expired. The request will not be executed automatically.")
        operator_notes = list(state.get("operator_notes", []))
        operator_notes.append(f"Approval {approval_id} expired and the case was cancelled.")

        updated_state = self.sla_service.refresh_state(
            {
                **state,
                "approvals": updated_approvals,
                "status": CaseStatus.CANCELLED.value,
                "current_stage": RuntimeStage.CLOSURE.value,
                "action_results": _build_cancelled_results(state, matched_approval, terminal_error_code="approval_expired"),
                "requester_updates": requester_updates,
                "operator_notes": operator_notes,
            }
        )
        self.case_service.persist_graph_state(updated_state, event_type="approval_expired", actor_id=actor_id)
        self.ticket_sync_service.sync_case(updated_state, actor_id=actor_id)
        self.notification_service.notify_requester(updated_state, actor_id=actor_id)
        return updated_state

    def get_case_state(self, case_id: str) -> dict[str, Any]:
        try:
            snapshot = self.graph.get_state(self._config(case_id))
        except Exception:
            snapshot = None
        if snapshot is not None and getattr(snapshot, "values", None):
            return self.sla_service.refresh_state(dict(snapshot.values))
        return self.sla_service.refresh_state(self.case_service.get_case_projection(case_id))

    def close(self) -> None:
        self.checkpointer.close()

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _failed_state(state: dict[str, Any], error_message: str) -> dict[str, Any]:
        requester_updates = list(state.get("requester_updates", []))
        requester_updates.append("Case execution failed and requires operator attention.")
        return {
            **state,
            "status": CaseStatus.FAILED.value,
            "current_stage": RuntimeStage.CLOSURE.value,
            "last_error": error_message,
            "requester_updates": requester_updates,
        }

    @staticmethod
    def _select_retry_actions(state: dict[str, Any], *, action_ids: list[str] | None = None) -> list[dict[str, Any]]:
        allowed_ids = set(action_ids or [])
        results_by_id = {
            result["action_id"]: result
            for result in state.get("action_results", [])
            if isinstance(result, dict) and result.get("action_id")
        }
        selected_actions = []
        for action in state.get("pending_actions", []):
            action_id = action["action_id"]
            result = results_by_id.get(action_id)
            if result is None or result.get("status") != "failed":
                continue
            if allowed_ids and action_id not in allowed_ids:
                continue
            selected_actions.append(action)
        return selected_actions


def create_dispatcher(
    settings: Settings | None = None,
    *,
    sla_service: SlaService | None = None,
    connector_registry: ConnectorRegistry | None = None,
) -> CaseGraphDispatcher:
    resolved_settings = settings or get_settings()
    checkpointer = build_checkpointer(resolved_settings)
    policy_engine = build_policy_engine()
    resolved_registry = connector_registry or build_default_connector_registry()
    domain_tool_executor = build_default_domain_tool_executor(resolved_registry)
    resolved_sla_service = sla_service or create_sla_service(resolved_settings)
    notification_service = create_notification_service(domain_tool_executor)
    return CaseGraphDispatcher(
        graph=build_case_graph(
            policy_engine=policy_engine,
            domain_tool_executor=domain_tool_executor,
            approval_timeout_hours=resolved_settings.approval_timeout_hours,
            checkpointer=checkpointer.saver,
        ),
        checkpointer=checkpointer,
        connector_registry=resolved_registry,
        case_service=create_case_service(),
        notification_service=notification_service,
        sla_service=resolved_sla_service,
        ticket_sync_service=create_ticket_sync_service(
            connector_registry=resolved_registry,
            domain_tool_executor=domain_tool_executor,
        ),
        policy_engine=policy_engine,
        domain_tool_executor=domain_tool_executor,
    )
