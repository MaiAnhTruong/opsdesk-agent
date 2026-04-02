from __future__ import annotations

from ...domain.enums import CaseStatus, RuntimeStage
from ..state import CaseState


def close_case(state: CaseState) -> CaseState:
    final_status = state.get("status", CaseStatus.RESOLVED.value)
    if final_status == CaseStatus.NEW.value:
        final_status = CaseStatus.RESOLVED.value

    resolution_message = "Case closed."
    if final_status == CaseStatus.PARTIALLY_COMPLETED.value:
        resolution_message = "Case staged for follow-up because write connectors are not wired yet."
    elif final_status == CaseStatus.CANCELLED.value:
        resolution_message = "Case closed after approval denial."
    elif final_status == CaseStatus.RESOLVED.value:
        resolution_message = "Case resolved in scaffold mode."

    return {
        "status": final_status,
        "current_stage": RuntimeStage.CLOSURE.value,
        "requester_updates": [
            *state.get("requester_updates", []),
            resolution_message,
        ],
    }
