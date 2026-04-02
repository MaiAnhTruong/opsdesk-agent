from __future__ import annotations

from ..base import DomainToolRequest, DomainToolResponse


class MockHrisAdapter:
    name = "hris"
    supported_actions = ("load_onboarding_bundle",)

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        if action_type != "load_onboarding_bundle":
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported HRIS action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }
        return {
            "ok": True,
            "external_ref": "bundle-product-designer",
            "summary": "Loaded onboarding bundle for the requested role.",
            "raw_result": {"bundle_name": "Product Designer", "apps": ["Slack", "Notion", "Jira"]},
            "retryable": False,
        }
