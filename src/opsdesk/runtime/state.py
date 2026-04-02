from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict
from uuid import uuid4

from ..domain.enums import CasePriority, CaseStatus, RuntimeStage, WorkflowType


class ActorRef(TypedDict):
    actor_id: str
    actor_type: Literal["employee", "manager", "operator", "system"]
    email: str
    display_name: str


class PolicyCitation(TypedDict):
    doc_id: str
    chunk_id: str
    title: str
    url: str
    snippet: str


class PlanStep(TypedDict):
    step_id: str
    title: str
    action_type: str
    target_system: str
    mode: Literal["read", "write"]
    rationale: str


class ActionSpec(TypedDict):
    action_id: str
    action_type: str
    target_system: str
    target_resource: str
    mode: Literal["read", "write"]
    risk_level: Literal["low", "medium", "high", "critical"]
    approval_mode: Literal["auto", "manager", "owner", "operator", "security", "deny"]
    requires_human: bool
    idempotency_key: str
    payload: dict[str, Any]
    policy_decision: NotRequired[Literal["auto_allow", "approval_required", "deny", "escalate"]]
    policy_reason: NotRequired[str]


class ActionResult(TypedDict):
    action_id: str
    status: Literal["pending", "completed", "failed", "skipped"]
    summary: str
    external_ref: NotRequired[str]
    error_code: NotRequired[str]
    details: NotRequired[dict[str, Any]]


class ApprovalState(TypedDict):
    approval_id: str
    approval_type: str
    approval_mode: Literal["auto", "manager", "owner", "operator", "security", "deny"]
    sequence_no: int
    status: Literal["pending", "approved", "denied", "expired"]
    requested_from: ActorRef
    prerequisite_approval_ids: list[str]
    requested_action_ids: list[str]
    summary: str
    expires_at: str | None
    decision_reason: NotRequired[str]


class SlaState(TypedDict):
    first_response_due_at: str | None
    resolution_due_at: str | None
    breach_risk: Literal["low", "medium", "high"]
    last_escalated_at: str | None


class CaseState(TypedDict, total=False):
    case_id: str
    tenant_id: str
    thread_id: str
    channel: Literal["slack", "portal", "email", "api", "scheduler"]
    workflow_type: Literal["access_request", "onboarding", "auth_issue", "policy_qa", "unknown"]
    intent: str
    priority: Literal["low", "normal", "high", "urgent"]
    status: str
    current_stage: str
    title: str
    requester: ActorRef
    subject_employee: ActorRef
    latest_user_message: str
    normalized_request: dict[str, Any]
    extracted_entities: dict[str, Any]
    missing_fields: list[str]
    policy_citations: list[PolicyCitation]
    knowledge_citations: list[PolicyCitation]
    plan_steps: list[PlanStep]
    pending_actions: list[ActionSpec]
    action_results: list[ActionResult]
    approvals: list[ApprovalState]
    requester_updates: list[str]
    operator_notes: list[str]
    sla: SlaState
    last_error: str


def build_initial_state(
    *,
    tenant_id: str,
    requester_email: str,
    requester_name: str | None,
    latest_user_message: str,
    channel: Literal["slack", "portal", "email", "api", "scheduler"] = "api",
    title: str | None = None,
    priority: Literal["low", "normal", "high", "urgent"] = CasePriority.NORMAL.value,
    case_id: str | None = None,
) -> CaseState:
    generated_case_id = case_id or uuid4().hex
    display_name = requester_name or requester_email.split("@", maxsplit=1)[0]
    now = datetime.now(timezone.utc).isoformat()
    return {
        "case_id": generated_case_id,
        "tenant_id": tenant_id,
        "thread_id": generated_case_id,
        "channel": channel,
        "workflow_type": WorkflowType.UNKNOWN.value,
        "intent": WorkflowType.UNKNOWN.value,
        "priority": priority,
        "status": CaseStatus.NEW.value,
        "current_stage": RuntimeStage.INTAKE.value,
        "title": title or latest_user_message[:120] or "Employee request",
        "requester": {
            "actor_id": requester_email,
            "actor_type": "employee",
            "email": requester_email,
            "display_name": display_name,
        },
        "latest_user_message": latest_user_message,
        "normalized_request": {
            "channel": channel,
            "received_at": now,
        },
        "extracted_entities": {},
        "missing_fields": [],
        "policy_citations": [],
        "knowledge_citations": [],
        "plan_steps": [],
        "pending_actions": [],
        "action_results": [],
        "approvals": [],
        "requester_updates": [f"Case created at {now}"],
        "operator_notes": [],
        "sla": {
            "first_response_due_at": None,
            "resolution_due_at": None,
            "breach_risk": "low",
            "last_escalated_at": None,
        },
    }
