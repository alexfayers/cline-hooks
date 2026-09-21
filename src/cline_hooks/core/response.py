from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from cline_hooks.core.outcome import Disposition, Outcome

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol

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
    elif outcome.message is not None and outcome.label:
        logger.warning("Reminding: %s", outcome.labelled_message)
    return protocol.render(outcome)
