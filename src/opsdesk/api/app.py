from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..connectors import build_default_connector_registry
from ..config import get_settings
from ..domain.services import create_approval_service, create_artifact_service, create_sla_service
from ..runtime import create_dispatcher
from ..storage import create_all, create_object_storage_service, dispose_engine
from ..workers import create_scheduler_worker
from .routes import approvals_router, cases_router, health_router, ops_router, portal_router, slack_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    if settings.database_auto_create:
        create_all()
    app.state.object_storage = create_object_storage_service(settings)
    app.state.sla_service = create_sla_service(settings)
    app.state.connector_registry = build_default_connector_registry()
    app.state.dispatcher = create_dispatcher(
        settings,
        sla_service=app.state.sla_service,
        connector_registry=app.state.connector_registry,
    )
    app.state.case_service = app.state.dispatcher.case_service
    app.state.artifact_service = create_artifact_service(app.state.object_storage)
    app.state.notification_service = app.state.dispatcher.notification_service
    app.state.approval_service = create_approval_service()
    app.state.ticket_sync_service = app.state.dispatcher.ticket_sync_service
    app.state.scheduler_worker = create_scheduler_worker(
        app.state.sla_service,
        approval_service=app.state.approval_service,
        dispatcher=app.state.dispatcher,
        approval_reminder_hours=settings.approval_reminder_hours,
        approval_reminder_cooldown_minutes=settings.approval_reminder_cooldown_minutes,
    )
    try:
        yield
    finally:
        dispatcher = getattr(app.state, "dispatcher", None)
        if dispatcher is not None:
            dispatcher.close()
        dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(cases_router, prefix=settings.api_prefix)
    app.include_router(approvals_router, prefix=settings.api_prefix)
    app.include_router(ops_router, prefix=settings.api_prefix)
    app.include_router(portal_router, prefix=settings.api_prefix)
    app.include_router(slack_router, prefix=settings.api_prefix)
    return app


app = create_app()
