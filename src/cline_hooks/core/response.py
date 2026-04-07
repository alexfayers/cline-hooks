from __future__ import annotations

import logging
from typing import NoReturn

from cline_hooks.core.protocol import get_protocol

logger = logging.getLogger("hooks")


def allow(message: str | None = None, *, prefix: str = "REMINDER") -> NoReturn:
    """Allow the tool call to proceed, optionally injecting a reminder.

    Args:
        message: Optional reminder text. Defaults to None.
        prefix: Label prepended to the message. Defaults to "REMINDER".
    """
    if message is not None:
        message = f"{prefix}: {message}" if prefix else message
        logger.warning("Reminding: %s", message)

    get_protocol().allow(message)


def block(message: str, *, task_id: str | None = None, tool_name: str | None = None) -> NoReturn:
    """Cancel the tool call with an error message.

    Args:
        message: Reason for blocking.
        task_id: Optional task ID for recording the block event.
        tool_name: Optional tool name for recording the block event.
    """
    logger.warning("Blocking: %s", message)
    if task_id is not None and tool_name is not None:
        from cline_hooks.state.store import TaskStateStore  # noqa: PLC0415

        TaskStateStore().record_block(task_id, tool_name, message)
    get_protocol().block(message)
