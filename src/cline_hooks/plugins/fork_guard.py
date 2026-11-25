from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import PreShellKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin, is_subagent
from cline_hooks.core.vocabulary import SHELL_TOOLS, PluginScope
from cline_hooks.handlers.commands import extract_commands, parse_command

if TYPE_CHECKING:
    import logging

_TEST_RUNNERS = frozenset({"pytest", "vitest", "jest", "tox", "nox"})
_TEST_SUBCOMMAND_RUNNERS = frozenset({
    "just",
    "npm",
    "pnpm",
    "yarn",
    "cargo",
    "go",
    "dotnet",
    "flutter",
    "dart",
    "mvn",
    "gradle",
})
_DEBUGGERS = frozenset({"gdb", "lldb", "pdb", "ipdb", "pudb", "dlv"})
_LAUNCHERS = frozenset({"uv", "uvx", "poetry", "npx", "pnpm", "python", "python3"})
_SCRIPT_RUNNER_WORDS = frozenset({"run", "run-script", "exec"})
_TEST_RECIPES = frozenset({"test", "t"})
_FORK_NOTE = "SHOULD send {work} to a fork and read its report, unless this check must run in the lead."


def _work_kind(tokens: list[str]) -> str | None:
    """Return the kind of work a command, given as its name and words, does that belongs in a fork, else None.

    Options and the `run`, `run-script` and `exec` words are dropped, and a bare `just` runs its default recipe,
    which runs the tests.
    """
    if not tokens:
        return None
    name = tokens[0]
    rest = [word for word in tokens[1:] if not word.startswith("-") and word not in _SCRIPT_RUNNER_WORDS]
    if name in _TEST_RUNNERS or (name in _TEST_SUBCOMMAND_RUNNERS and rest[:1] and rest[0] in _TEST_RECIPES):
        return "test runs"
    if name == "just" and len(tokens) == 1:
        return "test runs"
    if name in _DEBUGGERS:
        return "debugging"
    return _work_kind(rest) if name in _LAUNCHERS else None


class ForkGuardPlugin(HooksPlugin):
    """Bundled plugin that sends the lead's test runs and debugging to a fork."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Note to a lead that its test run or debugger belongs in a fork.

        Returns:
            A HookResult carrying a note that points to a fork, or None.
        """
        if hook_name != PluginScope.PRE_SHELL or is_subagent(kwargs):
            return None
        call = PreShellKwargs.build(kwargs)
        if call.tool_name not in SHELL_TOOLS:
            return None
        commands = []
        with contextlib.suppress(Exception):
            commands = extract_commands(parse_command(call.command))
        work = next(filter(None, (_work_kind([command.name, *command.words]) for command in commands)), None)
        if work is None:
            return None
        logger.debug("Noted the lead's %s belong in a fork", work)
        return HookResult(notes=[_FORK_NOTE.format(work=work)])
