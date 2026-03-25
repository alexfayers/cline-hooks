from __future__ import annotations

import json
import logging
import sys
from typing import NoReturn

logger = logging.getLogger("hooks")


def respond(
    *,
    cancel: bool,
    context_modification: str | None = None,
    error_message: str | None = None,
) -> NoReturn:
    """Return the hook result to Cline via stdout.

    Args:
        cancel: If True, Cline will cancel the tool call.
        context_modification: Optional context to inject. Defaults to None.
        error_message: Optional reason for cancellation. Defaults to None.
    """
    res: dict[str, object] = {"cancel": cancel}

    if context_modification is not None:
        res["contextModification"] = context_modification

    if error_message is not None:
        res["errorMessage"] = error_message

    print(json.dumps(res), end="")  # noqa: T201
    sys.exit(0)


def allow(message: str | None = None, *, prefix: str = "REMINDER") -> NoReturn:
    """Allow the tool call to proceed, optionally injecting a reminder.

    Args:
        message: Optional reminder text. Defaults to None.
        prefix: Label prepended to the message. Defaults to "REMINDER".
    """
    if message is not None:
        message = f"{prefix}: {message}" if prefix else message
        logger.warning("Reminding: %s", message)

    respond(cancel=False, context_modification=message)


def block(message: str, *, task_id: str | None = None, tool_name: str | None = None) -> NoReturn:
    """Cancel the tool call with an error message.

    Args:
        message: Reason for blocking.
        task_id: Optional task ID for recording the block event.
        tool_name: Optional tool name for recording the block event.
    """
    logger.warning("Blocking: %s", message)
    if task_id is not None and tool_name is not None:
        from cline_hooks.state import TaskStateStore  # noqa: PLC0415

        TaskStateStore().record_block(task_id, tool_name, message)
    respond(cancel=True, error_message=message)
