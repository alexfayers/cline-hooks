# Frontends

## Install targets

`cline-hook install <assistant>` writes to:

| Assistant | Writes to |
|-----------|-----------|
| Antigravity | `~/.gemini/config/hooks.json` |
| Claude Code | `~/.claude/settings.json` |
| Codex | `~/.codex/hooks.json` |
| Kiro | The agent config you give, which must already exist |
| OpenCode | `plugins/cline-hooks.ts` in `$OPENCODE_CONFIG_DIR`, `$XDG_CONFIG_HOME/opencode` or `~/.config/opencode` |
| Pi | `~/.pi/agent/extensions/cline-hooks.ts` (or under `$PI_CODING_AGENT_DIR`) |

Re-running an install only repoints entries whose binary is missing. `--force` repoints all of them. Pi's extension and OpenCode's plugin are always repointed.

Pi has no command hooks, so its extension relays Pi's events to `cline-hook`, with `session_compact` sent as a `TaskStart` with source `compact`. Reminders produced by tool calls nested in a script are delivered on the script's own result.

OpenCode (2.x) has no command hooks either, so its plugin relays OpenCode's plugin hooks to `cline-hook`, run in the session's directory. It sends `session.start` with a session's first prompt, as `resume` for a session that has run before. It adds prompt context as a synthetic message. It renames MCP tools to `mcp__<server>__<tool>` and checks a `patch` call once per file it touches. A blocked `session.idle` continues the session with a synthetic message. Child sessions, and sessions still waiting on their own background work, skip it.

## Hook support matrix

The canonical hooks each frontend fires, with its native name for each. `tests/test_readme_matrix.py` fails if this table drifts from `Protocol.supported_hooks`.

<!-- HOOK_MATRIX_START -->
| Canonical hook | Antigravity | Claude Code | Codex | Kiro | OpenCode | Pi |
|---|---|---|---|---|---|---|
| PreToolUse | `PreToolUse` | `PreToolUse` | `PreToolUse` | `preToolUse` | `tool.execute.before` | `tool_call` |
| PostToolUse | `PostToolUse` | `PostToolUse` | `PostToolUse` | `postToolUse` | `tool.execute.after` | `tool_result` |
| TaskStart | - | `SessionStart` | `SessionStart` | `agentSpawn` | `session.start` | `session_start` |
| TaskResume | - | - | - | - | - | - |
| TaskCancel | - | - | - | - | - | - |
| TaskComplete | - | - | - | - | - | - |
| UserPromptSubmit | - | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmit` | `session.prompt` | `before_agent_start` |
| PreCompact | - | - | - | - | `session.compaction` | `session_before_compact` |
| Stop | `Stop` | `Stop` | `Stop` | `stop` | `session.idle` | `agent_end` |
| AgentIdle | - | - | - | - | - | `agent_settled` |
| SubagentStart | - | `SubagentStart` | `SubagentStart` | - | - | - |
| SubagentStop | - | `SubagentStop` | `SubagentStop` | - | - | `session_shutdown` |
| SessionEnd | - | `SessionEnd` | `SessionEnd` | - | - | - |
<!-- HOOK_MATRIX_END -->

## Adding a frontend

A frontend is one package under `src/cline_hooks/frontends/`. Nothing in
`core/` names one: the registry imports every package it finds and reads the
`@frontend` registrations, so a new package is picked up by detection, the CLI,
the install subcommands, the conformance tests, and the matrix above.

```python
@frontend(
    name="my-agent",                 # cline-hook install my-agent
    display_name="My Agent",
    installer=MyAgentInstaller(),
    detect_priority=EXACT_MATCH,     # or SHAPE_SNIFF, where detection guesses
)
class MyAgentProtocol(StandardPayloadProtocol):
    supported_hooks = {CanonicalHook.PRE_TOOL_USE: HookRegistration("preTool")}
    tool_map = {"run": CanonicalTool.SHELL}
    hook_models = {...}              # only where raw hook fields differ
    tool_models = {...}              # only where raw tool input differs
    mcp_prefix, mcp_separators = "mcp__", ("__",)

    @classmethod
    def detect(cls, payload): ...
    def allow(self, message=None, *, system_message=None): ...
    def block(self, message): ...
```

The package holds, at most:

| File | Holds |
|------|-------|
| `protocol.py` | The `@frontend` declaration: hooks, tool names, output channel |
| `models.py` | Models for payload fields whose raw shape differs from canonical |
| `install.py` | An `Installer`, usually a few lines on `JsonHookInstaller` |
| `transcript.py` | A `TranscriptReader`, if the frontend writes a readable transcript |
| `extension.ts` / `plugin.ts` | A bridge extension or plugin, where the frontend runs those rather than hook commands |

A frontend speaking another's payload shape subclasses that frontend's spec
class and overrides only what differs - Codex is one.

Handlers see only the canonical vocabulary, a normalised `HookInput`, and the
capabilities the active `Protocol` exposes. A hook a frontend does not declare
never reaches one.
