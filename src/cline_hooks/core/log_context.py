"""Per-invocation frontend, agent and task_id context for log records."""

from __future__ import annotations

from contextvars import ContextVar
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput
    from cline_hooks.core.protocol import Protocol

_UNSET = "-"
_MAIN_AGENT = "main"

_frontend: ContextVar[str] = ContextVar("log_frontend", default=_UNSET)
_agent: ContextVar[str] = ContextVar("log_agent", default=_UNSET)
_task_id: ContextVar[str] = ContextVar("log_task_id", default=_UNSET)


def bind(proto: Protocol, hook: HookInput) -> None:
    """Bind the current invocation's frontend, agent and task_id to later log records."""
    _frontend.set(proto.frontend_spec.name if proto.frontend_spec else _UNSET)
    _agent.set(hook.agentId or hook.agentType or _MAIN_AGENT)
    _task_id.set(hook.taskId)


class HookContextFilter(logging.Filter):
    """Stamps every record with the current invocation's `context` and `task_id`."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the current invocation context to the record and always allow it through.

        Returns:
            True, unconditionally.
        """
        frontend = _frontend.get()
        agent = _agent.get()
        record.context = frontend if frontend == _UNSET or agent == _MAIN_AGENT else f"{frontend}/{agent}"
        record.task_id = _task_id.get()
        return True
