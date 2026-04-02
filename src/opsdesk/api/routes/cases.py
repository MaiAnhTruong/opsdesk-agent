from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ...config import Settings
from ...domain.services import ArtifactService, CaseService, NotificationService, TicketSyncService
from ...runtime import CaseGraphDispatcher
from ...runtime.state import build_initial_state
from ...schemas import ApprovalListResponse, ApprovalResponse, AuditLogListResponse, AuditLogResponse, CaseArtifactCompleteRequest, CaseArtifactCreateRequest, CaseArtifactListResponse, CaseArtifactResponse, CaseAssignmentRequest, CaseAssignmentResponse, CaseCommentListResponse, CaseCommentRequest, CaseCommentResponse, CaseCreateRequest, CaseDetailResponse, CaseListResponse, CaseResumeRequest, CaseRetryRequest, CaseRunResponse, CaseStateResponse, CaseTimelineResponse
from ...schemas import CaseEventResponse
from ..serialization import to_json_safe
from ..deps import get_artifact_service, get_case_service, get_dispatcher, get_notification_service, get_settings, get_ticket_sync_service

router = APIRouter(prefix="/cases", tags=["cases"])


def _to_run_response(result: dict[str, object]) -> CaseRunResponse:
    payload = to_json_safe(result)
    return CaseRunResponse(
        case_id=str(payload.get("case_id", "")),
        thread_id=str(payload.get("thread_id", payload.get("case_id", ""))),
        status=str(payload.get("status", "")),
        workflow_type=str(payload.get("workflow_type", "")),
        current_stage=str(payload.get("current_stage", "")),
        result=payload,
    )


@router.post("", response_model=CaseRunResponse)
def create_case(
    payload: CaseCreateRequest,
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
    settings: Settings = Depends(get_settings),
) -> CaseRunResponse:
    initial_state = build_initial_state(
        tenant_id=settings.tenant_id,
        requester_email=payload.requester_email,
        requester_name=payload.requester_name,
        latest_user_message=payload.message,
        channel=payload.channel,
        title=payload.title,
        priority=payload.priority,
        case_id=payload.case_id,
    )
    result = dispatcher.run_case(initial_state)
    return _to_run_response(result)


@router.post("/{case_id}/resume", response_model=CaseRunResponse)
def resume_case(
    case_id: str,
    payload: CaseResumeRequest,
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
) -> CaseRunResponse:
    result = dispatcher.resume_case(case_id, payload.resume_value)
    return _to_run_response(result)


@router.post("/{case_id}/retry", response_model=CaseRunResponse)
def retry_case(
    case_id: str,
    payload: CaseRetryRequest,
    dispatcher: CaseGraphDispatcher = Depends(get_dispatcher),
) -> CaseRunResponse:
    try:
        result = dispatcher.retry_case(
            case_id,
            actor_id=payload.actor_id,
            action_ids=payload.action_ids or None,
            note=payload.note,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_run_response(result)


@router.get("", response_model=CaseListResponse)
def list_cases(
    status: list[Literal["new", "triaged", "waiting_for_requester", "waiting_for_approval", "planned", "in_progress", "partially_completed", "resolved", "closed", "failed", "cancelled"]] | None = Query(default=None),
    workflow_type: list[Literal["access_request", "onboarding", "auth_issue", "policy_qa", "unknown"]] | None = Query(default=None),
    priority: list[Literal["low", "normal", "high", "urgent"]] | None = Query(default=None),
    channel: list[Literal["slack", "portal", "email", "api", "scheduler"]] | None = Query(default=None),
    assigned_team: str | None = None,
    assigned_operator_id: str | None = None,
    has_external_ticket: bool | None = None,
    q: str | None = Query(default=None, min_length=1),
    active_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    case_service: CaseService = Depends(get_case_service),
) -> CaseListResponse:
    result = case_service.list_cases(
        statuses=list(status or []),
        workflow_types=list(workflow_type or []),
        priorities=list(priority or []),
        channels=list(channel or []),
        assigned_team=assigned_team,
        assigned_operator_id=assigned_operator_id,
        has_external_ticket=has_external_ticket,
        query=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    payload = to_json_safe(result)
    return CaseListResponse(**payload)


@router.get("/{case_id}/state", response_model=CaseStateResponse)
def get_case_state(case_id: str, dispatcher: CaseGraphDispatcher = Depends(get_dispatcher)) -> CaseStateResponse:
    return CaseStateResponse(case_id=case_id, state=to_json_safe(dispatcher.get_case_state(case_id)))


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
) -> CaseDetailResponse:
    return CaseDetailResponse(case_id=case_id, detail=to_json_safe(case_service.get_case_detail(case_id)))


@router.get("/{case_id}/approvals", response_model=ApprovalListResponse)
def list_case_approvals(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
) -> ApprovalListResponse:
    if not case_service.get_case_projection(case_id):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    approvals = case_service.list_case_approvals(case_id)
    return ApprovalListResponse(
        case_id=case_id,
        approvals=[ApprovalResponse(**approval) for approval in to_json_safe(approvals)],
    )


@router.post("/{case_id}/assign", response_model=CaseAssignmentResponse)
def assign_case(
    case_id: str,
    payload: CaseAssignmentRequest,
    case_service: CaseService = Depends(get_case_service),
    ticket_sync_service: TicketSyncService = Depends(get_ticket_sync_service),
) -> CaseAssignmentResponse:
    detail = case_service.assign_case(
        case_id,
        actor_id=payload.actor_id,
        assigned_team=payload.assigned_team,
        assigned_operator_id=payload.assigned_operator_id,
        status=payload.status,
        note=payload.note,
    )
    if not detail:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    ticket_sync_service.sync_assignment(
        detail,
        actor_id=payload.actor_id,
        assigned_team=payload.assigned_team,
        assigned_operator_id=payload.assigned_operator_id,
        note=payload.note,
    )
    refreshed_detail = case_service.get_case_projection(case_id) or detail
    return CaseAssignmentResponse(case_id=case_id, detail=to_json_safe(refreshed_detail))


@router.get("/{case_id}/comments", response_model=CaseCommentListResponse)
def list_case_comments(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
) -> CaseCommentListResponse:
    if not case_service.get_case_projection(case_id):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    comments = case_service.list_case_comments(case_id)
    return CaseCommentListResponse(
        case_id=case_id,
        comments=[CaseCommentResponse(**comment) for comment in comments],
    )


@router.post("/{case_id}/comments", response_model=CaseCommentResponse)
def add_case_comment(
    case_id: str,
    payload: CaseCommentRequest,
    case_service: CaseService = Depends(get_case_service),
    notification_service: NotificationService = Depends(get_notification_service),
    ticket_sync_service: TicketSyncService = Depends(get_ticket_sync_service),
) -> CaseCommentResponse:
    comment = case_service.add_comment(
        case_id,
        actor_id=payload.actor_id,
        visibility=payload.visibility,
        body=payload.body,
    )
    if not comment:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")

    projection = case_service.get_case_projection(case_id)
    if payload.visibility == "requester":
        if projection:
            notification_service.send_requester_message(projection, payload.body, actor_id=payload.actor_id)
            ticket_sync_service.sync_comment(
                projection,
                actor_id=payload.actor_id,
                visibility=payload.visibility,
                body=payload.body,
            )
    else:
        if projection:
            ticket_sync_service.sync_comment(
                projection,
                actor_id=payload.actor_id,
                visibility=payload.visibility,
                body=payload.body,
            )

    return CaseCommentResponse(**to_json_safe(comment))


@router.get("/{case_id}/artifacts", response_model=CaseArtifactListResponse)
def list_case_artifacts(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> CaseArtifactListResponse:
    if not case_service.get_case_projection(case_id):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    artifacts = artifact_service.list_case_artifacts(case_id)
    return CaseArtifactListResponse(
        case_id=case_id,
        artifacts=[CaseArtifactResponse(**artifact) for artifact in artifacts],
    )


@router.post("/{case_id}/artifacts", response_model=CaseArtifactResponse)
def create_case_artifact(
    case_id: str,
    payload: CaseArtifactCreateRequest,
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> CaseArtifactResponse:
    artifact = artifact_service.issue_upload(
        case_id,
        actor_id=payload.actor_id,
        file_name=payload.file_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        visibility=payload.visibility,
        artifact_type=payload.artifact_type,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return CaseArtifactResponse(**to_json_safe(artifact))


@router.post("/{case_id}/artifacts/{artifact_id}/complete", response_model=CaseArtifactResponse)
def complete_case_artifact(
    case_id: str,
    artifact_id: str,
    payload: CaseArtifactCompleteRequest,
    artifact_service: ArtifactService = Depends(get_artifact_service),
    case_service: CaseService = Depends(get_case_service),
    ticket_sync_service: TicketSyncService = Depends(get_ticket_sync_service),
) -> CaseArtifactResponse:
    artifact = artifact_service.complete_upload(
        case_id,
        artifact_id,
        actor_id=payload.actor_id,
        checksum=payload.checksum,
    )
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact not found for case: {case_id}")

    projection = case_service.get_case_projection(case_id)
    if projection:
        ticket_sync_service.sync_comment(
            projection,
            actor_id=payload.actor_id,
            visibility=artifact.get("visibility", "internal"),
            body=f"Artifact uploaded: {artifact.get('file_name')} ({artifact.get('artifact_type')}).",
        )

    return CaseArtifactResponse(**to_json_safe(artifact))


@router.get("/{case_id}/timeline", response_model=CaseTimelineResponse)
def get_case_timeline(
    case_id: str,
    case_service: CaseService = Depends(get_case_service),
) -> CaseTimelineResponse:
    events = case_service.list_case_timeline(case_id)
    return CaseTimelineResponse(
        case_id=case_id,
        events=[CaseEventResponse(**event) for event in events],
    )


@router.get("/{case_id}/audit", response_model=AuditLogListResponse)
def get_case_audit_logs(
    case_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    case_service: CaseService = Depends(get_case_service),
) -> AuditLogListResponse:
    if not case_service.get_case_projection(case_id):
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    logs = case_service.list_case_audit_logs(case_id, limit=limit)
    return AuditLogListResponse(
        case_id=case_id,
        logs=[AuditLogResponse(**log) for log in to_json_safe(logs)],
    )
