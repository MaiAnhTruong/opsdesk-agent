from __future__ import annotations

from fastapi import Request

from ..config import Settings
from ..connectors import ConnectorRegistry
from ..domain.services import ApprovalService, ArtifactService, CaseService, NotificationService, SlaService, TicketSyncService
from ..runtime import CaseGraphDispatcher
from ..workers import SchedulerWorker


def get_dispatcher(request: Request) -> CaseGraphDispatcher:
    return request.app.state.dispatcher


def get_connector_registry(request: Request) -> ConnectorRegistry:
    return request.app.state.connector_registry


def get_case_service(request: Request) -> CaseService:
    return request.app.state.case_service


def get_artifact_service(request: Request) -> ArtifactService:
    return request.app.state.artifact_service


def get_notification_service(request: Request) -> NotificationService:
    return request.app.state.notification_service


def get_approval_service(request: Request) -> ApprovalService:
    return request.app.state.approval_service


def get_ticket_sync_service(request: Request) -> TicketSyncService:
    return request.app.state.ticket_sync_service


def get_sla_service(request: Request) -> SlaService:
    return request.app.state.sla_service


def get_scheduler_worker(request: Request) -> SchedulerWorker:
    return request.app.state.scheduler_worker


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
