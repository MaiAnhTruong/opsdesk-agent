from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ...domain.enums import RuntimeStage
from ..state import ActionSpec, CaseState, PlanStep


@dataclass(frozen=True)
class AccessRequestProfile:
    application: str
    approval_mode: str
    risk_level: str
    match_terms: tuple[str, ...]


ACCESS_REQUEST_PROFILES: tuple[AccessRequestProfile, ...] = (
    AccessRequestProfile(
        application="production admin",
        approval_mode="security",
        risk_level="critical",
        match_terms=("production admin", "prod admin", "admin access", "production access", "prod access"),
    ),
    AccessRequestProfile(
        application="analytics dashboard",
        approval_mode="owner",
        risk_level="high",
        match_terms=("analytics dashboard", "analytics access", "dashboard analytics"),
    ),
    AccessRequestProfile(
        application="finance folder",
        approval_mode="owner",
        risk_level="high",
        match_terms=("finance folder", "finance drive", "finance access"),
    ),
    AccessRequestProfile(
        application="github enterprise",
        approval_mode="manager",
        risk_level="high",
        match_terms=("github enterprise", "github"),
    ),
    AccessRequestProfile(
        application="figma",
        approval_mode="manager",
        risk_level="high",
        match_terms=("figma",),
    ),
    AccessRequestProfile(
        application="jira",
        approval_mode="manager",
        risk_level="high",
        match_terms=("jira",),
    ),
    AccessRequestProfile(
        application="notion",
        approval_mode="manager",
        risk_level="medium",
        match_terms=("notion",),
    ),
    AccessRequestProfile(
        application="slack",
        approval_mode="manager",
        risk_level="medium",
        match_terms=("slack",),
    ),
    AccessRequestProfile(
        application="google workspace",
        approval_mode="manager",
        risk_level="medium",
        match_terms=("google workspace",),
    ),
    AccessRequestProfile(
        application="vpn",
        approval_mode="manager",
        risk_level="medium",
        match_terms=("vpn",),
    ),
)


def _make_action(
    *,
    action_type: str,
    target_system: str,
    target_resource: str,
    mode: str,
    risk_level: str,
    approval_mode: str,
    payload: dict[str, object],
) -> ActionSpec:
    action_id = uuid4().hex
    return {
        "action_id": action_id,
        "action_type": action_type,
        "target_system": target_system,
        "target_resource": target_resource,
        "mode": mode,
        "risk_level": risk_level,
        "approval_mode": approval_mode,
        "requires_human": approval_mode not in {"auto", "deny"},
        "idempotency_key": f"{action_type}:{action_id}",
        "payload": payload,
    }


def _make_step(title: str, action_type: str, target_system: str, mode: str, rationale: str) -> PlanStep:
    return {
        "step_id": uuid4().hex,
        "title": title,
        "action_type": action_type,
        "target_system": target_system,
        "mode": mode,
        "rationale": rationale,
    }


def _infer_access_request_profile(request_text: str) -> AccessRequestProfile:
    lowered = request_text.lower()
    for profile in ACCESS_REQUEST_PROFILES:
        if any(term in lowered for term in profile.match_terms):
            return profile
    return AccessRequestProfile(
        application="requested-application",
        approval_mode="manager",
        risk_level="high",
        match_terms=(),
    )


def build_action_plan(state: CaseState) -> CaseState:
    workflow = state["workflow_type"]
    access_profile = _infer_access_request_profile(state.get("latest_user_message", ""))
    plan_steps: list[PlanStep] = []
    actions: list[ActionSpec] = []
    extracted_entities = dict(state.get("extracted_entities", {}))

    if workflow == "access_request":
        plan_steps.extend(
            [
                _make_step("Lookup current access", "lookup_current_access", "identity", "read", "Understand the current entitlement state."),
                _make_step("Check app license capacity", "check_license_capacity", "license", "read", "Ensure the requested tool can be granted."),
                _make_step("Grant requested access", "grant_application_access", "application", "write", "Provision the requested access after approval."),
            ]
        )
        actions.extend(
            [
                _make_action(
                    action_type="lookup_current_access",
                    target_system="okta",
                    target_resource=state["requester"]["email"],
                    mode="read",
                    risk_level="low",
                    approval_mode="auto",
                    payload={"email": state["requester"]["email"]},
                ),
                _make_action(
                    action_type="check_license_capacity",
                    target_system="license",
                    target_resource=access_profile.application,
                    mode="read",
                    risk_level="low",
                    approval_mode="auto",
                    payload={"requested_by": state["requester"]["email"], "application": access_profile.application},
                ),
                _make_action(
                    action_type="grant_application_access",
                    target_system="okta",
                    target_resource=access_profile.application,
                    mode="write",
                    risk_level=access_profile.risk_level,
                    approval_mode=access_profile.approval_mode,
                    payload={
                        "requested_by": state["requester"]["email"],
                        "application": access_profile.application,
                        "approval_hint": access_profile.approval_mode,
                    },
                ),
            ]
        )
        extracted_entities.update(
            {
                "requested_application": access_profile.application,
                "requested_access_approval_mode": access_profile.approval_mode,
                "requested_access_risk_level": access_profile.risk_level,
            }
        )
    elif workflow == "onboarding":
        plan_steps.extend(
            [
                _make_step("Load onboarding bundle", "load_onboarding_bundle", "hris", "read", "Identify the standard bundle for the new starter."),
                _make_step("Check device readiness", "check_device_inventory", "mdm", "read", "Confirm device availability."),
                _make_step("Create onboarding bundle", "create_onboarding_bundle", "identity", "write", "Stage the core starter configuration."),
            ]
        )
        actions.extend(
            [
                _make_action(
                    action_type="load_onboarding_bundle",
                    target_system="hris",
                    target_resource="role-template",
                    mode="read",
                    risk_level="low",
                    approval_mode="auto",
                    payload={"request_text": state["latest_user_message"]},
                ),
                _make_action(
                    action_type="check_device_inventory",
                    target_system="mdm",
                    target_resource="starter-device",
                    mode="read",
                    risk_level="low",
                    approval_mode="auto",
                    payload={"request_text": state["latest_user_message"]},
                ),
                _make_action(
                    action_type="create_onboarding_bundle",
                    target_system="okta",
                    target_resource="new-employee",
                    mode="write",
                    risk_level="high",
                    approval_mode="manager",
                    payload={"request_text": state["latest_user_message"]},
                ),
            ]
        )
    elif workflow == "auth_issue":
        plan_steps.extend(
            [
                _make_step("Verify identity context", "verify_identity_context", "identity", "read", "Confirm the requester identity before remediation."),
                _make_step("Issue self-service remediation", "issue_password_reset", "identity", "write", "Provide the lowest-risk remediation path first."),
            ]
        )
        actions.extend(
            [
                _make_action(
                    action_type="verify_identity_context",
                    target_system="okta",
                    target_resource=state["requester"]["email"],
                    mode="read",
                    risk_level="low",
                    approval_mode="auto",
                    payload={"email": state["requester"]["email"]},
                ),
                _make_action(
                    action_type="issue_password_reset",
                    target_system="okta",
                    target_resource=state["requester"]["email"],
                    mode="write",
                    risk_level="medium",
                    approval_mode="auto",
                    payload={"email": state["requester"]["email"]},
                ),
            ]
        )
    else:
        plan_steps.append(
            _make_step("Retrieve policy guidance", "retrieve_policy_guidance", "knowledge", "read", "Answer the request with cited policy guidance.")
        )
        actions.append(
            _make_action(
                action_type="retrieve_policy_guidance",
                target_system="knowledge",
                target_resource="policy",
                mode="read",
                risk_level="low",
                approval_mode="auto",
                payload={"question": state["latest_user_message"]},
            )
        )

    return {
        "current_stage": RuntimeStage.PERMISSION_EVALUATION.value,
        "plan_steps": plan_steps,
        "pending_actions": actions,
        "extracted_entities": extracted_entities,
        "requester_updates": [
            *state.get("requester_updates", []),
            f"Action plan created with {len(plan_steps)} steps.",
        ],
    }
