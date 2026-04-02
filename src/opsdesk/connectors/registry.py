from __future__ import annotations

from dataclasses import dataclass, field

from .adapters import MockHrisAdapter, MockKnowledgeAdapter, MockLicenseAdapter, MockMdmAdapter, MockOktaAdapter, MockSlackAdapter, MockTicketingAdapter
from .base import ConnectorAdapter, ConnectorDescriptor, ConnectorInvocationError, DomainToolRequest, DomainToolResponse


@dataclass
class ConnectorRegistry:
    adapters: dict[str, ConnectorAdapter] = field(default_factory=dict)

    def register(self, adapter: ConnectorAdapter) -> None:
        self.adapters[adapter.name] = adapter

    def get(self, target_system: str) -> ConnectorAdapter:
        adapter = self.adapters.get(target_system)
        if adapter is None:
            raise ConnectorInvocationError(
                target_system=target_system,
                action_type="unknown",
                detail="No adapter is registered for the target system.",
            )
        return adapter

    def list_connectors(self) -> list[ConnectorDescriptor]:
        return [
            self.describe_connector(name)
            for name in sorted(self.adapters)
        ]

    def describe_connector(self, target_system: str) -> ConnectorDescriptor:
        adapter = self.get(target_system)
        return adapter.describe()

    def supports(self, *, target_system: str, action_type: str) -> bool:
        adapter = self.get(target_system)
        return action_type in adapter.supported_actions

    def execute(self, *, target_system: str, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        adapter = self.get(target_system)
        if action_type not in adapter.supported_actions:
            raise ConnectorInvocationError(
                target_system=target_system,
                action_type=action_type,
                detail="Adapter does not support the requested action.",
            )
        try:
            response = adapter.invoke(action_type, request)
        except ConnectorInvocationError:
            raise
        except Exception as exc:
            return {
                "ok": False,
                "external_ref": None,
                "summary": f"Connector execution failed for {target_system}:{action_type}.",
                "raw_result": {"error": str(exc)},
                "retryable": True,
                "error_code": "connector_exception",
            }
        if not response["ok"] and not response["retryable"]:
            return response
        return response


def build_default_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(MockOktaAdapter())
    registry.register(MockLicenseAdapter())
    registry.register(MockKnowledgeAdapter())
    registry.register(MockHrisAdapter())
    registry.register(MockMdmAdapter())
    registry.register(MockSlackAdapter())
    registry.register(MockTicketingAdapter())
    return registry
