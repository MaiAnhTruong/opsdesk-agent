from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.func import task

from .base import ConnectorInvocationError, DomainToolRequest, DomainToolResponse
from .registry import ConnectorRegistry, build_default_connector_registry


@dataclass
class DomainToolExecutor:
    registry: ConnectorRegistry

    def execute_action(self, state: dict[str, Any], action: dict[str, Any]) -> DomainToolResponse:
        request: DomainToolRequest = {
            "case_id": str(state["case_id"]),
            "action_id": str(action["action_id"]),
            "idempotency_key": str(action["idempotency_key"]),
            "actor_id": str(state.get("requester", {}).get("actor_id", "system")),
            "tenant_id": str(state.get("tenant_id", "default")),
            "payload": dict(action.get("payload", {})),
            "metadata": {
                "workflow_type": state.get("workflow_type"),
                "case_status": state.get("status"),
                "channel": state.get("channel"),
            },
        }
        target_system = str(action["target_system"])
        action_type = str(action["action_type"])
        try:
            return self.registry.execute(
                target_system=target_system,
                action_type=action_type,
                request=request,
            )
        except ConnectorInvocationError as exc:
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Connector routing failed for {target_system}:{action_type}.",
                "raw_result": {"error": str(exc)},
                "retryable": False,
                "error_code": "connector_routing_failed",
            }

    def execute_system_action(
        self,
        *,
        case_id: str,
        tenant_id: str,
        actor_id: str,
        target_system: str,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        dry_run: bool = False,
    ) -> DomainToolResponse:
        request: DomainToolRequest = {
            "case_id": case_id,
            "action_id": f"{target_system}:{action_type}:{case_id}",
            "idempotency_key": idempotency_key,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "payload": payload,
            "dry_run": dry_run,
            "metadata": {"source": "system"},
        }
        try:
            return self.registry.execute(
                target_system=target_system,
                action_type=action_type,
                request=request,
            )
        except ConnectorInvocationError as exc:
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Connector routing failed for {target_system}:{action_type}.",
                "raw_result": {"error": str(exc)},
                "retryable": False,
                "error_code": "connector_routing_failed",
            }

    def build_task(self):
        executor = self

        @task
        def execute_domain_action(state: dict[str, Any], action: dict[str, Any]) -> DomainToolResponse:
            return executor.execute_action(state, action)

        return execute_domain_action


def build_default_domain_tool_executor(registry: ConnectorRegistry | None = None) -> DomainToolExecutor:
    return DomainToolExecutor(registry=registry or build_default_connector_registry())
