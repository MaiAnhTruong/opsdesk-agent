from __future__ import annotations

from typing import Any

from .state import ActionSpec, ApprovalState, CaseState


def build_approval_interrupt_payload(
    state: CaseState,
    approvals: list[ApprovalState],
    actions: list[ActionSpec],
) -> dict[str, Any]:
    actions_by_id = {action["action_id"]: action for action in actions}
    return {
        "type": "approval_request",
        "case_id": state["case_id"],
        "title": state["title"],
        "workflow_type": state["workflow_type"],
        "requester": state["requester"]["email"],
        "approvals": [
            {
                "approval_id": approval["approval_id"],
                "approval_type": approval["approval_type"],
                "approval_mode": approval["approval_mode"],
                "sequence_no": approval["sequence_no"],
                "summary": approval["summary"],
                "expires_at": approval.get("expires_at"),
                "requested_from": approval["requested_from"],
                "actions": [
                    {
                        "action_id": action["action_id"],
                        "action_type": action["action_type"],
                        "target_system": action["target_system"],
                        "target_resource": action["target_resource"],
                        "approval_mode": action["approval_mode"],
                        "risk_level": action["risk_level"],
                    }
                    for action_id in approval.get("requested_action_ids", [])
                    if (action := actions_by_id.get(action_id)) is not None
                ],
            }
            for approval in approvals
        ],
    }
