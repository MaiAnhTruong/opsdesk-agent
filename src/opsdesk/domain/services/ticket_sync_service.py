from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...connectors import ConnectorRegistry, DomainToolExecutor, build_default_connector_registry, build_default_domain_tool_executor
from ...storage import get_sessionmaker
from ..repositories import AuditLogRepository, CaseEventRepository, CaseRepository


@dataclass
class TicketSyncService:
    session_factory: sessionmaker[Session]
    connector_registry: ConnectorRegistry
    domain_tool_executor: DomainToolExecutor

    @contextmanager
    def _session_scope(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def sync_case(self, state: dict[str, Any], *, actor_id: str = "system") -> dict[str, Any] | None:
        case_id = state.get("case_id")
        if not case_id:
            return None

        response = self.domain_tool_executor.execute_system_action(
            case_id=str(case_id),
            tenant_id=str(state.get("tenant_id", "default")),
            actor_id=actor_id,
            target_system="ticketing",
            action_type="upsert_ticket",
            idempotency_key=f"ticket-sync:{case_id}:{state.get('status', 'unknown')}",
            payload={
                "case_id": case_id,
                "external_ticket_id": state.get("external_ticket_id"),
                "title": state.get("title"),
                "summary": state.get("summary") or (state.get("requester_updates") or [""])[-1],
                "status": state.get("status"),
                "workflow_type": state.get("workflow_type"),
                "priority": state.get("priority"),
            },
        )
        if not response["ok"]:
            return self._record_failure_event(
                case_id=str(case_id),
                actor_id=actor_id,
                event_type="ticket_sync_failed",
                summary=response["summary"],
                payload={
                    "case_id": case_id,
                    "status": state.get("status"),
                    "workflow_type": state.get("workflow_type"),
                    "retryable": response.get("retryable", False),
                    "error_code": response.get("error_code"),
                    "details": response.get("raw_result", {}),
                },
            )

        with self._session_scope() as session:
            case = CaseRepository(session).update_external_ticket(str(case_id), str(response["external_ref"]))
            if case is None:
                return None

            payload = {
                "ticket_id": response["external_ref"],
                "status": state.get("status"),
                "workflow_type": state.get("workflow_type"),
            }
            summary = response["summary"]
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="ticket_sync",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="ticket_sync",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "external_ticket_id": case.external_ticket_id,
                "summary": summary,
            }

    def sync_assignment(
        self,
        state: dict[str, Any],
        *,
        actor_id: str,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        case_id = state.get("case_id")
        if not case_id:
            return None

        external_ticket_id = state.get("external_ticket_id")
        if not external_ticket_id:
            ticket_state = self.sync_case(state, actor_id=actor_id)
            if ticket_state:
                external_ticket_id = ticket_state.get("external_ticket_id")

        response = self.domain_tool_executor.execute_system_action(
            case_id=str(case_id),
            tenant_id=str(state.get("tenant_id", "default")),
            actor_id=actor_id,
            target_system="ticketing",
            action_type="assign_ticket",
            idempotency_key=f"ticket-assign:{case_id}:{assigned_team or '-'}:{assigned_operator_id or '-'}:{state.get('status', '-')}",
            payload={
                "case_id": case_id,
                "external_ticket_id": external_ticket_id,
                "assigned_team": assigned_team,
                "assigned_operator_id": assigned_operator_id,
                "status": state.get("status"),
                "note": note,
            },
        )
        if not response["ok"]:
            return self._record_failure_event(
                case_id=str(case_id),
                actor_id=actor_id,
                event_type="ticket_assignment_sync_failed",
                summary=response["summary"],
                payload={
                    "case_id": case_id,
                    "external_ticket_id": external_ticket_id,
                    "assigned_team": assigned_team,
                    "assigned_operator_id": assigned_operator_id,
                    "status": state.get("status"),
                    "note": note,
                    "retryable": response.get("retryable", False),
                    "error_code": response.get("error_code"),
                    "details": response.get("raw_result", {}),
                },
            )

        return self._record_ticket_event(
            case_id=str(case_id),
            actor_id=actor_id,
            event_type="ticket_assignment_sync",
            summary=response["summary"],
            payload=response["raw_result"],
            external_ticket_id=str(response["external_ref"] or external_ticket_id or ""),
        )

    def sync_comment(
        self,
        state: dict[str, Any],
        *,
        actor_id: str,
        visibility: str,
        body: str,
    ) -> dict[str, Any] | None:
        case_id = state.get("case_id")
        if not case_id:
            return None

        external_ticket_id = state.get("external_ticket_id")
        if not external_ticket_id:
            ticket_state = self.sync_case(state, actor_id=actor_id)
            if ticket_state:
                external_ticket_id = ticket_state.get("external_ticket_id")

        response = self.domain_tool_executor.execute_system_action(
            case_id=str(case_id),
            tenant_id=str(state.get("tenant_id", "default")),
            actor_id=actor_id,
            target_system="ticketing",
            action_type="append_ticket_note",
            idempotency_key=f"ticket-note:{case_id}:{visibility}:{sha1(body.encode('utf-8')).hexdigest()[:12]}",
            payload={
                "case_id": case_id,
                "external_ticket_id": external_ticket_id,
                "visibility": visibility,
                "body": body,
                "status": state.get("status"),
            },
        )
        if not response["ok"]:
            return self._record_failure_event(
                case_id=str(case_id),
                actor_id=actor_id,
                event_type="ticket_comment_sync_failed",
                summary=response["summary"],
                payload={
                    "case_id": case_id,
                    "external_ticket_id": external_ticket_id,
                    "visibility": visibility,
                    "body": body,
                    "status": state.get("status"),
                    "retryable": response.get("retryable", False),
                    "error_code": response.get("error_code"),
                    "details": response.get("raw_result", {}),
                },
            )

        return self._record_ticket_event(
            case_id=str(case_id),
            actor_id=actor_id,
            event_type="ticket_comment_sync",
            summary=response["summary"],
            payload=response["raw_result"],
            external_ticket_id=str(response["external_ref"] or external_ticket_id or ""),
        )

    def _record_ticket_event(
        self,
        *,
        case_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
        external_ticket_id: str,
    ) -> dict[str, Any] | None:
        with self._session_scope() as session:
            case = CaseRepository(session).update_external_ticket(case_id, external_ticket_id)
            if case is None:
                return None

            AuditLogRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "external_ticket_id": case.external_ticket_id,
                "summary": summary,
            }

    def _record_failure_event(
        self,
        *,
        case_id: str,
        actor_id: str,
        event_type: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return None

            AuditLogRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "external_ticket_id": case.external_ticket_id,
                "summary": summary,
            }


def create_ticket_sync_service(
    connector_registry: ConnectorRegistry | None = None,
    domain_tool_executor: DomainToolExecutor | None = None,
) -> TicketSyncService:
    resolved_registry = connector_registry or build_default_connector_registry()
    resolved_executor = domain_tool_executor or build_default_domain_tool_executor(resolved_registry)
    return TicketSyncService(
        session_factory=get_sessionmaker(),
        connector_registry=resolved_registry,
        domain_tool_executor=resolved_executor,
    )
