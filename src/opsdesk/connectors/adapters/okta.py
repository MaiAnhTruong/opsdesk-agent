from __future__ import annotations

from uuid import uuid4

from ..base import DomainToolRequest, DomainToolResponse


class MockOktaAdapter:
    name = "okta"
    supported_actions = (
        "lookup_current_access",
        "verify_identity_context",
        "issue_password_reset",
        "grant_application_access",
        "create_onboarding_bundle",
    )

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        email = str(request["payload"].get("email", request["payload"].get("requested_by", "unknown@example.local")))
        if action_type == "lookup_current_access":
            return {
                "ok": True,
                "external_ref": email,
                "summary": f"Fetched current access for {email}.",
                "raw_result": {"groups": ["employees", "baseline-apps"], "email": email},
                "retryable": False,
            }
        if action_type == "verify_identity_context":
            return {
                "ok": True,
                "external_ref": email,
                "summary": f"Verified identity context for {email}.",
                "raw_result": {"verified": True, "email": email},
                "retryable": False,
            }
        if action_type == "issue_password_reset":
            return {
                "ok": True,
                "external_ref": uuid4().hex,
                "summary": f"Issued password reset for {email}.",
                "raw_result": {"email": email, "reset_issued": True},
                "retryable": False,
            }
        if action_type == "grant_application_access":
            application = str(request["payload"].get("application", "requested-application"))
            return {
                "ok": True,
                "external_ref": uuid4().hex,
                "summary": f"Granted {application} access for {email}.",
                "raw_result": {"email": email, "application": application, "granted": True},
                "retryable": False,
            }
        if action_type == "create_onboarding_bundle":
            return {
                "ok": True,
                "external_ref": uuid4().hex,
                "summary": "Created onboarding identity bundle in scaffold mode.",
                "raw_result": {"bundle_created": True},
                "retryable": False,
            }
        return {
            "ok": False,
            "external_ref": None,
            "summary": f"Unsupported Okta action: {action_type}.",
            "raw_result": {},
            "retryable": False,
        }
