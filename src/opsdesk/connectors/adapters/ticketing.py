from __future__ import annotations

from uuid import uuid4

from ..base import DomainToolRequest, DomainToolResponse


class MockTicketingAdapter:
    name = "ticketing"
    supported_actions = ("upsert_ticket", "sync_ticket_status", "assign_ticket", "append_ticket_note")

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        payload = request["payload"]
        case_id = str(payload.get("case_id", request["case_id"]))
        existing_ticket_id = payload.get("external_ticket_id")
        ticket_id = str(existing_ticket_id or f"OPS-{uuid4().hex[:8].upper()}")

        if action_type not in {"upsert_ticket", "sync_ticket_status", "assign_ticket", "append_ticket_note"}:
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported ticketing action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }

        if action_type == "assign_ticket":
            return {
                "ok": True,
                "external_ref": ticket_id,
                "summary": f"Ticket {ticket_id} assignment synced for case {case_id}.",
                "raw_result": {
                    "ticket_id": ticket_id,
                    "case_id": case_id,
                    "assigned_team": payload.get("assigned_team"),
                    "assigned_operator_id": payload.get("assigned_operator_id"),
                    "status": payload.get("status"),
                },
                "retryable": False,
            }

        if action_type == "append_ticket_note":
            return {
                "ok": True,
                "external_ref": ticket_id,
                "summary": f"Ticket {ticket_id} note appended for case {case_id}.",
                "raw_result": {
                    "ticket_id": ticket_id,
                    "case_id": case_id,
                    "visibility": payload.get("visibility"),
                    "body": payload.get("body"),
                },
                "retryable": False,
            }

        return {
            "ok": True,
            "external_ref": ticket_id,
            "summary": f"Ticket {ticket_id} synced for case {case_id}.",
            "raw_result": {
                "ticket_id": ticket_id,
                "case_id": case_id,
                "status": payload.get("status"),
                "summary": payload.get("summary"),
                "workflow_type": payload.get("workflow_type"),
            },
            "retryable": False,
        }
