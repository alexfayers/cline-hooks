from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NoReturn

from cline_hooks.core.outcome import Disposition, Outcome
from cline_hooks.core.protocol import get_protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger("hooks.response")


def allow(
    message: str | None = None,
    *,
    prefix: str = "REMINDER",
    system_message: str | None = None,
) -> NoReturn:
    """Allow the tool call to proceed, optionally injecting a reminder.

    Args:
        message: Optional reminder text. Defaults to None.
        prefix: Label prepended to the message. Defaults to "REMINDER".
        system_message: Optional message surfaced directly to the user on
            frontends that support a user channel.
    """
    if message is not None:
        message = f"{prefix}: {message}" if prefix else message
        logger.warning("Reminding: %s", message)

    get_protocol().allow(message, system_message=system_message)


def allow_with_input(
    updated_input: Mapping[str, Any],
    message: str | None = None,
    *,
    fallback_message: str | None = None,
    prefix: str = "REMINDER",
    system_message: str | None = None,
) -> NoReturn:
    """Allow the tool call to proceed with a changed input.

    Args:
        updated_input: The tool's complete input as it should run.
        message: Optional reminder text. Defaults to None.
        fallback_message: Context shown only where the frontend cannot change a call's input.
        prefix: Label prepended to the message. Defaults to "REMINDER".
        system_message: Optional message surfaced directly to the user on
            frontends that support a user channel.
    """
    if message is not None:
        message = f"{prefix}: {message}" if prefix else message
        logger.warning("Reminding: %s", message)

    logger.info("Updating input keys: %s", sorted(updated_input))
    get_protocol().allow_with_input(
        updated_input, message, fallback_message=fallback_message, system_message=system_message
    )


def block(message: str, *, task_id: str | None = None, tool_name: str | None = None) -> NoReturn:
    """Cancel the tool call with an error message.

    Args:
        message: Reason for blocking.
        task_id: Optional task ID for recording the block event.
        tool_name: Optional tool name for recording the block event.
    """
    logger.warning("Blocking: %s", message)
    if task_id is not None and tool_name is not None:
        from cline_hooks.state.store import TaskStateStore  # ruff: ignore[import-outside-top-level]

        TaskStateStore().record_block(task_id, tool_name, message)
    get_protocol().block(message)


def feedback(message: str) -> NoReturn:
    """Continue the conversation with non-error feedback."""
    logger.warning("Feedback: %s", message)
    get_protocol().feedback(message)


def emit(outcome: Outcome) -> NoReturn:
    """Resolve a hook handler's merged Outcome via the matching response function.

    Args:
        outcome: The merged Outcome to emit.
    """
    if outcome.disposition is Disposition.BLOCK:
        block(outcome.message or "")
    elif outcome.disposition is Disposition.FEEDBACK:
        feedback(outcome.message or "")
    elif outcome.updated_input is not None:
        allow_with_input(
            outcome.updated_input,
            outcome.message,
            fallback_message="\n\n".join(outcome.fallback_notes) or None,
            prefix=outcome.label,
            system_message=outcome.user_message or None,
        )
    else:
        allow(
            outcome.message,
            prefix=outcome.label,
            system_message=outcome.user_message or None,
        )
