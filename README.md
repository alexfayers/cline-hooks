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

Pass `--force` to repoint existing cline-hook entries, Pi's extension and Cline's
entry points even where the binary they name still exists; without it, only those
whose binary is missing are repointed.

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
| SubagentStop | - | `SubagentStop` | - | `SubagentStop` | `SubagentStop` | - | - |
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
detection, research tools, ecosystem tooling notes, and hook-driven
notes/blocking. Core knows only plugins and their callers: each extension point
is published by an owning plugin, and other plugins contribute to it.

### Creating a plugin

1. Subclass `HooksPlugin` and mark the extension points you contribute to with
   `@hookimpl`. The method name is the extension point's name:

```python
import logging

from cline_hooks.core.plugin import HookResult, HooksPlugin, hookimpl
from cline_hooks.handlers.commands import CommandRule
from cline_hooks.plugins.ecosystem import ToolingNote


class MyPlugin(HooksPlugin):
    @hookimpl
    def build_commands(self) -> frozenset[str]:
        """Register custom build tool names."""
        return frozenset({"make", "cmake"})

    @hookimpl
    def command_rules(self) -> list[CommandRule]:
        """Block dangerous commands or enforce conventions."""
        return [
            CommandRule(
                command="docker",
                blocked_flags=frozenset({"--privileged"}),
                message="--privileged is not allowed.",
            ),
        ]

    @hookimpl
    def ecosystem_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        """Supply this plugin's ecosystem tooling note for these workspace roots."""
        return None

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Handle any hook event, returning notes and/or a block reason."""
        return None
```

   Implement only the methods you need; a `@hookimpl` method takes a subset of
   its extension point's parameters. `@hookimpl(tryfirst=True)` runs before
   other contributors. `@hookimpl(optionalhook=True)` contributes to an
   extension point whose owner may not be installed, and is ignored when it is
   absent.

2. Register it as an entry point in your `pyproject.toml`:

```toml
[project.entry-points."cline_hooks"]
my-plugin = "my_package:MyPlugin"
```

   An entry point may name a class, a module or a package. A module or
   package entry point uses every `HooksPlugin` subclass defined in each
   module, and a package is loaded one submodule at a time in alphabetical
   order, so a submodule that fails to import is skipped. Entry points load
   sorted by name, then value, after the bundled plugins. A plugin that fails
   to load or register, or that still defines a removed `get_*` method, is
   reported at TaskStart to both the agent and the user.

```toml
[project.entry-points."cline_hooks"]
my-plugins = "my_package.plugins"
```

3. Install your package alongside cline-hooks. The plugin will be
   discovered automatically.

### Extension points

<!-- EXTENSION_POINTS_START -->
| Extension point | Owner | Purpose | Return |
|-----------------|-------|---------|--------|
| `build_commands()` | `BuildToolsPlugin` | Return command names that are considered build tools. | `frozenset[str]` |
| `command_rules()` | `CommandRulesPlugin` | Return CommandRule instances this plugin wants to enforce. | `list[CommandRule]` |
| `ecosystem_tooling_note(workspace_roots)` | `EcosystemPlugin` | Return this plugin's ecosystem tooling note for these workspace roots. | `ToolingNote \| None` |
| `research_tools()` | `ResearchPlugin` | Return the tools that count as research lookups, with their detail extractors. | `dict[str, Callable[[dict[str, Any]], str]]` |
<!-- EXTENSION_POINTS_END -->

`cline-hook plugins` lists the extension points each loaded plugin owns and
contributes to. `on_hook` is not an extension point: every plugin receives each
hook event in registration order.

### Merge rules

Contributions are collected in pluggy order: `tryfirst` contributors first, then
the last-registered plugin first, so plugins from entry points come before the
bundled ones. A contribution that is `None`, raises, or returns the wrong type
is skipped, and the last two are logged against the contributing plugin.

| Extension point | Merge rule |
|-----------------|------------|
| `build_commands` | The union of every contribution. |
| `command_rules` | Lists are concatenated in contributor order, and the first matching rule wins. |
| `research_tools` | Dicts are merged in contributor order, and the first entry for a tool name wins. |
| `ecosystem_tooling_note` | The generic note unless a contribution replaces it, then replacing notes, then additive notes. |

### Owning an extension point

A plugin publishes an extension point by setting `hookspecs` to a class of
`@hookspec` methods. The first docstring line of each method is its purpose,
and the method name is what contributors implement with `@hookimpl`:

```python
from cline_hooks.core.plugin import HooksPlugin, collect_contributions, hookspec


class LintersSpec:
    """Extension point for contributing linter commands."""

    @hookspec
    def linter_commands(self) -> frozenset[str]:
        """Return command names that are considered linters."""
        raise NotImplementedError


def all_linter_commands() -> frozenset[str]:
    return frozenset().union(*collect_contributions(LintersSpec.linter_commands, frozenset))


class LintersPlugin(HooksPlugin):
    hookspecs = LintersSpec
```

`collect_contributions(spec, expected, **kwargs)` calls every contributor and
returns their results as a list in contributor order. `expected` is the type each
result must be, and `kwargs` are the spec's parameters by name. The list is
empty when nothing contributes or the owner is not loaded. The owner decides
how the results merge.

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
