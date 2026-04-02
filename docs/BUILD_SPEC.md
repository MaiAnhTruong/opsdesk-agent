# OpsDesk Agent Build Spec

## 1. Goal

Build `opsdesk-agent` as an internal service desk agent for employee requests, starting with IT helpdesk and access management, then expanding to employee operations.

The production runtime should use:

- Python
- LangGraph `StateGraph` for orchestration
- Postgres for business data
- Postgres checkpointer for LangGraph persistence
- Deterministic policy and approval engine
- Domain tools for all external mutations

This document is the build-ready spec for the v1 system.

## 2. Product Scope

### v1 workflows

- Application access requests
- Onboarding checklist orchestration
- Password, SSO, VPN, and basic access issues
- Internal policy Q&A with case awareness

### v1 channels

- Slack
- Internal web portal
- API/webhook ingestion

### v1 systems

- Jira Service Management or ServiceNow
- Okta
- Google Workspace
- Slack
- Notion or Confluence

### v1 non-goals

- Fully autonomous HR and Finance operations
- Unbounded chatbot behavior
- Generic agent swarm without workflow controls
- Tool execution without policy gates

## 3. Core Design Decisions

### 3.1 Runtime model

- One employee request maps to one `case`.
- One `case` maps to one LangGraph `thread_id`.
- Each inbound event creates a new graph run against the same thread.
- The graph is the orchestration runtime, not the system of record.

### 3.2 Persistence model

- Business data lives in domain tables in Postgres.
- LangGraph checkpoints live in a separate Postgres schema or database.
- Attachments and exports live in object storage.
- Knowledge chunks and embeddings live in a retrieval store, not in graph state.

### 3.3 Control model

- LLMs may classify, summarize, extract, and draft plans.
- Policy engine decides allow, deny, approval-required, or escalate.
- Domain tool layer executes all side effects.
- Human approvals resume execution through LangGraph `interrupt`.

### 3.4 Mutation safety

- Every mutating external action must be wrapped in a LangGraph task.
- Every mutating action must support `idempotency_key`.
- Every mutating action must emit an audit payload.
- Every mutating action must declare whether approval is required before execution.

### 3.5 Multi-agent policy

- Default architecture is one top-level graph plus specialized subgraphs.
- Do not use a free-form supervisor agent as the main control plane.
- Use specialist subgraphs only where toolsets and policies differ materially.

## 4. Runtime Architecture

### 4.1 High-level components

- `API Gateway`
  - Receives Slack, portal, email, webhook, and scheduler events.
  - Authenticates caller, normalizes input, persists inbound event, starts graph run.
- `LangGraph Orchestrator`
  - Owns case graph, subgraphs, resume flow, and streaming progress.
- `Policy Engine`
  - Deterministic rule engine for access policy, approval policy, and escalation policy.
- `Connector Gateway`
  - Provides domain-specific tools backed by SaaS and internal APIs.
- `Knowledge Service`
  - Retrieves policy snippets and operational guidance from indexed docs.
- `Scheduler Worker`
  - Triggers SLA reminders, approval nudges, escalations, and retries.
- `Notification Service`
  - Sends Slack, email, or portal updates.
- `Observability Stack`
  - LangSmith traces, OpenTelemetry, metrics, audit logs, and error reporting.

### 4.2 Request lifecycle

1. Intake event arrives from Slack, portal, or webhook.
2. API normalizes request and creates `case` plus `case_event`.
3. Orchestrator resumes or creates LangGraph thread for the case.
4. Graph classifies intent and hydrates context.
5. Graph routes to workflow subgraph.
6. Read-only investigation tasks run in parallel.
7. Planner builds action plan.
8. Policy engine evaluates each action.
9. If approvals or missing data are needed, graph interrupts.
10. After resume, graph executes approved mutations serially.
11. Ticket and requester updates are written.
12. Scheduler tracks SLA and follow-up until closure.

## 5. LangGraph Design

### 5.1 Top-level graph

`case_graph`

- `ingest_case`
- `normalize_request`
- `classify_intent`
- `hydrate_case_context`
- `route_workflow`
- `update_case_summary`
- `finalize_turn`

### 5.2 Workflow subgraphs

- `access_request_subgraph`
- `onboarding_subgraph`
- `auth_issue_subgraph`
- `policy_qa_subgraph`
- `offboarding_subgraph` as planned v2

### 5.3 Shared node pattern

Each workflow subgraph should use the same node shape:

- `gather_facts_parallel`
- `retrieve_policy_and_templates`
- `build_action_plan`
- `evaluate_permissions`
- `interrupt_for_missing_info`
- `interrupt_for_approval`
- `execute_actions`
- `post_execution_reconcile`
- `update_ticket_and_notify`
- `schedule_follow_up_or_close`

### 5.4 Parallel versus serial execution

Parallel nodes:

- license availability check
- inventory check
- user profile lookup
- role template lookup
- current access lookup
- policy retrieval

Serial nodes:

- create account
- assign group
- grant app access
- revoke access
- update ticket status
- close case

### 5.5 Interrupt rules

Use `interrupt()` when:

- requester input is missing
- manager approval is required
- data owner approval is required
- an operator must review a high-risk plan
- policy conflict needs human decision

Important implementation rule:

- Nodes that call `interrupt()` can be re-run from the start when resumed.
- Therefore any side effect before `interrupt()` must be idempotent or moved into a task after the resume point.

## 6. Proposed Source Layout

Keep the current `src/` package root, but migrate from mirror placeholders to product modules.

```text
src/
  main.py
  config/
    settings.py
  api/
    app.py
    deps.py
    routes/
      cases.py
      slack.py
      portal.py
      approvals.py
      health.py
  runtime/
    graph.py
    dispatcher.py
    state.py
    reducers.py
    interrupts.py
    streaming.py
    nodes/
      intake.py
      classify.py
      hydrate.py
      plan.py
      permissions.py
      execute.py
      close.py
    subgraphs/
      access_request.py
      onboarding.py
      auth_issue.py
      policy_qa.py
  domain/
    models.py
    enums.py
    repositories/
      cases.py
      approvals.py
      actions.py
      policies.py
      knowledge.py
    services/
      case_service.py
      approval_service.py
      sla_service.py
      audit_service.py
  policy/
    engine.py
    rules.py
    matrix.py
  connectors/
    base.py
    registry.py
    domain_tools.py
    adapters/
      jira.py
      servicenow.py
      okta.py
      google_workspace.py
      slack.py
      notion.py
  knowledge/
    ingest.py
    retriever.py
    citations.py
  workers/
    scheduler.py
    retries.py
    escalation.py
  storage/
    db.py
    checkpoints.py
    objects.py
  observability/
    tracing.py
    metrics.py
    logging.py
  schemas/
    api.py
    events.py
    state.py
tests/
  unit/
  integration/
  workflow/
```

## 7. Module-by-Module Spec

### `src/main.py`

- Boot FastAPI app and worker entrypoints.
- Expose local dev CLI for replay, dry-run, and seed operations.

### `src/config/settings.py`

- Central configuration.
- Environment-based settings for DB, LangSmith, Slack, Okta, Google, retrieval, and secrets.

### `src/api/app.py`

- FastAPI app factory.
- Middleware for auth, request ID, tracing, and error mapping.

### `src/api/routes/cases.py`

- Create case manually.
- Get case detail.
- List case timeline.
- Resume case with operator input.

### `src/api/routes/slack.py`

- Slack slash command and event handlers.
- Signature verification.
- Channel mapping to tenant and workspace.

### `src/api/routes/portal.py`

- Internal portal endpoints.
- Case submit, case comment, attachment upload token, status polling.

### `src/api/routes/approvals.py`

- Approval action endpoints.
- Approve, deny, request changes.
- Resume blocked graph thread after approval update.

### `src/runtime/graph.py`

- Compile top-level LangGraph case graph.
- Attach checkpointer and stores.
- Register subgraphs.

### `src/runtime/dispatcher.py`

- Map inbound event type to graph run.
- Enforce one active case run per case at a time.
- Handle retries and duplicate event suppression.

### `src/runtime/state.py`

- Canonical LangGraph state types.
- TypedDict or Pydantic models used by graph nodes.

### `src/runtime/reducers.py`

- Merge strategy for plan steps, actions, approvals, citations, and messages.
- Must avoid accidental overwrite during parallel branches.

### `src/runtime/interrupts.py`

- Standard interrupt payload builders for:
  - missing requester data
  - approval request
  - operator review
  - escalation handoff

### `src/runtime/nodes/intake.py`

- Parse inbound message.
- Create or load case.
- Normalize case channel metadata.

### `src/runtime/nodes/classify.py`

- Intent classification for:
  - access request
  - onboarding
  - auth issue
  - policy question
  - unknown or operator triage

### `src/runtime/nodes/hydrate.py`

- Load requester profile, employee profile, org metadata, ticket metadata, open approvals, current SLA state.

### `src/runtime/nodes/plan.py`

- Build action plan from structured facts.
- Generate human-readable execution summary.
- Never execute side effects directly.

### `src/runtime/nodes/permissions.py`

- Call policy engine on each proposed action.
- Mark action as `auto_allow`, `requires_approval`, `deny`, or `escalate`.

### `src/runtime/nodes/execute.py`

- Execute approved actions through domain tool layer.
- Persist action results and partial failures.

### `src/runtime/nodes/close.py`

- Write ticket resolution summary.
- Notify requester.
- Transition to `resolved` or `waiting` status.

### `src/runtime/subgraphs/access_request.py`

- Handles app access, folder access, shared drive access, role template lookup, and license grants.

### `src/runtime/subgraphs/onboarding.py`

- Handles starter bundle planning for identity, apps, devices, and checklist tasks.

### `src/runtime/subgraphs/auth_issue.py`

- Handles password reset, SSO issue, VPN issue, and simple self-remediation playbooks.

### `src/runtime/subgraphs/policy_qa.py`

- Answers policy questions with citations.
- Can create follow-up ticket if action is required.

### `src/domain/models.py`

- SQLAlchemy models for all business entities.

### `src/domain/enums.py`

- Shared enums for status, priority, workflow type, action type, approval type, and risk class.

### `src/domain/repositories/*`

- Thin persistence layer for cases, approvals, actions, and policies.

### `src/domain/services/case_service.py`

- Case orchestration helper outside LangGraph.
- Create case, append event, compute human-readable status.

### `src/domain/services/approval_service.py`

- Create approval request objects.
- Verify approver authority.
- Resume case thread after decision.

### `src/domain/services/sla_service.py`

- Start and stop SLA timers.
- Compute breach windows.
- Trigger escalations.

### `src/domain/services/audit_service.py`

- Write immutable audit records for tool calls, approvals, and policy decisions.

### `src/policy/engine.py`

- Deterministic evaluator.
- Input: `ActionSpec`, requester context, subject context, policy context.
- Output: `PolicyDecision`.

### `src/policy/rules.py`

- Rule definitions such as:
  - access within role template
  - self-service auth reset
  - high-risk data access
  - onboarding bundle approval rules
  - offboarding cutover rules

### `src/policy/matrix.py`

- Policy classification matrix and risk tiers.

### `src/connectors/base.py`

- Base connector interfaces.
- Retry, timeout, auth, idempotency, and normalized error model.

### `src/connectors/registry.py`

- Registry of enabled tenant connectors and credentials.

### `src/connectors/domain_tools.py`

- Domain-safe tools exposed to LangGraph nodes.
- Example tools:
  - `lookup_employee_profile`
  - `lookup_current_access`
  - `lookup_role_template`
  - `check_license_capacity`
  - `grant_application_access`
  - `create_onboarding_bundle`
  - `issue_password_reset`
  - `update_ticket`
  - `post_slack_update`

### `src/connectors/adapters/*`

- SaaS-specific client adapters.
- Must not contain orchestration logic.

### `src/knowledge/ingest.py`

- Sync Notion or Confluence pages and policy docs.
- Chunk, embed, and version documents.

### `src/knowledge/retriever.py`

- Retrieval with citation support.
- Filter by tenant, document type, and policy version.

### `src/workers/scheduler.py`

- Processes delayed jobs:
  - approval reminder
  - SLA breach warning
  - escalation trigger
  - retry execution

### `src/storage/db.py`

- Business DB engine and session management.

### `src/storage/checkpoints.py`

- LangGraph checkpointer configuration.
- Separate schema from business tables.

### `src/observability/*`

- LangSmith trace config
- OpenTelemetry setup
- Prometheus counters and histograms
- Structured JSON logging

## 8. Domain Data Model

### 8.1 Core tables

- `cases`
- `case_events`
- `case_comments`
- `case_artifacts`
- `case_actions`
- `approvals`
- `approval_targets`
- `policy_rules`
- `role_templates`
- `knowledge_documents`
- `knowledge_chunks`
- `sla_policies`
- `sla_timers`
- `audit_logs`
- `connector_credentials`

### 8.2 `cases` table

Required columns:

- `id`
- `tenant_id`
- `external_ticket_id`
- `channel`
- `workflow_type`
- `intent`
- `priority`
- `status`
- `current_stage`
- `requester_id`
- `subject_employee_id`
- `title`
- `summary`
- `requested_start_at`
- `assigned_team`
- `assigned_operator_id`
- `created_at`
- `updated_at`
- `resolved_at`
- `closed_at`

### 8.3 `case_actions` table

Required columns:

- `id`
- `case_id`
- `sequence_no`
- `action_type`
- `target_system`
- `target_resource`
- `risk_level`
- `approval_mode`
- `status`
- `idempotency_key`
- `request_payload`
- `result_payload`
- `error_code`
- `error_detail`
- `started_at`
- `completed_at`

### 8.4 `approvals` table

Required columns:

- `id`
- `case_id`
- `approval_type`
- `requested_from_actor_id`
- `requested_by_actor_id`
- `decision`
- `reason`
- `expires_at`
- `decided_at`
- `resume_token`

## 9. State Schema

Use a typed graph state object that remains small, durable, and explicit.

```python
from typing import Any, Literal, NotRequired, TypedDict


class ActorRef(TypedDict):
    actor_id: str
    actor_type: Literal["employee", "manager", "operator", "system"]
    email: str
    display_name: str


class PolicyCitation(TypedDict):
    doc_id: str
    chunk_id: str
    title: str
    url: str
    snippet: str


class PlanStep(TypedDict):
    step_id: str
    title: str
    action_type: str
    target_system: str
    mode: Literal["read", "write"]
    rationale: str


class ActionSpec(TypedDict):
    action_id: str
    action_type: str
    target_system: str
    target_resource: str
    mode: Literal["read", "write"]
    risk_level: Literal["low", "medium", "high", "critical"]
    approval_mode: Literal["auto", "manager", "owner", "operator", "security", "deny"]
    requires_human: bool
    idempotency_key: str
    payload: dict[str, Any]


class ActionResult(TypedDict):
    action_id: str
    status: Literal["pending", "completed", "failed", "skipped"]
    external_ref: NotRequired[str]
    summary: str
    error_code: NotRequired[str]


class ApprovalState(TypedDict):
    approval_id: str
    status: Literal["pending", "approved", "denied", "expired"]
    requested_from: ActorRef
    decision_reason: NotRequired[str]


class SlaState(TypedDict):
    first_response_due_at: str | None
    resolution_due_at: str | None
    breach_risk: Literal["low", "medium", "high"]
    last_escalated_at: str | None


class CaseState(TypedDict):
    case_id: str
    tenant_id: str
    thread_id: str
    channel: Literal["slack", "portal", "email", "api", "scheduler"]
    workflow_type: Literal["access_request", "onboarding", "auth_issue", "policy_qa", "unknown"]
    intent: str
    priority: Literal["low", "normal", "high", "urgent"]
    status: str
    current_stage: str
    requester: ActorRef
    subject_employee: NotRequired[ActorRef]
    latest_user_message: str
    normalized_request: dict[str, Any]
    extracted_entities: dict[str, Any]
    missing_fields: list[str]
    policy_citations: list[PolicyCitation]
    knowledge_citations: list[PolicyCitation]
    plan_steps: list[PlanStep]
    pending_actions: list[ActionSpec]
    action_results: list[ActionResult]
    approvals: list[ApprovalState]
    requester_updates: list[str]
    operator_notes: list[str]
    sla: SlaState
    last_error: NotRequired[str]
```

### State management rules

- Keep raw documents out of graph state.
- Keep binary attachments out of graph state.
- Keep only stable references, extracted facts, plan, approvals, and action results in graph state.
- Persist full timeline and artifacts in domain tables.

## 10. Ticket State Machine

Separate business status from runtime stage.

### 10.1 Business status

- `new`
- `triaged`
- `waiting_for_requester`
- `waiting_for_approval`
- `planned`
- `in_progress`
- `partially_completed`
- `resolved`
- `closed`
- `failed`
- `cancelled`

### 10.2 Runtime stage

- `intake`
- `classification`
- `context_hydration`
- `planning`
- `permission_evaluation`
- `approval_wait`
- `execution`
- `post_execution`
- `follow_up`
- `closure`

### 10.3 State transitions

| From | Event | To | Owner |
| --- | --- | --- | --- |
| `new` | request normalized | `triaged` | graph |
| `triaged` | missing requester info | `waiting_for_requester` | graph |
| `triaged` | plan created without blockers | `planned` | graph |
| `planned` | approval required | `waiting_for_approval` | graph |
| `planned` | no approval required | `in_progress` | graph |
| `waiting_for_requester` | requester replied | `triaged` | graph |
| `waiting_for_approval` | approval granted | `in_progress` | graph |
| `waiting_for_approval` | approval denied | `cancelled` or `planned` | graph/operator |
| `in_progress` | some actions succeed and some blocked | `partially_completed` | graph |
| `in_progress` | all actions succeed | `resolved` | graph |
| `partially_completed` | remaining actions succeed | `resolved` | graph |
| `resolved` | resolution confirmed or timeout met | `closed` | scheduler/operator |
| any active status | unrecoverable execution error | `failed` | graph/operator |

### 10.4 SLA behavior by status

- `new`, `triaged`, `planned`, `in_progress`: resolution SLA clock active
- `waiting_for_requester`: requester-pending clock pauses resolution SLA
- `waiting_for_approval`: approval-pending clock may pause or branch by tenant policy
- `resolved`: closure timer active
- `closed`, `cancelled`, `failed`: no active SLA timer

## 11. Permission Matrix

This matrix is enforced by the policy engine, not by prompt text.

| Action class | Examples | Default mode | Approver | Execution rule | Audit requirement |
| --- | --- | --- | --- | --- | --- |
| Knowledge read | retrieve policy docs, role template docs | auto | none | always allowed for authenticated case processing | log query and citations |
| Identity read | lookup user, groups, licenses, inventory | auto | none | allowed for service desk scope | log connector and target |
| Ticket update | append internal note, status update, summary | auto | none | allowed for system actor | log before and after |
| Self-service auth remediation | issue password reset link, resend MFA enrollment | auto | none | allowed only if requester identity is verified and subject equals requester | log actor match and policy version |
| Standard access within template | grant app license or group from approved role template | approval-required | manager or role owner | require manager approval unless tenant policy allows auto for pre-approved bundles | log template version and approval |
| Access outside template | analytics, finance, admin, production data | approval-required | data owner plus manager | always block until approval chain completed | log risk class and approvers |
| Onboarding bundle | create standard bundle for approved job role | approval-required | hiring manager | allow only after manager approval and start date validation | log role template and execution results |
| Offboarding deprovisioning | revoke access, suspend account | approval-required | HR or manager based on policy | execute on effective date with strict sequencing | full audit trail required |
| HR or Finance data mutation | expense, payroll, leave balance | escalate | HR or Finance operator | not in v1 automation scope | log escalation only |
| Policy override | action contrary to policy | deny by default | security or senior operator | never auto-execute | log denial or override chain |
| External comms | email vendor or outside user | approval-required | operator | not allowed for graph-only execution in v1 | log draft and approval |

### 11.1 Risk tiers

- `low`: read-only lookups, ticket metadata changes
- `medium`: verified self-service remediation
- `high`: standard access writes, onboarding writes
- `critical`: privileged access, finance data, security-sensitive changes, offboarding

### 11.2 Approval routing rules

- Requester approval is never sufficient for privileged writes.
- Manager approval covers standard role-based access.
- Data owner approval covers data-domain access.
- Security approval covers exceptions, admin access, and policy overrides.
- Operator approval is required when automation confidence is too low.

## 12. Domain Tool Contract

All tools exposed to the graph must use a domain-safe interface.

```python
class DomainToolRequest(TypedDict):
    case_id: str
    action_id: str
    idempotency_key: str
    actor_id: str
    tenant_id: str
    payload: dict[str, Any]


class DomainToolResponse(TypedDict):
    ok: bool
    external_ref: str | None
    summary: str
    raw_result: dict[str, Any]
    retryable: bool
```

Rules:

- No raw SaaS SDK object should be passed into graph state.
- Tool errors must be normalized.
- Tools must support dry-run mode for planning and approval preview.
- Tools must emit metrics for latency, failure, and retries.

## 13. API Contract

### `POST /api/cases`

- Create case from portal or internal system.

### `POST /api/events/slack`

- Slack event intake.

### `POST /api/cases/{case_id}/resume`

- Resume with requester or operator input.

### `POST /api/approvals/{approval_id}/decision`

- Approve or deny pending action bundle.

### `GET /api/cases/{case_id}`

- Case detail, status, plan, approvals, action results, and timeline.

### `GET /api/cases/{case_id}/stream`

- SSE or websocket stream for case progress.

## 14. Observability and Audit

Required telemetry:

- case creation count
- case resolution time
- first response time
- approval turnaround time
- auto-resolve rate
- partial automation rate
- connector latency by system
- graph node failure rate
- interrupt count by reason

Required traces:

- one top-level trace per case run
- child spans for graph nodes
- child spans for connector calls

Required audit events:

- case created
- policy evaluated
- approval requested
- approval decided
- tool executed
- tool failed
- ticket updated
- case resolved

## 15. Testing Strategy

### Unit tests

- policy engine
- reducers
- state transitions
- tool request validation
- connector error normalization

### Integration tests

- Slack intake to case creation
- approval interrupt and resume
- access request planning with mocked connectors
- onboarding execution with idempotent retries

### Workflow tests

- end-to-end graph replay for each v1 workflow
- partial failure recovery
- timeout and escalation
- duplicate webhook suppression

### Non-functional tests

- checkpoint recovery after worker restart
- replay determinism for interrupted flows
- PII redaction in logs and traces

## 16. Security Requirements

- SSO-protected operator UI and portal
- Secrets stored in managed secret store
- Tenant-level connector credentials isolation
- PII minimization in prompts and traces
- Redaction before external tracing where required
- Immutable audit log for all write actions
- Least-privilege OAuth scopes for all connectors

## 17. 4-Week Delivery Roadmap

### Week 1: Foundations

Deliverables:

- Replace placeholder workspace focus with product source layout
- Postgres business schema and LangGraph checkpoint schema
- FastAPI app skeleton
- Case creation API
- Slack intake endpoint
- Top-level LangGraph graph skeleton
- Core `CaseState` models
- LangSmith and OpenTelemetry wiring

Acceptance criteria:

- Can create a case from API or Slack event
- Can start a graph run and persist checkpoints
- Can read case state and timeline from API

### Week 2: Planning and approvals

Deliverables:

- Intent classification node
- Context hydration node
- Access request subgraph
- Auth issue subgraph
- Knowledge retrieval service with citations
- Policy engine v1
- Approval creation and interrupt/resume flow
- Portal or API endpoint for approval decisions

Acceptance criteria:

- Access request can be triaged, planned, and paused for approval
- Auth issue can produce self-service plan or operator escalation
- Policy Q&A returns citation-backed answer

### Week 3: Execution and SLA

Deliverables:

- Okta adapter
- Google Workspace adapter
- Jira or ServiceNow adapter
- Domain tool registry
- Serial action executor with idempotency keys
- Ticket updates and requester notifications
- SLA timers and scheduler worker
- Partial failure handling

Acceptance criteria:

- Approved access request can execute writes safely
- Case state shows action results and audit trail
- SLA reminders and escalations fire from scheduler

### Week 4: Hardening and pilot readiness

Deliverables:

- Onboarding subgraph
- Error recovery and replay tooling
- Operator notes and manual handoff flow
- Metrics dashboards
- Audit export endpoint
- Workflow and load tests
- Pilot deployment docs and runbooks

Acceptance criteria:

- Three v1 workflows pass end-to-end tests
- Interrupt/resume survives restarts
- Dashboard shows core operational metrics
- Pilot tenant can run limited production trial

## 18. Build Order Inside the Repo

Recommended implementation order:

1. `storage`, `domain.models`, `domain.repositories`
2. `config`, `api.app`, `api.routes.health`
3. `runtime.state`, `runtime.graph`, `runtime.dispatcher`
4. `policy.engine`, `policy.matrix`
5. `connectors.base`, `connectors.registry`, `connectors.domain_tools`
6. `runtime.nodes` and `access_request_subgraph`
7. `api.routes.approvals`, `workers.scheduler`
8. `auth_issue_subgraph`, `policy_qa_subgraph`
9. `onboarding_subgraph`
10. observability, audit export, hardening

## 19. Immediate Next Step

After adopting this spec, the next implementation artifact should be:

- repository restructure under `src/`
- SQLAlchemy models for `cases`, `case_actions`, `approvals`, and `audit_logs`
- `CaseState` type definitions
- top-level `case_graph` with stub nodes
- FastAPI intake and resume endpoints

That is the minimum viable spine for the product.

## 20. References

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph
- Durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- Human in the loop: https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- Persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- Streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- Use threads: https://docs.langchain.com/langgraph-platform/use-threads
- Deploy standalone server: https://docs.langchain.com/langgraph-platform/deploy-standalone-server
