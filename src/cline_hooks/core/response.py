from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import NoReturn

from cline_hooks.core.outcome import Disposition, Outcome
from cline_hooks.core.protocol import Protocol, get_protocol

logger = logging.getLogger("hooks.response")


@dataclass(frozen=True, slots=True)
class Response:
    """A rendered hook decision, ready for a transport to deliver.

    Attributes:
        exit_code: Process exit code for the command-path transport.
        stdout: Text for the command-path transport's stdout.
        stderr: Text for the command-path transport's stderr.
    """

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


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


def block(message: str) -> NoReturn:
    """Cancel the tool call with an error message.

    Args:
        message: Reason for blocking.
    """
    logger.warning("Blocking: %s", message)
    get_protocol().block(message)


def feedback(message: str) -> NoReturn:
    """Continue the conversation with non-error feedback."""
    logger.warning("Feedback: %s", message)
    get_protocol().feedback(message)


def render(outcome: Outcome, protocol: Protocol) -> Response:
    """Render a merged Outcome into a transport-agnostic Response.

    Args:
        outcome: The merged Outcome to render.
        protocol: The protocol to render for.

    Returns:
        The rendered Response.
    """
    if outcome.disposition is Disposition.BLOCK:
        logger.warning("Blocking: %s", outcome.message)
    elif outcome.disposition is Disposition.FEEDBACK:
        logger.warning("Feedback: %s", outcome.message)
    else:
        message = outcome.message
        if message is not None and outcome.label:
            message = f"{outcome.label}: {message}"
            logger.warning("Reminding: %s", message)
    return protocol.render(outcome)
