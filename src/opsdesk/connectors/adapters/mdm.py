from __future__ import annotations

from ..base import DomainToolRequest, DomainToolResponse


class MockMdmAdapter:
    name = "mdm"
    supported_actions = ("check_device_inventory",)

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        if action_type != "check_device_inventory":
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported MDM action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }
        return {
            "ok": True,
            "external_ref": "device-inventory",
            "summary": "Confirmed that a starter device is available.",
            "raw_result": {"available": True, "device_type": "MacBook Pro 14"},
            "retryable": False,
        }
