from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import ApprovalMode
from .matrix import DEFAULT_POLICY_RULES, PolicyDecisionType, PolicyRule


@dataclass(frozen=True)
class PolicyDecision:
    decision: PolicyDecisionType
    approval_mode: ApprovalMode
    reason: str


@dataclass
class PolicyEngine:
    rules: tuple[PolicyRule, ...] = DEFAULT_POLICY_RULES

    def evaluate_action(self, state: dict[str, object], action: dict[str, object]) -> PolicyDecision:
        requester_email = str(state.get("requester", {}).get("email", ""))
        action_type = str(action.get("action_type", ""))
        mode = str(action.get("mode", "read"))
        payload = action.get("payload", {})

        if action_type == "grant_application_access":
            application = str(payload.get("application", action.get("target_resource", ""))).lower()
            approval_hint = str(payload.get("approval_hint", "")).lower()
            if approval_hint == ApprovalMode.SECURITY.value or any(token in application for token in ("prod", "production", "admin")):
                return PolicyDecision(
                    decision="escalate",
                    approval_mode=ApprovalMode.SECURITY,
                    reason="Privileged or production access requires security review.",
                )
            if approval_hint == ApprovalMode.OWNER.value or any(token in application for token in ("analytics", "finance")):
                return PolicyDecision(
                    decision="approval_required",
                    approval_mode=ApprovalMode.OWNER,
                    reason="Sensitive data access requires resource owner approval.",
                )
            return PolicyDecision(
                decision="approval_required",
                approval_mode=ApprovalMode.MANAGER,
                reason="Application access grants require manager approval by default.",
            )

        for rule in self.rules:
            if rule.action_type == action_type:
                return PolicyDecision(
                    decision=rule.decision,
                    approval_mode=rule.approval_mode,
                    reason=rule.reason,
                )

        if mode == "read":
            return PolicyDecision(
                decision="auto_allow",
                approval_mode=ApprovalMode.AUTO,
                reason="Read-only actions are auto-allowed by default.",
            )

        if action_type == "issue_password_reset":
            target_email = str(payload.get("email", action.get("target_resource", "")))
            if target_email and target_email == requester_email:
                return PolicyDecision(
                    decision="auto_allow",
                    approval_mode=ApprovalMode.AUTO,
                    reason="Self-service password reset is auto-allowed for the verified requester.",
                )
            return PolicyDecision(
                decision="approval_required",
                approval_mode=ApprovalMode.OPERATOR,
                reason="Password reset for another subject requires operator approval.",
            )

        if action_type in {"grant_admin_access", "grant_production_access"}:
            return PolicyDecision(
                decision="escalate",
                approval_mode=ApprovalMode.SECURITY,
                reason="Privileged access requires security review.",
            )

        if mode == "write":
            return PolicyDecision(
                decision="approval_required",
                approval_mode=ApprovalMode.OPERATOR,
                reason="Unknown write action requires operator approval.",
            )

        return PolicyDecision(
            decision="deny",
            approval_mode=ApprovalMode.DENY,
            reason="Action denied by default policy.",
        )


def build_policy_engine() -> PolicyEngine:
    return PolicyEngine()
