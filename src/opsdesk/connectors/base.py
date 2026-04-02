from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NotRequired, Protocol, TypedDict


class DomainToolRequest(TypedDict):
    case_id: str
    action_id: str
    idempotency_key: str
    actor_id: str
    tenant_id: str
    payload: dict[str, Any]
    dry_run: NotRequired[bool]
    metadata: NotRequired[dict[str, Any]]


class DomainToolResponse(TypedDict):
    ok: bool
    external_ref: str | None
    summary: str
    raw_result: dict[str, Any]
    retryable: bool
    error_code: NotRequired[str]


class ConnectorDescriptor(TypedDict):
    name: str
    supported_actions: list[str]


class ConnectorAdapter(Protocol):
    name: str
    supported_actions: tuple[str, ...]

    def invoke(self, action_type: str, request: DomainToolRequest) -> DomainToolResponse:
        ...

    def describe(self) -> ConnectorDescriptor:
        ...


@dataclass(frozen=True)
class ConnectorInvocationError(RuntimeError):
    target_system: str
    action_type: str
    detail: str

    def __str__(self) -> str:
        return f"{self.target_system}:{self.action_type}: {self.detail}"
