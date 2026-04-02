from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..connectors import DomainToolExecutor
from ..policy import PolicyEngine
from .nodes import (
    await_approval,
    build_action_plan,
    build_evaluate_permissions_node,
    build_execute_actions_node,
    classify_intent,
    close_case,
    hydrate_case_context,
    ingest_case,
)
from .state import CaseState


def build_case_graph(
    *,
    policy_engine: PolicyEngine,
    domain_tool_executor: DomainToolExecutor,
    approval_timeout_hours: int = 24,
    checkpointer: Any | None = None,
):
    evaluate_permissions = build_evaluate_permissions_node(
        policy_engine,
        approval_timeout_hours=approval_timeout_hours,
    )
    execute_actions = build_execute_actions_node(domain_tool_executor)

    builder = StateGraph(CaseState)
    builder.add_node("ingest_case", ingest_case)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("hydrate_case_context", hydrate_case_context)
    builder.add_node("build_action_plan", build_action_plan)
    builder.add_node("evaluate_permissions", evaluate_permissions)
    builder.add_node("await_approval", await_approval)
    builder.add_node("execute_actions", execute_actions)
    builder.add_node("close_case", close_case)

    builder.add_edge(START, "ingest_case")
    builder.add_edge("ingest_case", "classify_intent")
    builder.add_edge("classify_intent", "hydrate_case_context")
    builder.add_edge("hydrate_case_context", "build_action_plan")
    builder.add_edge("build_action_plan", "evaluate_permissions")
    builder.add_edge("execute_actions", "close_case")
    builder.add_edge("close_case", END)

    return builder.compile(checkpointer=checkpointer)
