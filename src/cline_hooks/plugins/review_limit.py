from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import TYPE_CHECKING, cast

from cline_hooks.config import CONFIG_PATH, MAX_IN_FLIGHT_REVIEWS_KEY, get_max_in_flight_reviews
from cline_hooks.core.hook_kwargs import PreShellKwargs
from cline_hooks.core.parameters import ShellParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, hookimpl, hookspec
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalHook, PluginScope
from cline_hooks.handlers.commands import extract_commands
from cline_hooks.state.jsonfile import read_json, updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    import logging

    from cline_hooks.handlers.commands import ParsedCommand

_LEDGER_PATH = get_data_dir() / "in-flight-reviews.json"
_GITHUB_PR = re.compile(r"https://(?P<host>[^/\s]+)/(?P<repo>[^/\s]+/[^/\s]+)/pull/(?P<number>\d+)")
_STATE_CHECK_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ReviewSource:
    """A command that opens a new review, and how to find and check the reviews it opens."""

    name: str
    creates: Callable[[ParsedCommand], bool]
    review_id: re.Pattern[str]
    is_open: Callable[[str], bool | None] | None = None


class ReviewSourcesSpec:
    """Extension point for contributing commands that open new reviews."""

    @hookspec
    def review_sources(self) -> list[ReviewSource]:
        """Return the commands that open a new review, counted against the in-flight review limit."""
        raise NotImplementedError


def _creates_github_pr(cmd: ParsedCommand) -> bool:
    """Return whether the command is `gh pr create`."""
    return cmd.name == "gh" and "pr" in cmd.args and cmd.args[cmd.args.index("pr") + 1 :][:1] == ["create"]


def _github_pr_open(url: str) -> bool | None:
    """Return whether the pull request at the URL is open, or None when `gh api` cannot tell."""
    if (match := _GITHUB_PR.fullmatch(url)) is None:
        return None
    try:
        result = subprocess.run(
            [  # ruff: ignore[start-process-with-partial-path]
                "gh",
                "api",
                "--hostname",
                match["host"],
                f"repos/{match['repo']}/pulls/{match['number']}",
                "--jq",
                ".state",
            ],
            capture_output=True,
            text=True,
            timeout=_STATE_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() == "open" if result.returncode == 0 else None


GITHUB_PR = ReviewSource(name="github", creates=_creates_github_pr, review_id=_GITHUB_PR, is_open=_github_pr_open)


def _sources() -> dict[str, ReviewSource]:
    """Return every contributed review source by name, the first contribution winning."""
    sources: dict[str, ReviewSource] = {}
    for contribution in collect_contributions(ReviewSourcesSpec.review_sources, list):
        for source in contribution:
            sources.setdefault(source.name, source)
    return sources


def _creating_sources(command: str, sources: dict[str, ReviewSource]) -> list[ReviewSource]:
    """Return the sources whose create command the shell command runs."""
    if not sources or not command.strip():
        return []

    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        commands = extract_commands(bashlex.parse(command))
    except (bashlex.errors.ParsingError, NotImplementedError):
        return []
    return [source for source in sources.values() if any(source.creates(cmd) for cmd in commands)]


def in_flight_reviews() -> dict[str, str]:
    """Return the ledger of in-flight review IDs, each mapped to its source name."""
    ledger = read_json(_LEDGER_PATH, dict[str, str]())
    return ledger if isinstance(ledger, dict) else {}


def drop_reviews(review_ids: list[str]) -> None:
    """Remove the given review IDs from the in-flight ledger."""
    with updated_json(_LEDGER_PATH, dict[str, str]()) as ledger:
        for review_id in review_ids:
            ledger.pop(review_id, None)


def _prune(sources: dict[str, ReviewSource]) -> dict[str, str]:
    """Drop ledger reviews their source reports as no longer open.

    Returns:
        The reviews left in the ledger.
    """
    ledger = in_flight_reviews()
    checks = {review_id: source.is_open for review_id, name in ledger.items() if (source := sources.get(name))}
    closed = [review_id for review_id, is_open in checks.items() if is_open is not None and is_open(review_id) is False]
    if closed:
        drop_reviews(closed)
    return {review_id: name for review_id, name in ledger.items() if review_id not in closed}


def _pre_shell_guard(logger: logging.Logger, command: str) -> HookResult | None:
    """Return a block for a command opening a new review while the in-flight count is at the limit."""
    sources = _sources()
    if not _creating_sources(command, sources):
        return None
    limit = get_max_in_flight_reviews()
    if len(in_flight_reviews()) < limit or len(ledger := _prune(sources)) < limit:
        return None
    logger.debug("Blocked a new review: %d in flight, limit %d", len(ledger), limit)
    return HookResult(
        block=(
            f"{len(ledger)} reviews are in flight, at the limit of {limit}: {', '.join(ledger)}. "
            "MUST NOT open a new review until some merge or close. Updating an existing review is allowed. "
            f"Only the user raises the limit, with `cline-hook reviews --limit <n>` or `{MAX_IN_FLIGHT_REVIEWS_KEY}` "
            f"in {CONFIG_PATH}. To drop merged or discarded reviews, run `cline-hook reviews --drop <id>...`."
        )
    )


def _record(command: str, tool_result: str) -> None:
    """Add the reviews a successful create command printed to the in-flight ledger."""
    found = {
        match[0]: source.name
        for source in _creating_sources(command, _sources())
        for match in source.review_id.finditer(tool_result)
    }
    if found:
        with updated_json(_LEDGER_PATH, dict[str, str]()) as ledger:
            ledger.update(found)


class ReviewLimitPlugin(HooksPlugin):
    """Bundled plugin limiting how many reviews created through guarded commands are in flight at once."""

    hookspecs = ReviewSourcesSpec

    @hookimpl
    def review_sources(self) -> list[ReviewSource]:
        """Return `gh pr create` as a review source."""
        return [GITHUB_PR]

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Block a new review at the limit on PreShell, and record created reviews on PostToolUse.

        Returns:
            The block on PreShell at the limit, otherwise None.
        """
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell_guard(logger, PreShellKwargs.build(kwargs).command)
        tool_result = kwargs.get("tool_result")
        shell_ran = kwargs.get("tool_name") in SHELL_TOOLS and kwargs.get("success")
        if hook_name == CanonicalHook.POST_TOOL_USE and shell_ran and isinstance(tool_result, str):
            command = ShellParameters.build(cast("dict[str, object]", kwargs.get("parameters") or {})).command
            _record(command, tool_result)
        return None
