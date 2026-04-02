from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...connectors import DomainToolExecutor, build_default_domain_tool_executor
from ...storage import get_sessionmaker
from ..repositories import AuditLogRepository, CaseEventRepository, CaseRepository


@dataclass
class NotificationService:
    session_factory: sessionmaker[Session]
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

    def notify_requester(self, state: dict[str, Any], *, actor_id: str = "system") -> dict[str, Any] | None:
        case_id = state.get("case_id")
        if not case_id or state.get("channel") != "slack":
            return None

        requester_updates = list(state.get("requester_updates", []))
        if not requester_updates:
            return None

        latest_message = str(requester_updates[-1]).strip()
        if not latest_message:
            return None

        return self.send_requester_message(state, latest_message, actor_id=actor_id)

    def send_requester_message(self, state: dict[str, Any], message: str, *, actor_id: str = "system") -> dict[str, Any] | None:
        case_id = state.get("case_id")
        if not case_id or state.get("channel") != "slack":
            return None

        latest_message = str(message).strip()
        if not latest_message:
            return None

        normalized_request = dict(state.get("normalized_request", {}))
        channel_name = str(normalized_request.get("channel_name", "employee-updates"))
        recipient = str(state.get("requester", {}).get("email", state.get("requester", {}).get("actor_id", "unknown")))
        message_hash = sha1(latest_message.encode("utf-8")).hexdigest()[:12]

        response = self.domain_tool_executor.execute_system_action(
            case_id=str(case_id),
            tenant_id=str(state.get("tenant_id", "default")),
            actor_id=actor_id,
            target_system="slack",
            action_type="post_requester_update",
            idempotency_key=f"notify:{case_id}:{message_hash}",
            payload={
                "channel": channel_name,
                "recipient": recipient,
                "message": latest_message,
                "status": state.get("status"),
            },
        )
        if not response["ok"]:
            return self._record_failure_event(
                case_id=str(case_id),
                actor_id=actor_id,
                summary=response["summary"],
                payload={
                    "channel": channel_name,
                    "recipient": recipient,
                    "message": latest_message,
                    "retryable": response.get("retryable", False),
                    "error_code": response.get("error_code"),
                    "details": response.get("raw_result", {}),
                },
            )

        with self._session_scope() as session:
            case = CaseRepository(session).get(str(case_id))
            if case is None:
                return None

            payload = {
                "channel": channel_name,
                "recipient": recipient,
                "message": latest_message,
                "notification_ref": response["external_ref"],
            }
            summary = response["summary"]
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="requester_notification",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="requester_notification",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "notification_ref": response["external_ref"],
                "summary": summary,
            }

    def _record_failure_event(
        self,
        *,
        case_id: str,
        actor_id: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return None

            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="requester_notification_failed",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="requester_notification_failed",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "notification_ref": None,
                "summary": summary,
            }


def create_notification_service(domain_tool_executor: DomainToolExecutor | None = None) -> NotificationService:
    return NotificationService(
        session_factory=get_sessionmaker(),
        domain_tool_executor=domain_tool_executor or build_default_domain_tool_executor(),
    )
