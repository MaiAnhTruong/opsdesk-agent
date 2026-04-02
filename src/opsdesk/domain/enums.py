from __future__ import annotations

from enum import StrEnum


class WorkflowType(StrEnum):
    ACCESS_REQUEST = "access_request"
    ONBOARDING = "onboarding"
    AUTH_ISSUE = "auth_issue"
    POLICY_QA = "policy_qa"
    UNKNOWN = "unknown"


class CasePriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class CaseStatus(StrEnum):
    NEW = "new"
    TRIAGED = "triaged"
    WAITING_FOR_REQUESTER = "waiting_for_requester"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    PARTIALLY_COMPLETED = "partially_completed"
    RESOLVED = "resolved"
    CLOSED = "closed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeStage(StrEnum):
    INTAKE = "intake"
    CLASSIFICATION = "classification"
    CONTEXT_HYDRATION = "context_hydration"
    PLANNING = "planning"
    PERMISSION_EVALUATION = "permission_evaluation"
    APPROVAL_WAIT = "approval_wait"
    EXECUTION = "execution"
    POST_EXECUTION = "post_execution"
    FOLLOW_UP = "follow_up"
    CLOSURE = "closure"


class ApprovalMode(StrEnum):
    AUTO = "auto"
    MANAGER = "manager"
    OWNER = "owner"
    OPERATOR = "operator"
    SECURITY = "security"
    DENY = "deny"


class ApprovalDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ActionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
