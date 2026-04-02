from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...config import Settings
from ...domain.services import CaseService
from ...runtime import CaseGraphDispatcher
from ...runtime.state import build_initial_state
from ...schemas import PortalCaseCreateRequest, PortalCaseStatusResponse
from ..deps import get_case_service, get_dispatcher, get_settings
from ..serialization import to_json_safe

router = APIRouter(prefix="/portal", tags=["portal"])


@router.post("/cases", response_model=PortalCaseStatusResponse)
def submit_portal_case(
    payload: PortalCaseCreateRequest,
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
    settings: Settings = Depends(get_settings),
) -> PortalCaseStatusResponse:
    initial_state = build_initial_state(
        tenant_id=settings.tenant_id,
        requester_email=payload.requester_email,
        requester_name=payload.requester_name,
        latest_user_message=payload.message,
        channel="portal",
        title=payload.title,
        priority=payload.priority,
        case_id=payload.case_id,
    )
    result = dispatcher.run_case(initial_state)
    return PortalCaseStatusResponse(
        case_id=str(result.get("case_id")),
        status=str(result.get("status", "")),
        workflow_type=str(result.get("workflow_type", "")),
        current_stage=str(result.get("current_stage", "")),
        requester_updates=[str(item) for item in result.get("requester_updates", [])],
    )


@router.get("/cases/{case_id}/status", response_model=PortalCaseStatusResponse)
def get_portal_case_status(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
) -> PortalCaseStatusResponse:
    detail = case_service.get_case_projection(case_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    payload = to_json_safe(detail)
    requester_updates = [str(item) for item in payload.get("requester_updates", [])]
    return PortalCaseStatusResponse(
        case_id=case_id,
        status=str(payload.get("status", "")),
        workflow_type=str(payload.get("workflow_type", "")),
        current_stage=str(payload.get("current_stage", "")),
        requester_updates=requester_updates,
    )
