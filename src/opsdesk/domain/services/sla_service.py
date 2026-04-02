from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...config import Settings, get_settings
from ...storage import get_sessionmaker
from ..enums import CasePriority, CaseStatus
from ..repositories import AuditLogRepository, CaseEventRepository, CaseRepository

FIRST_RESPONSE_TARGETS = {
    CasePriority.LOW.value: timedelta(hours=4),
    CasePriority.NORMAL.value: timedelta(hours=2),
    CasePriority.HIGH.value: timedelta(minutes=30),
    CasePriority.URGENT.value: timedelta(minutes=15),
}

RESOLUTION_TARGETS = {
    CasePriority.LOW.value: timedelta(hours=24),
    CasePriority.NORMAL.value: timedelta(hours=8),
    CasePriority.HIGH.value: timedelta(hours=4),
    CasePriority.URGENT.value: timedelta(hours=1),
}

PAUSED_STATUSES = {
    CaseStatus.WAITING_FOR_REQUESTER.value,
    CaseStatus.WAITING_FOR_APPROVAL.value,
}

TERMINAL_STATUSES = {
    CaseStatus.RESOLVED.value,
    CaseStatus.CLOSED.value,
    CaseStatus.CANCELLED.value,
    CaseStatus.FAILED.value,
}

ESCALATABLE_STATUSES = {
    CaseStatus.NEW.value,
    CaseStatus.TRIAGED.value,
    CaseStatus.PLANNED.value,
    CaseStatus.IN_PROGRESS.value,
    CaseStatus.PARTIALLY_COMPLETED.value,
}


@dataclass
class SlaService:
    session_factory: sessionmaker[Session]
    escalation_cooldown: timedelta

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

    def refresh_state(self, state: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        if not state:
            return {}

        current_time = now or datetime.now(timezone.utc)
        priority = str(state.get("priority", CasePriority.NORMAL.value))
        status = str(state.get("status", CaseStatus.NEW.value))
        reference_time = self._reference_time(state, current_time)

        sla = dict(state.get("sla", {}))
        if not sla.get("first_response_due_at"):
            sla["first_response_due_at"] = (reference_time + FIRST_RESPONSE_TARGETS.get(priority, FIRST_RESPONSE_TARGETS[CasePriority.NORMAL.value])).isoformat()
        if not sla.get("resolution_due_at"):
            sla["resolution_due_at"] = (reference_time + RESOLUTION_TARGETS.get(priority, RESOLUTION_TARGETS[CasePriority.NORMAL.value])).isoformat()

        sla["breach_risk"] = self._compute_breach_risk(
            status=status,
            resolution_due_at=sla.get("resolution_due_at"),
            now=current_time,
        )
        sla["last_escalated_at"] = sla.get("last_escalated_at")

        return {
            **state,
            "sla": sla,
        }

    def scan_cases(self, *, limit: int = 100, now: datetime | None = None) -> dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        current_time_iso = current_time.isoformat()

        with self._session_scope() as session:
            repository = CaseRepository(session)
            cases = repository.list_active_cases(limit=limit)
            updated_count = 0
            escalated_count = 0
            items: list[dict[str, Any]] = []

            for case in cases:
                refreshed_state = self.refresh_state(CaseRepository.to_state_projection(case), now=current_time)
                metadata = dict(case.metadata_json or {})
                operator_notes = list(metadata.get("operator_notes", []))
                refreshed_sla = dict(refreshed_state.get("sla", {}))

                escalated = False
                if self._should_escalate(status=case.status.value, sla=refreshed_sla, now=current_time):
                    escalated = True
                    escalated_count += 1
                    refreshed_sla["last_escalated_at"] = current_time_iso
                    operator_notes.append(
                        f"SLA escalation triggered at {current_time_iso} because the case is nearing or breaching its resolution target."
                    )
                    summary = "SLA escalation triggered by scheduler scan."
                    payload = {
                        "breach_risk": refreshed_sla.get("breach_risk", "low"),
                        "resolution_due_at": refreshed_sla.get("resolution_due_at"),
                        "last_escalated_at": refreshed_sla.get("last_escalated_at"),
                    }
                    AuditLogRepository(session).create(
                        case_id=case.id,
                        event_type="sla_escalation",
                        actor_id="scheduler",
                        summary=summary,
                        payload=payload,
                    )
                    CaseEventRepository(session).create(
                        case_id=case.id,
                        event_type="sla_escalation",
                        actor_id="scheduler",
                        summary=summary,
                        payload=payload,
                    )

                did_update = False
                if metadata.get("sla") != refreshed_sla or metadata.get("operator_notes", []) != operator_notes:
                    metadata["sla"] = refreshed_sla
                    metadata["operator_notes"] = operator_notes
                    case.metadata_json = metadata
                    did_update = True

                if did_update:
                    updated_count += 1

                items.append(
                    {
                        "case_id": case.id,
                        "status": case.status.value,
                        "priority": case.priority.value,
                        "breach_risk": refreshed_sla.get("breach_risk", "low"),
                        "resolution_due_at": refreshed_sla.get("resolution_due_at"),
                        "last_escalated_at": refreshed_sla.get("last_escalated_at"),
                        "escalated": escalated,
                    }
                )

            return {
                "scanned_count": len(cases),
                "updated_count": updated_count,
                "escalated_count": escalated_count,
                "items": items,
            }

    @staticmethod
    def _reference_time(state: dict[str, Any], fallback: datetime) -> datetime:
        normalized_request = state.get("normalized_request", {})
        received_at = normalized_request.get("received_at")
        created_at = state.get("created_at")

        for candidate in (received_at, created_at):
            parsed = SlaService._parse_datetime(candidate)
            if parsed is not None:
                return parsed
        return fallback

    @staticmethod
    def _compute_breach_risk(*, status: str, resolution_due_at: str | None, now: datetime) -> str:
        if status in TERMINAL_STATUSES or status in PAUSED_STATUSES:
            return "low"

        due_at = SlaService._parse_datetime(resolution_due_at)
        if due_at is None:
            return "low"

        remaining = due_at - now
        if remaining <= timedelta(0):
            return "high"
        if remaining <= timedelta(minutes=30):
            return "high"
        if remaining <= timedelta(hours=2):
            return "medium"
        return "low"

    def _should_escalate(self, *, status: str, sla: dict[str, Any], now: datetime) -> bool:
        if status not in ESCALATABLE_STATUSES:
            return False
        if sla.get("breach_risk") != "high":
            return False

        last_escalated_at = self._parse_datetime(sla.get("last_escalated_at"))
        if last_escalated_at is not None and now - last_escalated_at < self.escalation_cooldown:
            return False
        return True

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


def create_sla_service(settings: Settings | None = None) -> SlaService:
    resolved_settings = settings or get_settings()
    return SlaService(
        session_factory=get_sessionmaker(),
        escalation_cooldown=timedelta(minutes=resolved_settings.sla_escalation_cooldown_minutes),
    )
