from __future__ import annotations

from fastapi import APIRouter, Depends

from ...config import Settings
from ...runtime import CaseGraphDispatcher
from ...runtime.state import build_initial_state
from ...schemas import CaseRunResponse, SlackEventRequest
from ..deps import get_dispatcher, get_settings
from ..serialization import to_json_safe

router = APIRouter(prefix="/events/slack", tags=["slack"])


@router.post("", response_model=CaseRunResponse)
def receive_slack_event(
    payload: SlackEventRequest,
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
    settings: Settings = Depends(get_settings),
) -> CaseRunResponse:
    initial_state = build_initial_state(
        tenant_id=settings.tenant_id,
        requester_email=payload.user_email,
        requester_name=payload.user_name,
        latest_user_message=payload.text,
        channel="slack",
        title=payload.channel_name or "Slack employee request",
        case_id=payload.case_id,
    )
    initial_state["normalized_request"]["channel_name"] = payload.channel_name or "employee-updates"
    result = dispatcher.run_case(initial_state)
    payload = to_json_safe(result)
    return CaseRunResponse(
        case_id=str(payload.get("case_id", "")),
        thread_id=str(payload.get("thread_id", payload.get("case_id", ""))),
        status=str(payload.get("status", "")),
        workflow_type=str(payload.get("workflow_type", "")),
        current_stage=str(payload.get("current_stage", "")),
        result=payload,
    )
