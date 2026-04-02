from __future__ import annotations

from datetime import datetime, timezone

from ...domain.enums import CaseStatus, RuntimeStage
from ..state import CaseState


def ingest_case(state: CaseState) -> CaseState:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "status": CaseStatus.TRIAGED.value,
        "current_stage": RuntimeStage.CLASSIFICATION.value,
        "normalized_request": {
            **state.get("normalized_request", {}),
            "ingested_at": now,
            "source_channel": state["channel"],
        },
        "requester_updates": [
            *state.get("requester_updates", []),
            "Request ingested and queued for triage.",
        ],
    }
