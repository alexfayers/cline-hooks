"""Opencode's payload models: where the bridge plugin's tool input differs from canonical."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any

from pydantic import Field, model_validator

from cline_hooks.core.payload import PayloadEnvelope, ToolParams, diff_envelope, line_range

_PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+)$")


class OpencodeEnvelope(PayloadEnvelope):
    """Opencode's envelope; a shell call's `workdir` is the directory it runs in."""

    @model_validator(mode="before")
    @classmethod
    def _shell_workdir(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Point `cwd` at a shell call's `workdir`, resolved against the session directory.

        Returns:
            The data with `cwd` set to the workdir, where the tool input has one.
        """
        tool_input = data.get("tool_input")
        workdir = tool_input.get("workdir") if isinstance(tool_input, dict) else None
        if not isinstance(workdir, str) or not workdir:
            return data
        return {**data, "cwd": os.path.normpath(Path(str(data.get("cwd") or ""), workdir))}


class OpencodeReadParams(ToolParams):
    """Parameters for an opencode `read` tool call; `offset`/`limit` become a line range."""

    path: str = ""
    start_line: int | None = None
    end_line: int | None = None

    _line_range = model_validator(mode="before")(line_range)


class OpencodeWriteParams(ToolParams):
    """Parameters for an opencode `write` tool call."""

    path: str | None = None
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("content"))


def _search_replace(search: list[str], replace: list[str]) -> str:
    return "------- SEARCH\n{}=======\n{}+++++++ REPLACE".format(
        "".join(f"{line}\n" for line in search), "".join(f"{line}\n" for line in replace)
    )


def patch_file(patch_text: str) -> tuple[str, str | None] | None:
    """Return the first file a `patch` call touches and its change as SEARCH/REPLACE blocks.

    The bridge plugin splits a patch that touches several files into one call
    per file, so only the first file's section is read.

    Args:
        patch_text: The `*** Begin Patch` text opencode's `patch` tool takes.

    Returns:
        The file path and its diff, None for a deleted file, or None if no file is named.
    """
    lines = patch_text.splitlines()
    found = next(((i, m) for i, line in enumerate(lines) if (m := _PATCH_FILE.match(line))), None)
    if found is None:
        return None
    start, match = found
    kind, path = match.group(1), match.group(2).strip()
    if kind == "Delete":
        return path, None
    blocks: list[str] = []
    search: list[str] = []
    replace: list[str] = []
    for line in lines[start + 1 :]:
        if _PATCH_FILE.match(line) or line.startswith("*** End Patch"):
            break
        if line.startswith("@@") and (search or replace):
            blocks.append(_search_replace(search, replace))
            search, replace = [], []
        elif line[:1] in {" ", "-"} and kind == "Update":
            search.append(line[1:])
            if line[:1] == " ":
                replace.append(line[1:])
        elif line[:1] == "+":
            replace.append(line[1:])
    if search or replace:
        blocks.append(_search_replace(search, replace))
    return path, "\n".join(blocks) or None


class OpencodeEditParams(ToolParams):
    """Parameters for an opencode `edit` or `patch` tool call, rendered as SEARCH/REPLACE blocks.

    `edit` gives `oldString`/`newString`; `patch`, which GPT models get instead,
    gives `patchText`.
    """

    path: str | None = None
    diff: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _diff(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Render the replacement, or the patch's first file, as SEARCH/REPLACE blocks.

        Returns:
            The data with `path` and `diff` set from `patchText`, or `diff` set
            from the replacement, where there is one.
        """
        if "patchText" in data:
            parsed = patch_file(str(data["patchText"] or ""))
            return data if parsed is None else {**data, "path": parsed[0], "diff": parsed[1]}
        if "newString" not in data:
            return data
        diff = f"------- SEARCH\n{data.get('oldString', '')}\n=======\n{data['newString']}\n+++++++ REPLACE"
        return {**data, "diff": diff}


class OpencodeSkillParams(ToolParams):
    """Parameters for an opencode `skill` tool call, which names the skill as `id`."""

    skill: str = Field(default="", validation_alias="id")
