# cline-hooks

Lifecycle hooks framework for AI coding assistants. Supports Cline and Kiro.

## Installation

```bash
uv tool install git+https://github.com/alexfayers/cline-hooks
```

### Cline

```bash
cline-hook install cline ~/Documents/Cline/Hooks
```

### Kiro

```bash
cline-hook install kiro ~/.kiro/agents/my-agent.json
```

### List installed plugins

```bash
cline-hook plugins
```

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
    command="rm",                              # command name to match
    blocked_flags=frozenset({"-f", "--force"}), # flags that trigger a block
    message="rm -f is not allowed.",           # message returned to the LLM
    validator=my_validator_fn,                 # optional custom validator
)
```

A `validator` receives `(cmd: ParsedCommand, all_commands: list[ParsedCommand])`
and returns `True` if the command should be blocked.
