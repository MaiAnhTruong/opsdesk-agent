from __future__ import annotations

from typing import Any, Callable

from ...domain.enums import CaseStatus, RuntimeStage
from ...connectors import DomainToolExecutor
from ..state import ActionResult, CaseState


def execute_pending_actions(
    state: CaseState,
    execute_action: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    results: list[ActionResult] = []
    requester_updates = list(state.get("requester_updates", []))
    knowledge_citations = list(state.get("knowledge_citations", []))

    for action in state.get("pending_actions", []):
        policy_decision = action.get("policy_decision", "auto_allow")
        if policy_decision == "deny":
            results.append(
                {
                    "action_id": action["action_id"],
                    "status": "skipped",
                    "summary": f"Action '{action['action_type']}' was denied by policy.",
                    "error_code": "policy_denied",
                }
            )
            continue

        if policy_decision == "escalate":
            results.append(
                {
                    "action_id": action["action_id"],
                    "status": "skipped",
                    "summary": f"Action '{action['action_type']}' requires escalation.",
                    "error_code": "policy_escalation_required",
                }
            )
            continue

        response = execute_action(state, action)
        if response["ok"]:
            requester_updates.append(response["summary"])
            if action["action_type"] == "retrieve_policy_guidance":
                answer = str(response["raw_result"].get("answer", response["summary"]))
                requester_updates.append(answer)
                citations = response["raw_result"].get("citations", [])
                if isinstance(citations, list):
                    knowledge_citations.extend(citations)
            results.append(
                {
                    "action_id": action["action_id"],
                    "status": "completed",
                    "summary": response["summary"],
                    "external_ref": response["external_ref"] or "",
                    "details": response["raw_result"],
                }
            )
        else:
            requester_updates.append(response["summary"])
            results.append(
                {
                    "action_id": action["action_id"],
                    "status": "failed",
                    "summary": response["summary"],
                    "error_code": response.get("error_code", "connector_execution_failed"),
                    "details": response["raw_result"],
                }
            )

    final_status = resolve_case_status(results)
    requester_updates.append("Execution pass completed.")
    return {
        "action_results": results,
        "status": final_status,
        "current_stage": RuntimeStage.POST_EXECUTION.value,
        "requester_updates": requester_updates,
        "knowledge_citations": knowledge_citations,
    }


def resolve_case_status(results: list[ActionResult]) -> str:
    failed = any(result["status"] == "failed" for result in results)
    pending = any(result["status"] == "pending" for result in results)
    skipped = any(result["status"] == "skipped" for result in results)
    completed = any(result["status"] == "completed" for result in results)

    if pending:
        return CaseStatus.IN_PROGRESS.value
    if failed and completed:
        return CaseStatus.PARTIALLY_COMPLETED.value
    if failed:
        return CaseStatus.FAILED.value
    if skipped:
        return CaseStatus.PARTIALLY_COMPLETED.value
    return CaseStatus.RESOLVED.value


def build_execute_actions_node(domain_tool_executor: DomainToolExecutor):
    execute_task = domain_tool_executor.build_task()

    def execute_actions(state: CaseState) -> CaseState:
        return execute_pending_actions(
            state,
            lambda current_state, action: execute_task(current_state, action).result(),
        )

    return execute_actions
