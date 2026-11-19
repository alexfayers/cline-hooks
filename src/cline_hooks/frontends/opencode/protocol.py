"""Opencode exit-code protocol, spoken by the opencode bridge plugin."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.models import PreCompactFields, TaskStartFields
from cline_hooks.core.payload import PayloadEnvelope, StandardPayloadProtocol, ToolParams
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.claude_code.models import (
    ClaudeCodeShellParams,
    ClaudeCodeStop,
    ClaudeCodeUserPromptSubmit,
)
from cline_hooks.frontends.opencode.install import config_dir
from cline_hooks.frontends.opencode.models import (
    OpencodeEditParams,
    OpencodeEnvelope,
    OpencodeReadParams,
    OpencodeSkillParams,
    OpencodeWriteParams,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.protocol import RawPayload


def _skills_dir() -> Path:
    return config_dir() / "skills"


@frontend(
    name="opencode",
    display_name="OpenCode",
    installer=None,
    detect_priority=EXACT_MATCH,
    skills_dir=_skills_dir,
)
class OpencodeProtocol(StandardPayloadProtocol):
    """Opencode 2.x exit-code protocol: exit 0 + stdout for context, exit 2 + stderr to block.

    Opencode has no command hooks, only plugin hooks, so the bridge plugin
    relays each as snake_case JSON named `<domain>.<hook>` after the plugin
    API hook it came from, and maps the exit code back onto it. `session.start`
    is the bridge's own name for a session's first prompt. The plugin renames
    MCP tools, which opencode names `<server>_<tool>`, to `mcp__<server>__<tool>`,
    and splits a `patch` call that touches several files into one call per file.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("tool.execute.before"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("tool.execute.after"),
        CanonicalHook.TASK_START: HookRegistration("session.start"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("session.prompt"),
        CanonicalHook.PRE_COMPACT: HookRegistration("session.compaction"),
        CanonicalHook.STOP: HookRegistration("session.idle"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "shell": CanonicalTool.SHELL,
        "read": CanonicalTool.READ,
        "edit": CanonicalTool.EDIT,
        "patch": CanonicalTool.EDIT,
        "write": CanonicalTool.WRITE,
        "skill": CanonicalTool.SKILL,
        "subagent": CanonicalTool.SPAWN_AGENT,
        "webfetch": CanonicalTool.WEB_FETCH,
        "websearch": CanonicalTool.WEB_SEARCH,
        "todowrite": CanonicalTool.BOOKKEEPING,
    }
    envelope_model: ClassVar[type[PayloadEnvelope]] = OpencodeEnvelope
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.TASK_START: TaskStartFields,
        CanonicalHook.PRE_COMPACT: PreCompactFields,
        CanonicalHook.USER_PROMPT_SUBMIT: ClaudeCodeUserPromptSubmit,
        CanonicalHook.STOP: ClaudeCodeStop,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.SHELL: ClaudeCodeShellParams,
        CanonicalTool.READ: OpencodeReadParams,
        CanonicalTool.EDIT: OpencodeEditParams,
        CanonicalTool.WRITE: OpencodeWriteParams,
        CanonicalTool.SKILL: OpencodeSkillParams,
    }
    mcp_prefix: ClassVar[str] = "mcp__"
    mcp_separators: ClassVar[tuple[str, ...]] = ("__",)

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect the bridge plugin's payload by its opencode hook or event name.

        Returns:
            True if `hook_event_name` is one of opencode's own hook or event names.
        """
        data = payload.data
        if data is None:
            return False
        return data.get(cls.hook_event_key) in cls.native_hook_names()

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout."""
        exit_allow(message)

    def allow_with_input(
        self,
        updated_input: Mapping[str, Any],
        message: str | None = None,
        *,
        fallback_message: str | None = None,
        system_message: str | None = None,
    ) -> NoReturn:
        """Allow via exit 0, JSON on stdout that the bridge plugin copies into the tool args."""
        exit_allow(json.dumps({"updated_input": dict(updated_input), "message": message}))

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        exit_block(message)
