from __future__ import annotations

from pathlib import Path
import shlex
import tempfile
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import PreShellKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.handlers.commands import _iter_nodes, extract_commands, parse_command
from cline_hooks.plugins.command_rules import reads_piped_build_output

if TYPE_CHECKING:
    import logging

    import bashlex.ast

FILTER_NOTE = "MUST NOT filter build output through a pipe - MUST redirect it to a log file and read the log."
MANUAL_REDIRECT = "MUST run the build as `<build command> > <log file> 2>&1`, then read the log."


_BUILD_AND_FILTER_STAGES = 2
_STDERR_TO_STDOUT = (">&", 2, 1)


def _redirects(stage: bashlex.ast.node) -> list[tuple[str, int | None, object]]:
    """Return the (operator, fd, target) of each redirect on a stage."""
    return [(part.type, part.input, part.output) for part in getattr(stage, "parts", []) if part.kind == "redirect"]


def _filters_build(pipeline: bashlex.ast.node) -> bool:
    """Return True when a stage of the pipeline filters a build command's piped output.

    shortcut: a pipeline with a stage that is not a plain command is not inspected.
    """
    stages = [part for part in pipeline.parts if part.kind != "pipe"]
    commands = extract_commands([pipeline])
    return len(commands) == len(stages) and any(reads_piped_build_output(command) for command in commands)


def _is_plain_build_into_filter(pipeline: bashlex.ast.node) -> bool:
    """Return True for `<build> | <filter>` where only the build redirects, and only stderr into stdout."""
    stages = [part for part in pipeline.parts if part.kind != "pipe"]
    if len(stages) != _BUILD_AND_FILTER_STAGES or _redirects(stages[1]):
        return False
    return all(redirect == _STDERR_TO_STDOUT for redirect in _redirects(stages[0]))


def _filtered_pipelines(command: str) -> list[bashlex.ast.node]:
    """Return each pipeline that filters a build's output."""
    pipelines = (node for root in parse_command(command) for node in _iter_nodes(root) if node.kind == "pipeline")
    return [pipeline for pipeline in pipelines if _filters_build(pipeline)]


def redirect_filtered_builds(command: str, filtered: list[bashlex.ast.node], log_dir: Path) -> str:
    """Rewrite each `<build> | <filter>` to write a log in `log_dir` that its filter reads.

    The rewritten command runs the filter after a failed build, also under `set -e`,
    then exits with the build's status, else the filter's.

    Returns:
        The rewritten command.
    """
    for number, pipeline in reversed(list(enumerate(filtered))):
        build, filter_ = (command[part.pos[0] : part.pos[1]] for part in pipeline.parts if part.kind != "pipe")
        log = shlex.quote(str(log_dir / f"build-{number}.log"))
        rewritten = (
            f"{{ build_status=0; filter_status=0; {build} > {log} 2>&1 || build_status=$?; "
            f"{filter_} < {log} || filter_status=$?; "
            f"(exit $((build_status ? build_status : filter_status))); }}"
        )
        command = command[: pipeline.pos[0]] + rewritten + command[pipeline.pos[1] :]
    return command


class BuildRedirectPlugin(HooksPlugin):
    """Bundled plugin that redirects a build piped into grep, head or tail to a log the filter reads."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Rewrite a shell command that filters build output through a pipe.

        Returns:
            A HookResult carrying the rewritten input, or None.
        """
        if hook_name != PluginScope.PRE_SHELL:
            return None
        import bashlex.errors  # ruff: ignore[import-outside-top-level]

        call = PreShellKwargs.build(kwargs)
        try:
            filtered = _filtered_pipelines(call.command)
        except (bashlex.errors.ParsingError, NotImplementedError):
            logger.debug("Could not rewrite command: %s", call.command)
            return None
        if not filtered:
            return None
        if not (get_protocol().supports_updated_input() and all(map(_is_plain_build_into_filter, filtered))):
            return HookResult(block=f"{FILTER_NOTE} {MANUAL_REDIRECT}")
        log_dir = Path(tempfile.mkdtemp(prefix="build-logs-"))
        logs = [log_dir / f"build-{number}.log" for number in range(len(filtered))]
        return HookResult(
            notes=[f"{FILTER_NOTE} Full output: {', '.join(map(str, logs))}"],
            updated_input={**call.parameters, "command": redirect_filtered_builds(call.command, filtered, log_dir)},
        )
