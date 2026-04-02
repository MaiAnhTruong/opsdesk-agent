from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.services import ApprovalService
from ..runtime import CaseGraphDispatcher
from ..domain.services import SlaService


@dataclass
class SchedulerWorker:
    sla_service: SlaService
    approval_service: ApprovalService | None = None
    dispatcher: CaseGraphDispatcher | None = None
    approval_reminder_hours: int = 6
    approval_reminder_cooldown_minutes: int = 240

    def run_sla_scan(self, *, limit: int = 100) -> dict[str, Any]:
        return self.sla_service.scan_cases(limit=limit)

    def run_approval_expiry_scan(self, *, limit: int = 100) -> dict[str, Any]:
        if self.approval_service is None or self.dispatcher is None:
            return {"scanned_count": 0, "expired_count": 0, "items": []}

        expired_approvals = self.approval_service.list_expired_pending(limit=limit)
        items = []
        expired_count = 0
        for approval in expired_approvals:
            self.dispatcher.expire_case_approval(
                approval["case_id"],
                approval_id=approval["approval_id"],
                actor_id="scheduler",
                reason="Approval expired during scheduler scan.",
            )
            expired_count += 1
            items.append(
                {
                    "approval_id": approval["approval_id"],
                    "case_id": approval["case_id"],
                    "expired": True,
                    "status": "cancelled",
                }
            )
        return {
            "scanned_count": len(expired_approvals),
            "expired_count": expired_count,
            "items": items,
        }

    def run_approval_reminder_scan(self, *, limit: int = 100) -> dict[str, Any]:
        if self.approval_service is None:
            return {"scanned_count": 0, "reminded_count": 0, "items": []}

        reminders = self.approval_service.list_pending_near_expiry(
            remind_before_hours=self.approval_reminder_hours,
            cooldown_minutes=self.approval_reminder_cooldown_minutes,
            limit=limit,
        )
        items = []
        reminded_count = 0
        for approval in reminders:
            record = self.approval_service.record_reminder(
                approval["approval_id"],
                actor_id="scheduler",
                reason="Approval approaching expiry.",
            )
            if record:
                reminded_count += 1
                items.append(
                    {
                        "approval_id": record["approval_id"],
                        "case_id": record["case_id"],
                        "reminded": True,
                        "status": record["decision"],
                    }
                )
        return {
            "scanned_count": len(reminders),
            "reminded_count": reminded_count,
            "items": items,
        }


def create_scheduler_worker(
    sla_service: SlaService,
    *,
    approval_service: ApprovalService | None = None,
    dispatcher: CaseGraphDispatcher | None = None,
    approval_reminder_hours: int = 6,
    approval_reminder_cooldown_minutes: int = 240,
) -> SchedulerWorker:
    return SchedulerWorker(
        sla_service=sla_service,
        approval_service=approval_service,
        dispatcher=dispatcher,
        approval_reminder_hours=approval_reminder_hours,
        approval_reminder_cooldown_minutes=approval_reminder_cooldown_minutes,
    )
