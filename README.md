# cline-hooks

Lifecycle hooks framework for AI coding assistants. Supports Cline, Antigravity,
Claude Code, Codex, GitHub Copilot, Kiro, and Pi.

## Installation

```bash
uv tool install "git+https://github.com/alexfayers/cline-hooks.git"
```

### As part of the llm-prompts ecosystem

Add cline-hooks to your `~/.config/llm-prompts/config.toml`:

```toml
[[tools]]
name = "cline-hooks"
source = "git+https://github.com/alexfayers/cline-hooks.git"
```

Then run `llm-prompts setup` to install everything.

One install subcommand per frontend, listed by `cline-hook install --help`:

```bash
cline-hook install cline ~/Documents/Cline/Hooks
cline-hook install antigravity
cline-hook install claude-code
cline-hook install codex
cline-hook install copilot
cline-hook install kiro ~/.kiro/agents/my-agent.json
cline-hook install pi
```

Pi has no command hooks, so `cline-hook install pi` writes a bridge extension
(`~/.pi/agent/extensions/cline-hooks.ts`, or under `$PI_CODING_AGENT_DIR`) that
relays pi's extension events to `cline-hook`.

### List installed plugins

```bash
cline-hook plugins
```

## Hook support matrix

Which canonical hooks each frontend fires, and its native name for each.
Generated from `Protocol.supported_hooks`; `tests/test_readme_matrix.py` fails
the build if it drifts.

<!-- HOOK_MATRIX_START -->
| Canonical hook | Antigravity | Claude Code | Cline | Codex | GitHub Copilot | Kiro | Pi |
|---|---|---|---|---|---|---|---|
| PreToolUse | `PreToolUse` | `PreToolUse` | `PreToolUse` | `PreToolUse` | `PreToolUse` | `preToolUse` | `tool_call` |
| PostToolUse | `PostToolUse` | `PostToolUse` | `PostToolUse` | `PostToolUse` | `PostToolUse` | `postToolUse` | `tool_result` |
| TaskStart | - | `SessionStart` | `TaskStart` | `SessionStart` | `SessionStart` | `agentSpawn` | `session_start` |
| TaskResume | - | - | `TaskResume` | - | - | - | - |
| TaskCancel | - | - | `TaskCancel` | - | - | - | - |
| TaskComplete | - | - | `TaskComplete` | - | - | - | - |
| UserPromptSubmit | - | `UserPromptSubmit` | `UserPromptSubmit` | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmit` | `before_agent_start` |
| PreCompact | - | - | `PreCompact` | - | `PreCompact` | - | `session_before_compact` |
| Stop | `Stop` | `Stop` | `Stop` | `Stop` | `Stop` | `stop` | `agent_end` |
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
    mcp_prefix, mcp_separator = "mcp__", "__"

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
class and overrides only what differs - all Codex and Copilot are.

Handlers see only the canonical vocabulary, a normalised `HookInput`, and the
capabilities the active `Protocol` exposes; a hook a frontend does not declare
never reaches one.

## Plugins

Plugins extend the hook framework with custom command rules, build tool
detection, ecosystem tooling notes, and hook-driven notes/blocking.

### Creating a plugin

1. Subclass `HooksPlugin` and override the methods you need:

```python
import logging

from cline_hooks.core.plugin import HookResult, HooksPlugin, ToolingNote
from cline_hooks.handlers.commands import CommandRule


class MyPlugin(HooksPlugin):
    def get_build_commands(self) -> frozenset[str]:
        """Register custom build tool names."""
        return frozenset({"make", "cmake"})

    def get_command_rules(self) -> list[CommandRule]:
        """Block dangerous commands or enforce conventions."""
        return [
            CommandRule(
                command="docker",
                blocked_flags=frozenset({"--privileged"}),
                message="--privileged is not allowed.",
            ),
        ]

    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        """Supply this plugin's ecosystem tooling note for these workspace roots."""
        return None

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Handle any hook event, returning notes and/or a block reason."""
        return None
```

2. Register it as an entry point in your `pyproject.toml`:

```toml
[project.entry-points."cline_hooks"]
my-plugin = "my_package:MyPlugin"
```

3. Install your package alongside cline-hooks. The plugin will be
   discovered automatically.

### Plugin methods

<!-- PLUGIN_METHODS_START -->
| Method | Purpose | Return |
|--------|---------|--------|
| `get_build_commands()` | Return command names that are considered build tools. | `frozenset[str]` |
| `get_command_rules()` | Return CommandRule instances this plugin wants to enforce. | `list[CommandRule]` |
| `get_state_write_tool_names()` | Return MCP tool names that are considered state-write operations. | `frozenset[str]` |
| `get_research_tool_names()` | Return additional tool names that count as research lookups. | `frozenset[str]` |
| `get_research_detail_extractors()` | Return per-tool detail extractors for research lookups. | `dict[str, Callable[[dict[str, Any]], str]]` |
| `get_tooling_note(workspace_roots)` | Return this plugin's ecosystem tooling note for these workspace roots. | `ToolingNote \| None` |
| `on_hook(hook_name, logger, **kwargs)` | Handle any hook event, returning notes and/or a block reason. | `HookResult \| None` |
<!-- PLUGIN_METHODS_END -->

### CommandRule

```python
CommandRule(
    command="rm",  # command name to match
    blocked_flags=frozenset({"-f", "--force"}),  # flags that trigger a block
    message="rm -f is not allowed.",  # message returned to the LLM
    validator=my_validator_fn,  # optional custom validator
)
```

A `validator` receives `(cmd: ParsedCommand, all_commands: list[ParsedCommand])`
and returns `True` if the command should be blocked.

## Related

- [llm-prompts](https://github.com/alexfayers/llm-prompts) - cross-agent rules, workflows, and skills
- [mcp-memory](https://github.com/alexfayers/mcp-memory) - persistent memory MCP server (overlay for llm-prompts and cline-hooks)
