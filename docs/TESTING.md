# Testing

This project now has a minimal repeatable test path for the new `src/opsdesk/` runtime.

## Environment

Use Python `3.11+`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If you are inside `conda base` on Windows, do not rely on the bare `python` command unless it already points at the interpreter you want. On this machine, the safe path is:

```powershell
C:\Users\Mai Anh Truong\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable); print(sys.version)"
```

That version check should print `.venv\Scripts\python.exe` and a `3.11.x` runtime.

If you want to run the app manually:

```powershell
python -m src.opsdesk.main
```

## Automated Tests

Current API tests live in `tests/test_opsdesk_api.py`.

Run them with:

```powershell
python -m pytest tests/test_opsdesk_api.py -q
```

If `pytest` tries to autoload unrelated third-party plugins in your local environment, you can force a clean run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_opsdesk_api.py -q
```

What they cover today:

- `test_health_and_connector_inventory`
  verifies app boot, `/api/healthz`, and connector registry exposure
- `test_case_operator_flow`
  verifies case creation, assignment, operator comment, and case comment listing
- `test_case_list_supports_inbox_filters_and_search`
  verifies inbox filtering by assignment, active state, channel, and search by text or external ticket id
- `test_access_request_approval_approved_flow`
  verifies an `access_request` pauses for approval, resumes, and executes after approval
- `test_access_request_approval_denied_flow`
  verifies a denied approval cancels the case and marks actions as skipped
- `test_access_request_owner_approval_for_analytics_dashboard`
  verifies sensitive analytics access routes to owner approval
- `test_access_request_security_approval_for_production_admin`
  verifies privileged production access routes through a manager then security approval chain
- `test_approval_expiry_scan_cancels_stale_case`
  verifies expired pending approvals are cancelled by the approval expiry scan
- `test_approval_reminder_scan_marks_pending_approval`
  verifies near-expiry approvals are reminded and recorded in audit logs
- `test_case_retry_recovers_failed_actions`
  verifies an operator can retry failed execution actions and recover the case
- `test_case_retry_rejects_non_retryable_case`
  verifies resolved cases cannot be retried through the retry endpoint
- `test_case_audit_logs_include_ticket_sync_events`
  verifies operator actions produce auditable ticket sync events
- `test_slack_case_audit_logs_include_requester_notifications`
  verifies Slack-originated cases produce requester notification audit entries
- `test_ticket_sync_failures_are_audited`
  verifies outbound ticket sync failures are recorded in audit logs
- `test_requester_notification_failures_are_audited`
  verifies Slack delivery failures are recorded in audit logs
- `test_artifact_lifecycle_and_case_detail`
  verifies artifact upload issuance, artifact completion, artifact listing, and case detail projection
- `test_sla_scan_runs`
  verifies the SLA scan worker endpoint can execute against live case data

## Manual Smoke Checks

After booting the API, these flows are worth checking manually:

- create an `auth_issue` case and verify it resolves through the graph
- create an `access_request` case and verify approval gating behavior
- submit a Slack intake payload through `/api/slack/events`
- add an operator comment and confirm requester-visible comments trigger notification routing
- create an artifact and confirm the external ticket sync note is emitted

## Next Tests To Add

The highest-value gaps are:

- failure-path tests for connector errors and graph exceptions
- audit trail export or pagination beyond the basic per-case listing
- richer inbox sorting or saved views for operators
- approval escalation based on reminder count or manual approvals SLA

## Troubleshooting

### `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`

This usually means the virtual environment is using one Python runtime, but a compiled package wheel from another runtime was installed into it.

Example of a broken environment:

- `.venv\pyvenv.cfg` says the environment was created from `D:\miniconda3\python.exe`
- `site-packages\pydantic_core\_pydantic_core.cp311-win_amd64.pyd` shows a CPython 3.11 wheel

Fix it by recreating the environment cleanly:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
C:\Users\Mai Anh Truong\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_opsdesk_api.py -q
```
