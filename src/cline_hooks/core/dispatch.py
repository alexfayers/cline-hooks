"""Transport-agnostic hook dispatch, shared by the CLI entrypoint and the daemon."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.frontends import select_protocol
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.protocol import set_protocol
from cline_hooks.core.registry import HOOK_HANDLERS

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput
    from cline_hooks.core.protocol import Protocol, RawPayload

logger = logging.getLogger("hooks.dispatch")


def parse_hook(payload: RawPayload) -> tuple[Protocol, HookInput]:
    """Detect the frontend, set it active, configure logging, and parse the payload.

    Returns:
        The detected protocol and the parsed hook input.
    """
    proto = select_protocol(payload).from_payload(payload)
    set_protocol(proto)
    proto.configure_logging()
    hook = proto.parse(payload)
    return proto, hook


def run_handler(protocol: Protocol, hook: HookInput) -> Outcome:
    """Run the registered handler for `hook`, failing open to a plain allow.

    Args:
        protocol: The detected protocol, used to check which hooks it fires.
        hook: The parsed hook input.

    Returns:
        The handler's Outcome, or an allow Outcome where the protocol
        doesn't fire this hook or no handler is registered for it.
    """
    if not protocol.fires(hook.hookName):
        logger.debug("Ignoring %s: not a hook %s fires", hook.hookName, type(protocol).__name__)
        return Outcome.allow()

    handler = HOOK_HANDLERS.get(hook.hookName)
    if handler is None:
        return Outcome.allow()

    return handler(hook) or Outcome.allow()


def dispatch(payload: RawPayload) -> Outcome:
    """Parse a raw hook payload and run it through the matching handler.

    Fails open: a parse failure, an event this frontend doesn't fire, or no
    registered handler all resolve to a plain allow.

    Args:
        payload: The raw hook invocation payload.

    Returns:
        The handler's Outcome, or an allow Outcome for every fail-open case.
    """
    try:
        proto, hook = parse_hook(payload)
    except Exception:
        logger.exception("Failed to parse hook input")
        return Outcome.allow()

    return run_handler(proto, hook)
