# opsdesk-agent

AI service desk agent for internal employee requests, access workflows, and IT operations.

Build spec: [docs/BUILD_SPEC.md](docs/BUILD_SPEC.md)
Testing guide: [docs/TESTING.md](docs/TESTING.md)

Initial product scaffold lives under `src/opsdesk/`.

Dependencies for the new runtime are listed in `requirements-opsdesk.txt`.
Development and test dependencies are listed in `requirements-dev.txt`.

Intended app entrypoint:

`python -m src.opsdesk.main`

Environment setup:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If your shell is running inside `conda base`, prefer an explicit CPython interpreter to avoid mixing Python runtimes inside `.venv`:

```powershell
C:\Users\Mai Anh Truong\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable); print(sys.version)"
```

Run the API locally:

```powershell
python -m src.opsdesk.main
```

Run the automated tests:

```powershell
python -m pytest tests/test_opsdesk_api.py -q
```

Current automated coverage:

- health check and connector inventory
- case creation and operator assignment/comment flow
- inbox filtering and search by channel, assignment, active state, and external ticket
- access request approval approve/deny flow
- application-aware access request policy for manager, owner, and security approvals
- multi-step approval chain for privileged access and approval expiry scan
- approval reminder scan for pending approvals nearing expiry
- retry path for failed and partially completed execution cases
- case audit trail for ticket sync and requester notifications
- connector failure audit trail for ticket sync and Slack delivery failures
- artifact issue and completion flow
- SLA scan endpoint

Current note:

- LangGraph runtime, policy engine, DB persistence, and mock connector-backed domain tools are scaffolded.
- External system adapters are still mock implementations and need tenant-specific wiring.
- Case detail, timeline, approval decision, and ticket sync loops are now scaffolded through the API and domain services.
