from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand

_HERDR_TIMEOUT_SECONDS = 5
_PROMPT_TARGET_INDEX = 2
_ACK_MARKER_PATTERN = re.compile(r"HANDOFF-ACK ([\w:.-]*\w)")
_HANDOFF_FIRST_LINE_PATTERN = re.compile(r"HANDOFF-ACK ([\w:.-]*\w)\.?")
_PEER_MESSAGE_PATTERN = re.compile(r"<cross-session-message\b[^>]*>\n?(.*?)\n?</cross-session-message>", re.DOTALL)
_PICKUP_CUE_PATTERN = re.compile(r"\bpickup\b", re.IGNORECASE)
_PRINTF_SUBSHELL_PREFIX = re.compile(r"""^\s*\$\(\s*printf\s+['"]""")


def ack_marker(pane_id: str) -> str:
    """Return the handoff acknowledgement marker for a pane.

    Returns:
        The fixed marker text naming the pane to acknowledge.
    """
    return f"HANDOFF-ACK {pane_id}"


def ack_marker_ids(text: str) -> list[str]:
    """Return the pane ids named by every handoff acknowledgement marker in the text.

    Returns:
        The pane ids, in order of appearance.
    """
    return _ACK_MARKER_PATTERN.findall(text)


def unwrap_peer_message(message: str) -> str:
    """Return the body of a cross-session peer message.

    Returns:
        The text inside the `cross-session-message` element, or the message unchanged if it has none.
    """
    match = _PEER_MESSAGE_PATTERN.search(message)
    return match.group(1) if match else message


def handoff_prompt_marker_id(message: str) -> str | None:
    """Return the pane id a pickup prompt asks to acknowledge.

    A pickup prompt has the marker alone on its first line and a `pickup` cue in the rest of the text.

    Returns:
        The marker pane id, or None if the message is not a pickup prompt.
    """
    first_line, _, rest = message.strip().partition("\n")
    match = _HANDOFF_FIRST_LINE_PATTERN.fullmatch(first_line.strip())
    if match is None or not _PICKUP_CUE_PATTERN.search(rest):
        return None
    return match.group(1)


def sent_handoff_marker_id(text: str) -> str | None:
    """Return the pane id a sent prompt asks to acknowledge.

    A `$(printf '...')` wrapper and its literal backslash-n escapes are undone before the pickup-prompt check.

    Returns:
        The marker pane id, or None if the text is not a pickup prompt.
    """
    return handoff_prompt_marker_id(_PRINTF_SUBSHELL_PREFIX.sub("", text).replace("\\n", "\n"))


def resolve_agent_pane(target: str) -> str | None:
    """Resolve a Herdr agent name or pane id to its pane id.

    Returns:
        The agent's pane id, or None if herdr is unavailable or no such agent exists.
    """
    if not shutil.which("herdr"):
        return None
    try:
        completed = subprocess.run(
            ["herdr", "agent", "get", target],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            timeout=_HERDR_TIMEOUT_SECONDS,
            check=False,
        )
        pane_id = json.loads(completed.stdout)["result"]["agent"]["pane_id"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    return pane_id if isinstance(pane_id, str) else None


def agent_prompts(commands: list[ParsedCommand]) -> list[tuple[str, str]]:
    """Return the target and text of every `herdr agent prompt` command.

    Returns:
        A (target pane, prompt text) pair per command, flags excluded.
    """
    prompts: list[tuple[str, str]] = []
    for cmd in commands:
        if cmd.name == "herdr" and cmd.args[:2] == ["agent", "prompt"] and len(cmd.args) > _PROMPT_TARGET_INDEX:
            target, *text = cmd.args[_PROMPT_TARGET_INDEX:]
            prompts.append((target, " ".join(text)))
    return prompts


def is_ack_only(commands: list[ParsedCommand], pane_id: str) -> bool:
    """Check that the commands are solely the acknowledgement prompt for a pane.

    Returns:
        True if every command is `herdr agent prompt <pane_id>` carrying the pane's marker.
    """
    prompts = agent_prompts(commands)
    return (
        bool(commands)
        and len(prompts) == len(commands)
        and all(target == pane_id and ack_marker(pane_id) in text for target, text in prompts)
    )


def is_tab_close(commands: list[ParsedCommand]) -> bool:
    """Check whether any command is `herdr tab close`.

    Returns:
        True if a `herdr tab close` command is present.
    """
    return any(cmd.name == "herdr" and cmd.args[:2] == ["tab", "close"] for cmd in commands)


def removed_worktree_paths(commands: list[ParsedCommand]) -> list[str]:
    """Return the path arguments of every `git worktree remove` command.

    Returns:
        The path words that follow `worktree remove`, flags excluded.
    """
    paths: list[str] = []
    for cmd in commands:
        if cmd.name == "git" and "worktree" in cmd.args:
            rest = cmd.args[cmd.args.index("worktree") + 1 :]
            if rest[:1] == ["remove"]:
                paths.extend(rest[1:])
    return paths


def _linked_workspaces() -> dict[str, str]:
    """Map each Herdr workspace's checkout path to its id.

    Returns:
        The mapping, or empty if herdr is unavailable or fails.
    """
    if not shutil.which("herdr"):
        return {}
    try:
        completed = subprocess.run(
            ["herdr", "workspace", "list"],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            timeout=_HERDR_TIMEOUT_SECONDS,
            check=False,
        )
        workspaces = json.loads(completed.stdout)["result"]["workspaces"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {}
    if completed.returncode != 0:
        return {}
    return {
        os.path.normpath(workspace["worktree"]["checkout_path"]): workspace["workspace_id"]
        for workspace in workspaces
        if "checkout_path" in (workspace.get("worktree") or {})
    }


def workspace_linking(paths: list[str], cwd: str) -> str | None:
    """Return the id of a Herdr workspace linked to any of the given paths, else None.

    Returns:
        The first matching workspace id, or None when none match or herdr cannot be queried.
    """
    if not paths:
        return None
    linked = _linked_workspaces()
    for path in paths:
        resolved = os.path.normpath(Path(cwd) / Path(path).expanduser())
        if resolved in linked:
            return linked[resolved]
    return None
