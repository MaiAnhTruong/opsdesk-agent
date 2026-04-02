from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.opsdesk.config import get_settings
from src.opsdesk.domain.repositories import ApprovalRepository
from src.opsdesk.storage.db import dispose_engine, get_engine, get_sessionmaker


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "opsdesk-test.db"
    object_root = tmp_path / "objects"

    monkeypatch.setenv("OPSDESK_DATABASE_URL", f"sqlite+pysqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("OPSDESK_DATABASE_AUTO_CREATE", "true")
    monkeypatch.setenv("OPSDESK_ARTIFACT_STORAGE_ROOT", object_root.as_posix())
    monkeypatch.setenv("OPSDESK_ARTIFACT_BASE_URL", "http://testserver/objects")

    get_settings.cache_clear()
    try:
        dispose_engine()
    except Exception:
        pass
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    from src.opsdesk.api.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    try:
        dispose_engine()
    except Exception:
        pass
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_settings.cache_clear()


def test_health_and_connector_inventory(client: TestClient) -> None:
    health = client.get("/api/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    connectors = client.get("/api/ops/connectors")
    assert connectors.status_code == 200
    connector_names = {item["name"] for item in connectors.json()["items"]}
    assert {"ticketing", "okta", "slack"}.issubset(connector_names)


def test_case_operator_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    case_id = payload["case_id"]
    assert payload["workflow_type"] == "auth_issue"

    assign_response = client.post(
        f"/api/cases/{case_id}/assign",
        json={
            "actor_id": "operator-1",
            "assigned_team": "it-helpdesk",
            "assigned_operator_id": "operator-1",
            "status": "in_progress",
            "note": "Taking ownership",
        },
    )
    assert assign_response.status_code == 200
    detail = assign_response.json()["detail"]
    assert detail["assigned_team"] == "it-helpdesk"
    assert detail["assigned_operator_id"] == "operator-1"
    assert detail["external_ticket_id"]

    comment_response = client.post(
        f"/api/cases/{case_id}/comments",
        json={
            "actor_id": "operator-1",
            "visibility": "internal",
            "body": "Initial triage completed",
        },
    )
    assert comment_response.status_code == 200
    assert comment_response.json()["visibility"] == "internal"

    comments_response = client.get(f"/api/cases/{case_id}/comments")
    assert comments_response.status_code == 200
    comments = comments_response.json()["comments"]
    assert len(comments) >= 2
    assert any(comment["body"] == "Initial triage completed" for comment in comments)


def test_case_list_supports_inbox_filters_and_search(client: TestClient) -> None:
    api_case_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    assert api_case_response.status_code == 200
    api_case_id = api_case_response.json()["case_id"]

    assign_response = client.post(
        f"/api/cases/{api_case_id}/assign",
        json={
            "actor_id": "operator-1",
            "assigned_team": "it-helpdesk",
            "assigned_operator_id": "operator-1",
            "status": "in_progress",
        },
    )
    assert assign_response.status_code == 200
    external_ticket_id = assign_response.json()["detail"]["external_ticket_id"]
    assert external_ticket_id

    slack_case_response = client.post(
        "/api/events/slack",
        json={
            "user_email": "mai@example.com",
            "user_name": "Mai",
            "text": "What is the work from home policy?",
            "channel_name": "employee-help",
        },
    )
    assert slack_case_response.status_code == 200
    slack_case_id = slack_case_response.json()["case_id"]

    assigned_list = client.get(
        "/api/cases",
        params={
            "assigned_operator_id": "operator-1",
            "has_external_ticket": "true",
            "active_only": "true",
        },
    )
    assert assigned_list.status_code == 200
    assigned_items = assigned_list.json()["items"]
    assert len(assigned_items) == 1
    assert assigned_items[0]["case_id"] == api_case_id

    search_by_ticket = client.get("/api/cases", params={"q": external_ticket_id})
    assert search_by_ticket.status_code == 200
    assert any(item["case_id"] == api_case_id for item in search_by_ticket.json()["items"])

    search_by_text = client.get("/api/cases", params={"q": "VPN"})
    assert search_by_text.status_code == 200
    assert any(item["case_id"] == api_case_id for item in search_by_text.json()["items"])

    slack_only = client.get("/api/cases", params={"channel": "slack", "q": "work from home"})
    assert slack_only.status_code == 200
    slack_items = slack_only.json()["items"]
    assert len(slack_items) == 1
    assert slack_items[0]["case_id"] == slack_case_id


def test_artifact_lifecycle_and_case_detail(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    case_id = create_response.json()["case_id"]

    issue_response = client.post(
        f"/api/cases/{case_id}/artifacts",
        json={
            "actor_id": "operator-1",
            "file_name": "vpn-log.txt",
            "content_type": "text/plain",
            "size_bytes": 128,
            "visibility": "internal",
            "artifact_type": "log_bundle",
        },
    )
    assert issue_response.status_code == 200
    artifact = issue_response.json()
    assert artifact["status"] == "pending_upload"
    assert artifact["upload"]["upload_url"]

    complete_response = client.post(
        f"/api/cases/{case_id}/artifacts/{artifact['artifact_id']}/complete",
        json={"actor_id": "operator-1", "checksum": "sha256:abc123"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "available"

    artifacts_response = client.get(f"/api/cases/{case_id}/artifacts")
    assert artifacts_response.status_code == 200
    artifacts = artifacts_response.json()["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["file_name"] == "vpn-log.txt"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert len(detail["artifacts"]) == 1
    assert detail["artifacts"][0]["artifact_type"] == "log_bundle"


def test_sla_scan_runs(client: TestClient) -> None:
    client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "What is the work from home policy?",
            "channel": "api",
        },
    )

    response = client.post("/api/ops/sla/scan")
    assert response.status_code == 200
    assert response.json()["scanned_count"] >= 0


def test_portal_case_submission_and_status(client: TestClient) -> None:
    create_response = client.post(
        "/api/portal/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me Jira access.",
            "priority": "normal",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    case_id = payload["case_id"]
    assert payload["workflow_type"] == "access_request"
    assert payload["current_stage"] in {"approval_wait", "execution", "closure", "post_execution"}

    status_response = client.get(f"/api/portal/cases/{case_id}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["case_id"] == case_id
    assert status_payload["requester_updates"]


def test_policy_qa_returns_citations(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "What is the work from home policy?",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    case_id = payload["case_id"]
    assert payload["workflow_type"] == "policy_qa"
    assert payload["status"] == "resolved"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    citations = detail["knowledge_citations"]
    assert citations
    assert any(citation["doc_id"].startswith("policy-wfh") for citation in citations)
    assert any("work from home" in citation["title"].lower() for citation in citations)


def test_access_request_approval_approved_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me Figma access for the design review this week.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    case_id = create_payload["case_id"]
    assert create_payload["workflow_type"] == "access_request"
    assert create_payload["status"] == "waiting_for_approval"
    assert create_payload["current_stage"] == "approval_wait"

    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()["approvals"]
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["decision"] == "pending"
    assert approval["approval_mode"] == "manager"
    assert approval["requested_action_ids"]

    decision_response = client.post(
        f"/api/approvals/{approval['approval_id']}/decision",
        json={
            "approved": True,
            "actor_id": "manager-1",
            "reason": "Approved for project work",
        },
    )
    assert decision_response.status_code == 200
    result = decision_response.json()["result"]
    assert result["status"] == "resolved"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert detail["status"] == "resolved"
    assert any(action["action_type"] == "grant_application_access" and action["status"] == "completed" for action in detail["actions"])
    assert any(item["approval_id"] == approval["approval_id"] and item["decision"] == "approved" for item in detail["approvals_detail"])


def test_access_request_approval_denied_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me GitHub Enterprise access.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    assert approvals_response.status_code == 200
    approval = approvals_response.json()["approvals"][0]

    decision_response = client.post(
        f"/api/approvals/{approval['approval_id']}/decision",
        json={
            "approved": False,
            "actor_id": "manager-1",
            "reason": "Not needed for current role",
        },
    )
    assert decision_response.status_code == 200
    result = decision_response.json()["result"]
    assert result["status"] == "cancelled"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert detail["status"] == "cancelled"
    assert any(action["status"] == "skipped" for action in detail["actions"])
    assert any(
        action["action_type"] == "grant_application_access" and action["error_code"] == "approval_denied"
        for action in detail["actions"]
    )
    assert any(item["approval_id"] == approval["approval_id"] and item["decision"] == "denied" for item in detail["approvals_detail"])


def test_access_request_owner_approval_for_analytics_dashboard(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me read access to the analytics dashboard.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]
    assert create_response.json()["status"] == "waiting_for_approval"

    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    assert approvals_response.status_code == 200
    approval = approvals_response.json()["approvals"][0]
    assert approval["approval_mode"] == "owner"
    assert approval["requested_from_actor_id"] == "owner-placeholder"

    decision_response = client.post(
        f"/api/approvals/{approval['approval_id']}/decision",
        json={"approved": True, "actor_id": "owner-1", "reason": "Approved by data owner"},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["result"]["status"] == "resolved"


def test_access_request_security_approval_for_production_admin(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me production admin access for incident response.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]
    assert create_response.json()["status"] == "waiting_for_approval"

    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()["approvals"]
    assert len(approvals) == 2
    manager_approval = next(approval for approval in approvals if approval["approval_mode"] == "manager")
    security_approval = next(approval for approval in approvals if approval["approval_mode"] == "security")
    assert manager_approval["approval_mode"] == "manager"
    assert manager_approval["requested_from_actor_id"] == "manager-placeholder"
    assert security_approval["approval_mode"] == "security"
    assert security_approval["requested_from_actor_id"] == "security-placeholder"
    assert security_approval["prerequisite_approval_ids"] == [manager_approval["approval_id"]]

    manager_decision = client.post(
        f"/api/approvals/{manager_approval['approval_id']}/decision",
        json={"approved": True, "actor_id": "manager-1", "reason": "Manager pre-approved"},
    )
    assert manager_decision.status_code == 200
    assert manager_decision.json()["result"]["status"] == "waiting_for_approval"

    security_decision = client.post(
        f"/api/approvals/{security_approval['approval_id']}/decision",
        json={"approved": True, "actor_id": "security-1", "reason": "Security approved"},
    )
    assert security_decision.status_code == 200
    assert security_decision.json()["result"]["status"] == "resolved"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert detail["extracted_entities"]["requested_access_risk_level"] == "critical"
    assert any(item["approval_id"] == manager_approval["approval_id"] and item["decision"] == "approved" for item in detail["approvals_detail"])
    assert any(item["approval_id"] == security_approval["approval_id"] and item["decision"] == "approved" for item in detail["approvals_detail"])


def test_approval_expiry_scan_cancels_stale_case(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me Figma access.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]
    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    approval = approvals_response.json()["approvals"][0]

    session = get_sessionmaker()()
    try:
        record = ApprovalRepository(session).get(approval["approval_id"])
        assert record is not None
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
    finally:
        session.close()

    expiry_response = client.post("/api/ops/approvals/expire")
    assert expiry_response.status_code == 200
    payload = expiry_response.json()
    assert payload["expired_count"] >= 1
    assert any(item["approval_id"] == approval["approval_id"] and item["expired"] is True for item in payload["items"])

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert detail["status"] == "cancelled"
    assert any(item["approval_id"] == approval["approval_id"] and item["decision"] == "expired" for item in detail["approvals_detail"])


def test_approval_reminder_scan_marks_pending_approval(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "Please grant me Figma access.",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]
    approvals_response = client.get(f"/api/cases/{case_id}/approvals")
    approval = approvals_response.json()["approvals"][0]

    session = get_sessionmaker()()
    try:
        record = ApprovalRepository(session).get(approval["approval_id"])
        assert record is not None
        record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        record.last_reminded_at = None
        session.commit()
    finally:
        session.close()

    reminder_response = client.post("/api/ops/approvals/remind")
    assert reminder_response.status_code == 200
    payload = reminder_response.json()
    assert payload["reminded_count"] >= 1
    assert any(item["approval_id"] == approval["approval_id"] and item["reminded"] is True for item in payload["items"])

    detail_response = client.get(f"/api/cases/{case_id}")
    detail = detail_response.json()["detail"]
    assert any(
        item["approval_id"] == approval["approval_id"] and item["last_reminded_at"] is not None
        for item in detail["approvals_detail"]
    )

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    assert any(log["event_type"] == "approval_reminder" for log in audit_response.json()["logs"])


def test_case_retry_recovers_failed_actions(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    executor = client.app.state.dispatcher.domain_tool_executor
    original_execute_action = executor.execute_action
    failure_state = {"failed_once": False}

    def flaky_execute_action(state, action):
        if action["action_type"] == "issue_password_reset" and not failure_state["failed_once"]:
            failure_state["failed_once"] = True
            return {
                "ok": False,
                "external_ref": None,
                "summary": "Simulated password reset connector failure.",
                "raw_result": {"reason": "temporary outage"},
                "retryable": True,
                "error_code": "simulated_password_reset_failure",
            }
        return original_execute_action(state, action)

    monkeypatch.setattr(executor, "execute_action", flaky_execute_action)

    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    case_id = payload["case_id"]
    assert payload["status"] == "partially_completed"

    detail_response = client.get(f"/api/cases/{case_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["detail"]
    assert any(
        action["action_type"] == "issue_password_reset" and action["status"] == "failed"
        for action in detail["actions"]
    )

    monkeypatch.setattr(executor, "execute_action", original_execute_action)

    retry_response = client.post(
        f"/api/cases/{case_id}/retry",
        json={
            "actor_id": "operator-1",
            "note": "Retry after connector recovery",
        },
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "resolved"

    detail_after_retry = client.get(f"/api/cases/{case_id}").json()["detail"]
    assert detail_after_retry["status"] == "resolved"
    assert any(
        action["action_type"] == "issue_password_reset" and action["status"] == "completed"
        for action in detail_after_retry["actions"]
    )

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    assert any(log["event_type"] == "case_retry" for log in audit_response.json()["logs"])


def test_case_retry_rejects_non_retryable_case(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "What is the work from home policy?",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    retry_response = client.post(
        f"/api/cases/{case_id}/retry",
        json={"actor_id": "operator-1"},
    )
    assert retry_response.status_code == 409


def test_case_audit_logs_include_ticket_sync_events(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    assign_response = client.post(
        f"/api/cases/{case_id}/assign",
        json={
            "actor_id": "operator-1",
            "assigned_team": "it-helpdesk",
            "assigned_operator_id": "operator-1",
            "status": "in_progress",
        },
    )
    assert assign_response.status_code == 200

    comment_response = client.post(
        f"/api/cases/{case_id}/comments",
        json={
            "actor_id": "operator-1",
            "visibility": "internal",
            "body": "Checked the VPN device posture.",
        },
    )
    assert comment_response.status_code == 200

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    logs = audit_response.json()["logs"]
    event_types = [log["event_type"] for log in logs]
    assert "case_run" in event_types
    assert "ticket_sync" in event_types
    assert "case_assignment" in event_types
    assert "ticket_assignment_sync" in event_types
    assert "case_comment" in event_types
    assert "ticket_comment_sync" in event_types


def test_slack_case_audit_logs_include_requester_notifications(client: TestClient) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "slack",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    requester_comment_response = client.post(
        f"/api/cases/{case_id}/comments",
        json={
            "actor_id": "operator-1",
            "visibility": "requester",
            "body": "Please try signing in again after the reset link arrives.",
        },
    )
    assert requester_comment_response.status_code == 200

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    logs = audit_response.json()["logs"]

    requester_notifications = [log for log in logs if log["event_type"] == "requester_notification"]
    assert len(requester_notifications) >= 2
    assert any(
        "Please try signing in again after the reset link arrives." in log["payload"].get("message", "")
        for log in requester_notifications
    )
    assert any(log["event_type"] == "ticket_comment_sync" for log in logs)


def test_ticket_sync_failures_are_audited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "api",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    executor = client.app.state.ticket_sync_service.domain_tool_executor
    original_execute = executor.execute_system_action

    def failing_execute_system_action(**kwargs):
        if kwargs["target_system"] == "ticketing" and kwargs["action_type"] in {"assign_ticket", "append_ticket_note"}:
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Simulated failure for {kwargs['action_type']}.",
                "raw_result": {"reason": "simulated failure"},
                "retryable": True,
                "error_code": "simulated_ticketing_failure",
            }
        return original_execute(**kwargs)

    monkeypatch.setattr(executor, "execute_system_action", failing_execute_system_action)

    assign_response = client.post(
        f"/api/cases/{case_id}/assign",
        json={
            "actor_id": "operator-1",
            "assigned_team": "it-helpdesk",
            "assigned_operator_id": "operator-1",
            "status": "in_progress",
        },
    )
    assert assign_response.status_code == 200

    comment_response = client.post(
        f"/api/cases/{case_id}/comments",
        json={
            "actor_id": "operator-1",
            "visibility": "internal",
            "body": "This comment should fail to sync outward.",
        },
    )
    assert comment_response.status_code == 200

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    logs = audit_response.json()["logs"]
    assert any(log["event_type"] == "ticket_assignment_sync_failed" for log in logs)
    assert any(log["event_type"] == "ticket_comment_sync_failed" for log in logs)
    assert any(log["payload"].get("error_code") == "simulated_ticketing_failure" for log in logs)


def test_requester_notification_failures_are_audited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    create_response = client.post(
        "/api/cases",
        json={
            "requester_email": "mai@example.com",
            "requester_name": "Mai",
            "message": "I cannot access VPN",
            "channel": "slack",
        },
    )
    assert create_response.status_code == 200
    case_id = create_response.json()["case_id"]

    executor = client.app.state.notification_service.domain_tool_executor
    original_execute = executor.execute_system_action

    def failing_execute_system_action(**kwargs):
        if kwargs["target_system"] == "slack" and kwargs["action_type"] == "post_requester_update":
            return {
                "ok": False,
                "external_ref": None,
                "summary": "Simulated Slack delivery failure.",
                "raw_result": {"reason": "simulated slack outage"},
                "retryable": True,
                "error_code": "simulated_slack_failure",
            }
        return original_execute(**kwargs)

    monkeypatch.setattr(executor, "execute_system_action", failing_execute_system_action)

    requester_comment_response = client.post(
        f"/api/cases/{case_id}/comments",
        json={
            "actor_id": "operator-1",
            "visibility": "requester",
            "body": "This requester update should fail to deliver to Slack.",
        },
    )
    assert requester_comment_response.status_code == 200

    audit_response = client.get(f"/api/cases/{case_id}/audit")
    assert audit_response.status_code == 200
    logs = audit_response.json()["logs"]
    failure_logs = [log for log in logs if log["event_type"] == "requester_notification_failed"]
    assert failure_logs
    assert any(log["payload"].get("error_code") == "simulated_slack_failure" for log in failure_logs)
    assert any(
        "This requester update should fail to deliver to Slack." in log["payload"].get("message", "")
        for log in failure_logs
    )
