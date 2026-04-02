from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..domain.enums import ApprovalMode

PolicyDecisionType = Literal["auto_allow", "approval_required", "deny", "escalate"]


@dataclass(frozen=True)
class PolicyRule:
    action_type: str
    decision: PolicyDecisionType
    approval_mode: ApprovalMode
    reason: str


DEFAULT_POLICY_RULES: tuple[PolicyRule, ...] = (
    PolicyRule(
        action_type="lookup_current_access",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Read-only entitlement lookup is allowed during case processing.",
    ),
    PolicyRule(
        action_type="check_license_capacity",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Read-only license lookup is allowed during case processing.",
    ),
    PolicyRule(
        action_type="load_onboarding_bundle",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Read-only role bundle lookup is allowed during case processing.",
    ),
    PolicyRule(
        action_type="check_device_inventory",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Read-only inventory lookup is allowed during case processing.",
    ),
    PolicyRule(
        action_type="verify_identity_context",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Identity verification is required and safe as a read-only action.",
    ),
    PolicyRule(
        action_type="retrieve_policy_guidance",
        decision="auto_allow",
        approval_mode=ApprovalMode.AUTO,
        reason="Policy retrieval is read-only and auto-allowed.",
    ),
    PolicyRule(
        action_type="grant_application_access",
        decision="approval_required",
        approval_mode=ApprovalMode.MANAGER,
        reason="Application access grants require manager approval by default.",
    ),
    PolicyRule(
        action_type="create_onboarding_bundle",
        decision="approval_required",
        approval_mode=ApprovalMode.MANAGER,
        reason="Onboarding bundle writes require manager approval by default.",
    ),
)
