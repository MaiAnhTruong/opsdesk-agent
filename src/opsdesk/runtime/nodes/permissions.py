from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from langgraph.types import Command, interrupt

from ...domain.enums import ApprovalDecision, ApprovalMode, CaseStatus, RuntimeStage
from ...policy import PolicyEngine
from ..interrupts import build_approval_interrupt_payload
from ..state import ActionResult, ActionSpec, ApprovalState, CaseState


def build_evaluate_permissions_node(policy_engine: PolicyEngine, *, approval_timeout_hours: int = 24):
    def evaluate_permissions(state: CaseState) -> Command[Literal["await_approval", "execute_actions", "close_case"]]:
        pending_actions = state.get("pending_actions", [])
        evaluated_actions = []
        operator_notes = list(state.get("operator_notes", []))
        approval_actions = []

        for action in pending_actions:
            decision = policy_engine.evaluate_action(state, action)
            enriched_action = {
                **action,
                "approval_mode": decision.approval_mode.value,
                "policy_decision": decision.decision,
                "policy_reason": decision.reason,
                "requires_human": decision.decision in {"approval_required", "escalate"},
            }
            evaluated_actions.append(enriched_action)
            operator_notes.append(f"Policy evaluated {action['action_type']}: {decision.decision} ({decision.reason})")
            if enriched_action["mode"] == "write" and enriched_action["policy_decision"] in {"approval_required", "escalate"}:
                approval_actions.append(enriched_action)

        if not evaluated_actions:
            return Command(
                update={
                    "status": CaseStatus.RESOLVED.value,
                    "current_stage": RuntimeStage.CLOSURE.value,
                    "requester_updates": [
                        *state.get("requester_updates", []),
                        "No actions were required for this request.",
                    ],
                },
                goto="close_case",
            )

        if approval_actions:
            approvals: list[ApprovalState] = []
            for action in approval_actions:
                approvals.extend(_build_approval_states(state, action, approval_timeout_hours=approval_timeout_hours))
            operator_notes.append(f"Queued {len(approvals)} approval request(s) before execution.")
            return Command(
                update={
                    "pending_actions": evaluated_actions,
                    "status": CaseStatus.WAITING_FOR_APPROVAL.value,
                    "current_stage": RuntimeStage.APPROVAL_WAIT.value,
                    "approvals": approvals,
                    "operator_notes": operator_notes,
                },
                goto="await_approval",
            )

        return Command(
            update={
                "pending_actions": evaluated_actions,
                "operator_notes": operator_notes,
                "status": CaseStatus.IN_PROGRESS.value,
                "current_stage": RuntimeStage.EXECUTION.value,
            },
            goto="execute_actions",
        )

    return evaluate_permissions


def await_approval(state: CaseState) -> Command[Literal["await_approval", "execute_actions", "close_case"]]:
    pending_write_actions = [
        action
        for action in state.get("pending_actions", [])
        if action["mode"] == "write" and action["approval_mode"] not in {"auto", "deny"}
    ]
    pending_approvals = [approval for approval in state.get("approvals", []) if approval.get("status") == ApprovalDecision.PENDING.value]
    actionable_approvals = _get_actionable_approvals(pending_approvals, state.get("approvals", []))

    expired_approvals = [approval for approval in actionable_approvals if _is_approval_expired(approval)]
    if expired_approvals:
        expired_approval = expired_approvals[0]
        updated_approvals = []
        for approval in state.get("approvals", []):
            updated_approval = dict(approval)
            if approval["approval_id"] == expired_approval["approval_id"]:
                updated_approval["status"] = ApprovalDecision.EXPIRED.value
                updated_approval["decision_reason"] = "Approval expired before a decision was recorded."
                expired_approval = updated_approval
            updated_approvals.append(updated_approval)
        return Command(
            update={
                "approvals": updated_approvals,
                "status": CaseStatus.CANCELLED.value,
                "current_stage": RuntimeStage.CLOSURE.value,
                "action_results": _build_cancelled_results(state, expired_approval, terminal_error_code="approval_expired"),
                "requester_updates": [
                    *state.get("requester_updates", []),
                    "A required approval expired. The request will not be executed automatically.",
                ],
                "operator_notes": [
                    *state.get("operator_notes", []),
                    f"Approval {expired_approval['approval_id']} expired before decision.",
                ],
            },
            goto="close_case",
        )

    decision = interrupt(build_approval_interrupt_payload(state, actionable_approvals, pending_write_actions))

    approved = False
    decision_reason = ""
    approval_id = ""
    if isinstance(decision, bool):
        approved = decision
    elif isinstance(decision, dict):
        approved = bool(decision.get("approved"))
        decision_reason = str(decision.get("reason", ""))
        approval_id = str(decision.get("approval_id", ""))

    if not approval_id and len(pending_approvals) == 1:
        approval_id = pending_approvals[0]["approval_id"]

    matched_approval: ApprovalState | None = None
    updated_approvals = []
    for approval in state.get("approvals", []):
        updated_approval = dict(approval)
        if approval["approval_id"] == approval_id and approval["status"] == ApprovalDecision.PENDING.value:
            updated_approval["status"] = ApprovalDecision.APPROVED.value if approved else ApprovalDecision.DENIED.value
            if decision_reason:
                updated_approval["decision_reason"] = decision_reason
            matched_approval = updated_approval
        updated_approvals.append(updated_approval)

    if matched_approval is None:
        return Command(
            update={
                "approvals": updated_approvals,
                "status": CaseStatus.WAITING_FOR_APPROVAL.value,
                "current_stage": RuntimeStage.APPROVAL_WAIT.value,
                "operator_notes": [
                    *state.get("operator_notes", []),
                    f"Approval response could not be matched to a pending approval ({approval_id or 'missing approval id'}).",
                ],
            },
            goto="await_approval",
        )

    remaining_pending = [
        approval
        for approval in updated_approvals
        if approval["status"] == ApprovalDecision.PENDING.value
    ]

    if approved:
        requester_updates = list(state.get("requester_updates", []))
        requester_updates.append(f"Approval received for {matched_approval['approval_type']}.")
        update = {
            "approvals": updated_approvals,
            "requester_updates": requester_updates,
            "operator_notes": [
                *state.get("operator_notes", []),
                f"Approval {matched_approval['approval_id']} approved.",
            ],
        }
        if remaining_pending:
            return Command(
                update={
                    **update,
                    "status": CaseStatus.WAITING_FOR_APPROVAL.value,
                    "current_stage": RuntimeStage.APPROVAL_WAIT.value,
                },
                goto="await_approval",
            )
        return Command(
            update={
                **update,
                "pending_actions": _unlock_approved_actions(state, updated_approvals),
                "status": CaseStatus.IN_PROGRESS.value,
                "current_stage": RuntimeStage.EXECUTION.value,
            },
            goto="execute_actions",
        )

    return Command(
        update={
            "approvals": updated_approvals,
            "status": CaseStatus.CANCELLED.value,
            "current_stage": RuntimeStage.CLOSURE.value,
            "action_results": _build_cancelled_results(state, matched_approval, terminal_error_code="approval_denied"),
            "requester_updates": [
                *state.get("requester_updates", []),
                "A required approval was denied. The request will not be executed automatically.",
            ],
            "operator_notes": [
                *state.get("operator_notes", []),
                f"Approval {matched_approval['approval_id']} was denied. Case cancelled pending manual follow-up.",
            ],
        },
        goto="close_case",
    )


def _build_approval_states(state: CaseState, action: ActionSpec, *, approval_timeout_hours: int) -> list[ApprovalState]:
    approval_mode = action["approval_mode"]
    target = action.get("target_resource") or action["action_type"]
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=approval_timeout_hours)).isoformat()
    if approval_mode == ApprovalMode.SECURITY.value:
        manager_approval_id = f"approval-{state['case_id']}-{action['action_id'][:8]}-manager"
        security_approval_id = f"approval-{state['case_id']}-{action['action_id'][:8]}-security"
        return [
            {
                "approval_id": manager_approval_id,
                "approval_type": f"{action['action_type']}:manager_precheck",
                "approval_mode": ApprovalMode.MANAGER.value,
                "sequence_no": 1,
                "status": ApprovalDecision.PENDING.value,
                "requested_from": _approval_actor(ApprovalMode.MANAGER.value),
                "prerequisite_approval_ids": [],
                "requested_action_ids": [action["action_id"]],
                "summary": f"Manager approval required before security review for {target}.",
                "expires_at": expires_at,
            },
            {
                "approval_id": security_approval_id,
                "approval_type": f"{action['action_type']}:security_review",
                "approval_mode": approval_mode,
                "sequence_no": 2,
                "status": ApprovalDecision.PENDING.value,
                "requested_from": _approval_actor(approval_mode),
                "prerequisite_approval_ids": [manager_approval_id],
                "requested_action_ids": [action["action_id"]],
                "summary": f"Security approval required for {target}.",
                "expires_at": expires_at,
            },
        ]

    return [
        {
            "approval_id": f"approval-{state['case_id']}-{action['action_id'][:8]}",
            "approval_type": f"{action['action_type']}:{approval_mode}",
            "approval_mode": approval_mode,
            "sequence_no": 1,
            "status": ApprovalDecision.PENDING.value,
            "requested_from": _approval_actor(approval_mode),
            "prerequisite_approval_ids": [],
            "requested_action_ids": [action["action_id"]],
            "summary": f"Approve {action['action_type']} for {target}.",
            "expires_at": expires_at,
        }
    ]


def _build_cancelled_results(state: CaseState, terminal_approval: ApprovalState, *, terminal_error_code: str) -> list[ActionResult]:
    terminal_action_ids = set(terminal_approval.get("requested_action_ids", []))
    results_by_id = {
        result["action_id"]: result
        for result in state.get("action_results", [])
        if isinstance(result, dict) and result.get("action_id")
    }

    for action in state.get("pending_actions", []):
        if action["action_id"] in results_by_id:
            continue
        if action["action_id"] in terminal_action_ids:
            summary = (
                f"Action '{action['action_type']}' was not executed because approval "
                f"'{terminal_approval['approval_id']}' was not completed."
            )
            error_code = terminal_error_code
        else:
            summary = f"Action '{action['action_type']}' was not executed because the case was cancelled."
            error_code = "case_cancelled"
        results_by_id[action["action_id"]] = {
            "action_id": action["action_id"],
            "status": "skipped",
            "summary": summary,
            "error_code": error_code,
        }

    return list(results_by_id.values())


def _unlock_approved_actions(state: CaseState, approvals: list[ApprovalState]) -> list[ActionSpec]:
    approved_action_ids = {
        action_id
        for approval in approvals
        if approval["status"] == ApprovalDecision.APPROVED.value
        for action_id in approval.get("requested_action_ids", [])
    }
    unlocked_actions = []
    for action in state.get("pending_actions", []):
        updated_action = dict(action)
        if action["action_id"] in approved_action_ids and updated_action.get("policy_decision") in {"approval_required", "escalate"}:
            updated_action["policy_decision"] = "auto_allow"
            updated_action["policy_reason"] = "Required approvals completed."
            updated_action["requires_human"] = False
        unlocked_actions.append(updated_action)
    return unlocked_actions


def _get_actionable_approvals(pending_approvals: list[ApprovalState], all_approvals: list[ApprovalState]) -> list[ApprovalState]:
    approvals_by_id = {approval["approval_id"]: approval for approval in all_approvals}
    actionable = []
    for approval in pending_approvals:
        prerequisites = approval.get("prerequisite_approval_ids", [])
        if all(approvals_by_id.get(approval_id, {}).get("status") == ApprovalDecision.APPROVED.value for approval_id in prerequisites):
            actionable.append(approval)
    return sorted(actionable, key=lambda approval: (approval.get("sequence_no", 0), approval["approval_id"]))


def _is_approval_expired(approval: ApprovalState) -> bool:
    expires_at = approval.get("expires_at")
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _approval_actor(mode: str) -> dict[str, str]:
    actor_map = {
        ApprovalMode.MANAGER.value: {
            "actor_id": "manager-placeholder",
            "actor_type": "manager",
            "email": "manager@example.local",
            "display_name": "Approving Manager",
        },
        ApprovalMode.OWNER.value: {
            "actor_id": "owner-placeholder",
            "actor_type": "manager",
            "email": "owner@example.local",
            "display_name": "Resource Owner",
        },
        ApprovalMode.SECURITY.value: {
            "actor_id": "security-placeholder",
            "actor_type": "operator",
            "email": "security@example.local",
            "display_name": "Security Reviewer",
        },
        ApprovalMode.OPERATOR.value: {
            "actor_id": "operator-placeholder",
            "actor_type": "operator",
            "email": "opsdesk@example.local",
            "display_name": "OpsDesk Operator",
        },
    }
    return actor_map.get(
        mode,
        {
            "actor_id": "approver-placeholder",
            "actor_type": "operator",
            "email": "opsdesk@example.local",
            "display_name": "Approver",
        },
    )
