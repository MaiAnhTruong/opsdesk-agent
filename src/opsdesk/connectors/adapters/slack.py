from __future__ import annotations

from uuid import uuid4

from ..base import DomainToolRequest, DomainToolResponse


class MockSlackAdapter:
    name = "slack"
    supported_actions = ("post_requester_update",)

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        if action_type != "post_requester_update":
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported Slack action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }

        message = str(request["payload"].get("message", "")).strip()
        channel = str(request["payload"].get("channel", "employee-updates"))
        recipient = str(request["payload"].get("recipient", request["actor_id"]))
        return {
            "ok": True,
            "external_ref": uuid4().hex,
            "summary": f"Posted requester update to Slack channel {channel}.",
            "raw_result": {
                "channel": channel,
                "recipient": recipient,
                "message": message,
            },
            "retryable": False,
        }
