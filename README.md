# cline-hooks

Lifecycle hooks framework for AI coding assistants. Supports Cline, Claude Code,
Codex, GitHub Copilot, and Kiro.

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
cline-hook install claude-code
cline-hook install codex
cline-hook install copilot
cline-hook install kiro ~/.kiro/agents/my-agent.json
```

### List installed plugins

```bash
cline-hook plugins
```

## Hook support matrix

Which canonical hooks each frontend fires, and its native name for each.
Generated from `Protocol.supported_hooks`; `tests/test_readme_matrix.py` fails
the build if it drifts.

<!-- HOOK_MATRIX_START -->
| Canonical hook | Claude Code | Cline | Codex | GitHub Copilot | Kiro |
|---|---|---|---|---|---|
| PreToolUse | `PreToolUse` | `PreToolUse` | `PreToolUse` | `PreToolUse` | `preToolUse` |
| PostToolUse | `PostToolUse` | `PostToolUse` | `PostToolUse` | `PostToolUse` | `postToolUse` |
| TaskStart | `SessionStart` | `TaskStart` | `SessionStart` | `SessionStart` | `agentSpawn` |
| TaskResume | - | `TaskResume` | - | - | - |
| TaskCancel | - | `TaskCancel` | - | - | - |
| TaskComplete | - | `TaskComplete` | - | - | - |
| UserPromptSubmit | `UserPromptSubmit` | `UserPromptSubmit` | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmit` |
| PreCompact | - | `PreCompact` | - | `PreCompact` | - |
| Stop | `Stop` | `Stop` | `Stop` | `Stop` | `stop` |
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

A frontend speaking another's payload shape subclasses that frontend's spec
class and overrides only what differs - all Codex and Copilot are.

Handlers see only the canonical vocabulary, a normalised `HookInput`, and the
capabilities the active `Protocol` exposes; a hook a frontend does not declare
never reaches one.

## Plugins

Plugins extend the hook framework with custom command rules, build tool
detection, workspace context, and MCP tool validation.

### Creating a plugin

1. Subclass `HooksPlugin` and override the methods you need:

```python
from cline_hooks.core.plugin import HooksPlugin
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

    def get_workspace_context(self, workspace_roots: list[str]) -> str | None:
        """Inject context at session start (e.g. workspace type detection)."""
        return None

    def validate_mcp_tool(self, tool_name: str, arguments: dict[str, object]) -> str | None:
        """Return a block reason for an MCP tool call, or None to allow."""
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

| Method | Purpose | Return |
|--------|---------|--------|
| `get_build_commands()` | Names of build tools (e.g. `make`, `npm`) | `frozenset[str]` |
| `get_command_rules()` | Rules to block or validate shell commands | `list[CommandRule]` |
| `get_workspace_context(roots)` | Context string injected at session start | `str \| None` |
| `validate_mcp_tool(name, args)` | Block reason for MCP tool calls | `str \| None` |

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
