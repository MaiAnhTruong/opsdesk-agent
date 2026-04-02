from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .enums import ActionStatus, ApprovalDecision, ApprovalMode, CasePriority, CaseStatus, RiskLevel, WorkflowType


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for product tables."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CaseRecord(TimestampMixin, Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_ticket_id: Mapped[str | None] = mapped_column(String(128))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    workflow_type: Mapped[WorkflowType] = mapped_column(SqlEnum(WorkflowType, native_enum=False), nullable=False)
    intent: Mapped[str] = mapped_column(String(128), nullable=False, default=WorkflowType.UNKNOWN.value)
    priority: Mapped[CasePriority] = mapped_column(SqlEnum(CasePriority, native_enum=False), nullable=False, default=CasePriority.NORMAL)
    status: Mapped[CaseStatus] = mapped_column(SqlEnum(CaseStatus, native_enum=False), nullable=False, default=CaseStatus.NEW)
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_employee_id: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    requested_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_team: Mapped[str | None] = mapped_column(String(128))
    assigned_operator_id: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)


class CaseActionRecord(TimestampMixin, Base):
    __tablename__ = "case_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_system: Mapped[str] = mapped_column(String(128), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    risk_level: Mapped[RiskLevel] = mapped_column(SqlEnum(RiskLevel, native_enum=False), nullable=False)
    approval_mode: Mapped[ApprovalMode] = mapped_column(SqlEnum(ApprovalMode, native_enum=False), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(SqlEnum(ActionStatus, native_enum=False), nullable=False, default=ActionStatus.PENDING)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRecord(TimestampMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_from_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(SqlEnum(ApprovalDecision, native_enum=False), nullable=False, default=ApprovalDecision.PENDING)
    reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resume_token: Mapped[str | None] = mapped_column(String(255))


class AuditLogRecord(TimestampMixin, Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CaseEventRecord(Base):
    __tablename__ = "case_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CaseCommentRecord(Base):
    __tablename__ = "case_comments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CaseArtifactRecord(TimestampMixin, Base):
    __tablename__ = "case_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, default="attachment")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    upload_token: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_upload")
    checksum: Mapped[str | None] = mapped_column(String(128))
    uploaded_by_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
