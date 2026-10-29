# Frontends

## Install targets

`cline-hook install <assistant>` writes to:

| Assistant | Writes to |
|-----------|-----------|
| Antigravity | `~/.gemini/config/hooks.json` |
| Claude Code | `~/.claude/settings.json` |
| Codex | `~/.codex/hooks.json` |
| Kiro | The agent config you give, which must already exist |
| Pi | `~/.pi/agent/extensions/cline-hooks.ts` (or under `$PI_CODING_AGENT_DIR`) |

Re-running an install only repoints entries whose binary is missing. `--force` repoints all of them. Pi's extension is always repointed.

Pi has no command hooks, so its extension relays Pi's events to `cline-hook`, with `session_compact` sent as a `TaskStart` with source `compact`.

## Hook support matrix

The canonical hooks each frontend fires, with its native name for each. `tests/test_readme_matrix.py` fails if this table drifts from `Protocol.supported_hooks`.

<!-- HOOK_MATRIX_START -->
| Canonical hook | Antigravity | Claude Code | Codex | Kiro | Pi |
|---|---|---|---|---|---|
| PreToolUse | `PreToolUse` | `PreToolUse` | `PreToolUse` | `preToolUse` | `tool_call` |
| PostToolUse | `PostToolUse` | `PostToolUse` | `PostToolUse` | `postToolUse` | `tool_result` |
| TaskStart | - | `SessionStart` | `SessionStart` | `agentSpawn` | `session_start` |
| TaskResume | - | - | - | - | - |
| TaskCancel | - | - | - | - | - |
| TaskComplete | - | - | - | - | - |
| UserPromptSubmit | - | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmit` | `before_agent_start` |
| PreCompact | - | - | - | - | `session_before_compact` |
| Stop | `Stop` | `Stop` | `Stop` | `stop` | `agent_end` |
| SubagentStart | - | `SubagentStart` | `SubagentStart` | - | - |
| SubagentStop | - | `SubagentStop` | `SubagentStop` | - | `session_shutdown` |
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
| `extension.ts` | A bridge extension, where the frontend runs extensions rather than hook commands |

A frontend speaking another's payload shape subclasses that frontend's spec
class and overrides only what differs - Codex is one.

Handlers see only the canonical vocabulary, a normalised `HookInput`, and the
capabilities the active `Protocol` exposes. A hook a frontend does not declare
never reaches one.
