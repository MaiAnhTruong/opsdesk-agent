from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ...storage import get_sessionmaker
from ..repositories import ActionRepository, ApprovalRepository, AuditLogRepository, CaseArtifactRepository, CaseCommentRepository, CaseEventRepository, CaseRepository


@dataclass
class CaseService:
    session_factory: sessionmaker[Session]

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

    def persist_graph_state(self, state: dict[str, Any], *, event_type: str, actor_id: str = "system") -> dict[str, Any]:
        case_id = state.get("case_id")
        if not case_id:
            return {}

        with self._session_scope() as session:
            case = CaseRepository(session).upsert_from_state(state)
            action_count = ActionRepository(session).sync_from_state(state)
            approval_count = ApprovalRepository(session).sync_from_state(state)
            summary = f"Persisted case snapshot with {action_count} actions and {approval_count} approvals."
            event_payload = {
                "status": state.get("status"),
                "current_stage": state.get("current_stage"),
                "workflow_type": state.get("workflow_type"),
            }
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=event_payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type=event_type,
                actor_id=actor_id,
                summary=summary,
                payload=event_payload,
            )
            return CaseRepository.to_state_projection(case)

    def get_case_projection(self, case_id: str) -> dict[str, Any]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return {}
            return CaseRepository.to_state_projection(case)

    def list_cases(
        self,
        *,
        statuses: list[str] | None = None,
        workflow_types: list[str] | None = None,
        priorities: list[str] | None = None,
        channels: list[str] | None = None,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        has_external_ticket: bool | None = None,
        query: str | None = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            repository = CaseRepository(session)
            resolved_statuses = list(statuses or [])
            if active_only and not resolved_statuses:
                resolved_statuses = [
                    "new",
                    "triaged",
                    "waiting_for_requester",
                    "waiting_for_approval",
                    "planned",
                    "in_progress",
                    "partially_completed",
                ]

            total = repository.count_cases(
                statuses=resolved_statuses or None,
                workflow_types=workflow_types,
                priorities=priorities,
                channels=channels,
                assigned_team=assigned_team,
                assigned_operator_id=assigned_operator_id,
                has_external_ticket=has_external_ticket,
                query=query,
            )
            cases = repository.list_cases(
                statuses=resolved_statuses or None,
                workflow_types=workflow_types,
                priorities=priorities,
                channels=channels,
                assigned_team=assigned_team,
                assigned_operator_id=assigned_operator_id,
                has_external_ticket=has_external_ticket,
                query=query,
                limit=limit,
                offset=offset,
            )

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": [CaseRepository.to_inbox_projection(case) for case in cases],
            }

    def get_case_detail(self, case_id: str) -> dict[str, Any]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return {}

            actions = ActionRepository(session).list_for_case(case_id)
            approvals = ApprovalRepository(session).list_for_case(case_id)
            artifacts = CaseArtifactRepository(session).list_for_case(case_id)
            comments = CaseCommentRepository(session).list_for_case(case_id)
            events = CaseEventRepository(session).list_for_case(case_id)
            base_projection = CaseRepository.to_state_projection(case)
            metadata_approvals = {
                approval["approval_id"]: approval
                for approval in base_projection.get("approvals", [])
                if approval.get("approval_id")
            }

            return {
                **base_projection,
                "actions": [
                    {
                        "action_id": action.id,
                        "sequence_no": action.sequence_no,
                        "action_type": action.action_type,
                        "target_system": action.target_system,
                        "target_resource": action.target_resource,
                        "risk_level": action.risk_level.value,
                        "approval_mode": action.approval_mode.value,
                        "status": action.status.value,
                        "idempotency_key": action.idempotency_key,
                        "request_payload": action.request_payload,
                        "result_payload": action.result_payload,
                        "error_code": action.error_code,
                        "error_detail": action.error_detail,
                    }
                    for action in actions
                ],
                "approvals_detail": [
                    self._serialize_approval(approval, metadata_approvals.get(approval.id, {}))
                    for approval in approvals
                ],
                "comments": [
                    {
                        "comment_id": comment.id,
                        "case_id": comment.case_id,
                        "author_actor_id": comment.author_actor_id,
                        "visibility": comment.visibility,
                        "body": comment.body,
                        "created_at": comment.created_at.isoformat() if comment.created_at else None,
                    }
                    for comment in comments
                ],
                "artifacts": [
                    {
                        "artifact_id": artifact.id,
                        "case_id": artifact.case_id,
                        "artifact_type": artifact.artifact_type,
                        "visibility": artifact.visibility,
                        "file_name": artifact.file_name,
                        "content_type": artifact.content_type,
                        "size_bytes": artifact.size_bytes,
                        "storage_key": artifact.storage_key,
                        "status": artifact.status,
                        "checksum": artifact.checksum,
                        "uploaded_by_actor_id": artifact.uploaded_by_actor_id,
                        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                        "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
                        "uploaded_at": artifact.uploaded_at.isoformat() if artifact.uploaded_at else None,
                        "download_url": None,
                    }
                    for artifact in artifacts
                ],
                "timeline": [
                    {
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "actor_id": event.actor_id,
                        "summary": event.summary,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                    for event in events
                ],
            }

    def list_case_timeline(self, case_id: str) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            events = CaseEventRepository(session).list_for_case(case_id)
            return [
                {
                    "event_id": event.id,
                    "case_id": event.case_id,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "summary": event.summary,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                for event in events
            ]

    def list_case_comments(self, case_id: str) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            comments = CaseCommentRepository(session).list_for_case(case_id)
            return [
                {
                    "comment_id": comment.id,
                    "case_id": comment.case_id,
                    "author_actor_id": comment.author_actor_id,
                    "visibility": comment.visibility,
                    "body": comment.body,
                    "created_at": comment.created_at.isoformat() if comment.created_at else None,
                }
                for comment in comments
            ]

    def list_case_audit_logs(self, case_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return []

            audit_logs = AuditLogRepository(session).list_for_case(case_id, limit=limit)
            return [
                {
                    "audit_log_id": log.id,
                    "case_id": log.case_id,
                    "event_type": log.event_type,
                    "actor_id": log.actor_id,
                    "summary": log.summary,
                    "payload": log.payload,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in audit_logs
            ]

    def list_case_approvals(self, case_id: str) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return []

            metadata_approvals = {
                approval["approval_id"]: approval
                for approval in (case.metadata_json or {}).get("approvals", [])
                if approval.get("approval_id")
            }
            approvals = ApprovalRepository(session).list_for_case(case_id)
            return [self._serialize_approval(approval, metadata_approvals.get(approval.id, {})) for approval in approvals]

    def assign_case(
        self,
        case_id: str,
        *,
        actor_id: str,
        assigned_team: str | None = None,
        assigned_operator_id: str | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            case_repository = CaseRepository(session)
            case = case_repository.update_assignment(
                case_id,
                assigned_team=assigned_team,
                assigned_operator_id=assigned_operator_id,
                status=status,
            )
            if case is None:
                return {}

            payload = {
                "assigned_team": case.assigned_team,
                "assigned_operator_id": case.assigned_operator_id,
                "status": case.status.value,
                "note": note,
            }
            summary = f"Case assigned to team={case.assigned_team or '-'} operator={case.assigned_operator_id or '-'}."
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="case_assignment",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="case_assignment",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            if note:
                CaseCommentRepository(session).create(
                    case_id=case.id,
                    author_actor_id=actor_id,
                    visibility="internal",
                    body=note,
                )
            return CaseRepository.to_state_projection(case)

    def add_comment(
        self,
        case_id: str,
        *,
        actor_id: str,
        visibility: str,
        body: str,
    ) -> dict[str, Any]:
        with self._session_scope() as session:
            case = CaseRepository(session).get(case_id)
            if case is None:
                return {}

            comment = CaseCommentRepository(session).create(
                case_id=case.id,
                author_actor_id=actor_id,
                visibility=visibility,
                body=body,
            )
            payload = {
                "comment_id": comment.id,
                "visibility": visibility,
                "body": body,
            }
            summary = f"Added {visibility} comment to case."
            AuditLogRepository(session).create(
                case_id=case.id,
                event_type="case_comment",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            CaseEventRepository(session).create(
                case_id=case.id,
                event_type="case_comment",
                actor_id=actor_id,
                summary=summary,
                payload=payload,
            )
            return {
                "comment_id": comment.id,
                "case_id": comment.case_id,
                "author_actor_id": comment.author_actor_id,
                "visibility": comment.visibility,
                "body": comment.body,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
            }

    @staticmethod
    def _serialize_approval(approval, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "approval_id": approval.id,
            "approval_type": approval.approval_type,
            "approval_mode": metadata.get("approval_mode"),
            "sequence_no": metadata.get("sequence_no"),
            "requested_from_actor_id": approval.requested_from_actor_id,
            "requested_by_actor_id": approval.requested_by_actor_id,
            "requested_from": metadata.get("requested_from"),
            "prerequisite_approval_ids": metadata.get("prerequisite_approval_ids", []),
            "requested_action_ids": metadata.get("requested_action_ids", []),
            "summary": metadata.get("summary"),
            "decision": approval.decision.value,
            "reason": approval.reason,
            "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
            "last_reminded_at": approval.last_reminded_at.isoformat() if approval.last_reminded_at else None,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        }


def create_case_service() -> CaseService:
    return CaseService(session_factory=get_sessionmaker())
