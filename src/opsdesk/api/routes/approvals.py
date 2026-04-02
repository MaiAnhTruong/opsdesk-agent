from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...domain.services import ApprovalService
from ...runtime import CaseGraphDispatcher
from ...schemas import ApprovalDecisionRequest, ApprovalDecisionResponse
from ..deps import get_approval_service, get_dispatcher
from ..serialization import to_json_safe

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse)
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
) -> ApprovalDecisionResponse:
    existing = approval_service.get_approval(approval_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}")
    if existing["decision"] != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already decided: {approval_id}")

    try:
        approval = approval_service.decide(
            approval_id,
            approved=payload.approved,
            actor_id=payload.actor_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    resume_payload = {
        "approval_id": approval_id,
        "approved": payload.approved,
        "reason": payload.reason or "",
    }
    result = dispatcher.resume_case(approval["case_id"], resume_payload)
    return ApprovalDecisionResponse(
        approval_id=approval_id,
        case_id=approval["case_id"],
        decision=approval["decision"],
        resumed=True,
        result=to_json_safe(result),
    )
