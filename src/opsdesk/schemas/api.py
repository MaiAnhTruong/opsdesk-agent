from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CaseCreateRequest(BaseModel):
    requester_email: str
    requester_name: str | None = None
    message: str = Field(min_length=1)
    title: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    channel: Literal["slack", "portal", "email", "api", "scheduler"] = "api"
    case_id: str | None = None


class SlackEventRequest(BaseModel):
    user_email: str
    user_name: str | None = None
    text: str = Field(min_length=1)
    channel_name: str | None = None
    case_id: str | None = None


class PortalCaseCreateRequest(BaseModel):
    requester_email: str
    requester_name: str | None = None
    message: str = Field(min_length=1)
    title: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    case_id: str | None = None


class PortalCaseStatusResponse(BaseModel):
    case_id: str
    status: str
    workflow_type: str
    current_stage: str
    requester_updates: list[str]


class CaseResumeRequest(BaseModel):
    resume_value: Any


class CaseRetryRequest(BaseModel):
    actor_id: str
    action_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class CaseRunResponse(BaseModel):
    case_id: str
    thread_id: str
    status: str
    workflow_type: str
    current_stage: str
    result: dict[str, Any]


class CaseStateResponse(BaseModel):
    case_id: str
    state: dict[str, Any]


class CaseDetailResponse(BaseModel):
    case_id: str
    detail: dict[str, Any]


class ApprovalResponse(BaseModel):
    approval_id: str
    approval_type: str
    approval_mode: str | None = None
    sequence_no: int | None = None
    requested_from_actor_id: str
    requested_by_actor_id: str
    requested_from: dict[str, Any] | None = None
    prerequisite_approval_ids: list[str] = Field(default_factory=list)
    requested_action_ids: list[str] = Field(default_factory=list)
    summary: str | None = None
    decision: str
    reason: str | None = None
    expires_at: str | None = None
    last_reminded_at: str | None = None
    decided_at: str | None = None


class ApprovalListResponse(BaseModel):
    case_id: str
    approvals: list[ApprovalResponse]


class CaseAssignmentRequest(BaseModel):
    actor_id: str
    assigned_team: str | None = None
    assigned_operator_id: str | None = None
    status: Literal["new", "triaged", "waiting_for_requester", "waiting_for_approval", "planned", "in_progress", "partially_completed", "resolved", "closed", "failed", "cancelled"] | None = None
    note: str | None = None


class CaseAssignmentResponse(BaseModel):
    case_id: str
    detail: dict[str, Any]


class CaseListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]


class CaseEventResponse(BaseModel):
    event_id: str
    case_id: str
    event_type: str
    actor_id: str
    summary: str
    payload: dict[str, Any]
    created_at: str | None = None


class CaseTimelineResponse(BaseModel):
    case_id: str
    events: list[CaseEventResponse]


class AuditLogResponse(BaseModel):
    audit_log_id: str
    case_id: str
    event_type: str
    actor_id: str
    summary: str
    payload: dict[str, Any]
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    case_id: str
    logs: list[AuditLogResponse]


class CaseCommentRequest(BaseModel):
    actor_id: str
    visibility: Literal["internal", "requester"] = "internal"
    body: str = Field(min_length=1)


class CaseCommentResponse(BaseModel):
    comment_id: str
    case_id: str
    author_actor_id: str
    visibility: str
    body: str
    created_at: str | None = None


class CaseCommentListResponse(BaseModel):
    case_id: str
    comments: list[CaseCommentResponse]


class CaseArtifactCreateRequest(BaseModel):
    actor_id: str
    file_name: str = Field(min_length=1)
    content_type: str = "application/octet-stream"
    size_bytes: int = Field(ge=0)
    visibility: Literal["internal", "requester"] = "internal"
    artifact_type: Literal["attachment", "screenshot", "log_bundle", "export"] = "attachment"


class CaseArtifactCompleteRequest(BaseModel):
    actor_id: str
    checksum: str | None = None


class CaseArtifactResponse(BaseModel):
    artifact_id: str
    case_id: str
    artifact_type: str
    visibility: str
    file_name: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    checksum: str | None = None
    uploaded_by_actor_id: str
    created_at: str | None = None
    updated_at: str | None = None
    uploaded_at: str | None = None
    download_url: str | None = None
    upload: dict[str, Any] | None = None


class CaseArtifactListResponse(BaseModel):
    case_id: str
    artifacts: list[CaseArtifactResponse]


class SlaScanItemResponse(BaseModel):
    case_id: str
    status: str
    priority: str
    breach_risk: str
    resolution_due_at: str | None = None
    last_escalated_at: str | None = None
    escalated: bool


class SlaScanResponse(BaseModel):
    scanned_count: int
    updated_count: int
    escalated_count: int
    items: list[SlaScanItemResponse]


class ApprovalExpiryScanItemResponse(BaseModel):
    approval_id: str
    case_id: str
    expired: bool
    status: str


class ApprovalExpiryScanResponse(BaseModel):
    scanned_count: int
    expired_count: int
    items: list[ApprovalExpiryScanItemResponse]


class ApprovalReminderScanItemResponse(BaseModel):
    approval_id: str
    case_id: str
    reminded: bool
    status: str


class ApprovalReminderScanResponse(BaseModel):
    scanned_count: int
    reminded_count: int
    items: list[ApprovalReminderScanItemResponse]


class ConnectorDescriptorResponse(BaseModel):
    name: str
    supported_actions: list[str]


class ConnectorInventoryResponse(BaseModel):
    items: list[ConnectorDescriptorResponse]


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    actor_id: str = "operator"
    reason: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval_id: str
    case_id: str
    decision: str
    resumed: bool
    result: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
