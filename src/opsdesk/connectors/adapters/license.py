from __future__ import annotations

from ..base import DomainToolRequest, DomainToolResponse


class MockLicenseAdapter:
    name = "license"
    supported_actions = ("check_license_capacity",)

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        if action_type != "check_license_capacity":
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported license action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }
        return {
            "ok": True,
            "external_ref": "license-capacity",
            "summary": "Confirmed license capacity is available.",
            "raw_result": {"available": True, "remaining": 12},
            "retryable": False,
        }
