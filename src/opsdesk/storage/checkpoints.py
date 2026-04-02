from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings


@dataclass
class CheckpointerHandle:
    saver: Any
    kind: str
    _closer: Any | None = None

    def close(self) -> None:
        if self._closer is not None:
            self._closer(None, None, None)
            self._closer = None


def build_checkpointer(settings: Settings) -> CheckpointerHandle:
    """Build a LangGraph checkpointer handle.

    For the first implementation step we default to the in-memory saver for local
    development. A Postgres-backed saver should be wired in at app lifespan time
    once deployment dependencies are present.
    """

    if settings.langgraph_checkpointer_dsn:
        from langgraph.checkpoint.postgres import PostgresSaver

        context_manager = PostgresSaver.from_conn_string(settings.langgraph_checkpointer_dsn)
        saver = context_manager.__enter__()
        saver.setup()
        return CheckpointerHandle(
            saver=saver,
            kind="postgres",
            _closer=context_manager.__exit__,
        )

    from langgraph.checkpoint.memory import InMemorySaver

    return CheckpointerHandle(saver=InMemorySaver(), kind="memory")
