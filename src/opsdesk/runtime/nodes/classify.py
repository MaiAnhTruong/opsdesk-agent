from __future__ import annotations

from ...domain.enums import RuntimeStage, WorkflowType
from ..state import CaseState


def classify_intent(state: CaseState) -> CaseState:
    message = state.get("latest_user_message", "").lower()
    workflow = WorkflowType.ACCESS_REQUEST
    intent = WorkflowType.ACCESS_REQUEST.value

    if any(token in message for token in ("onboard", "new hire", "starter", "laptop setup")):
        workflow = WorkflowType.ONBOARDING
        intent = "employee_onboarding"
    elif any(token in message for token in ("vpn", "password", "mfa", "sso", "login", "signin")):
        workflow = WorkflowType.AUTH_ISSUE
        intent = "authentication_issue"
    elif any(token in message for token in ("policy", "work from home", "leave", "expense", "pto")):
        workflow = WorkflowType.POLICY_QA
        intent = "policy_question"

    return {
        "workflow_type": workflow.value,
        "intent": intent,
        "current_stage": RuntimeStage.CONTEXT_HYDRATION.value,
        "operator_notes": [
            *state.get("operator_notes", []),
            f"Intent classified as {intent}.",
        ],
    }
