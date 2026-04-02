from __future__ import annotations

from ...domain.enums import RuntimeStage
from ..state import CaseState, PolicyCitation


def hydrate_case_context(state: CaseState) -> CaseState:
    citations: list[PolicyCitation] = []
    return {
        "current_stage": RuntimeStage.PLANNING.value,
        "knowledge_citations": citations,
        "extracted_entities": {
            **state.get("extracted_entities", {}),
            "requester_email": state["requester"]["email"],
        },
    }
