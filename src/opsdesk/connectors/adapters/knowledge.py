from __future__ import annotations

from ...knowledge import KnowledgeStore, load_default_knowledge_store
from ..base import DomainToolRequest, DomainToolResponse


class MockKnowledgeAdapter:
    name = "knowledge"
    supported_actions = ("retrieve_policy_guidance",)

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self.store = store or load_default_knowledge_store()

    def describe(self):
        return {"name": self.name, "supported_actions": list(self.supported_actions)}

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        if action_type != "retrieve_policy_guidance":
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Unsupported knowledge action: {action_type}.",
                "raw_result": {},
                "retryable": False,
            }
        question = str(request["payload"].get("question", ""))
        citations = self.store.search(question, limit=2)
        if citations:
            answer = citations[0].get("snippet", "Policy guidance is available in the internal handbook.")
        else:
            answer = "No matching policy guidance was found. Please route to an operator."
        return {
            "ok": True,
            "external_ref": "policy-guidance",
            "summary": "Retrieved policy guidance for the request.",
            "raw_result": {
                "question": question,
                "answer": answer,
                "citations": citations,
            },
            "retryable": False,
        }
