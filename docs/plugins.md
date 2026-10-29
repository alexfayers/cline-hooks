# Plugins

Plugins add custom command rules, build tool detection, research tools, ecosystem tooling notes, and hook-driven notes or blocks. Core knows only plugins and their callers: each extension point is published by an owning plugin, and other plugins contribute to it.

`cline-hook plugins` lists the loaded plugins and the extension points each owns and contributes to.

## Bundled plugins

- Build tool detection and build failure alerts
- Shell command rules and guards, such as `rm -f`, commit messages and the push block
- Per-tool guards and edit blocks for files managed by llm-prompts
- Research lookups and the research trace at `Stop`
- Ecosystem tooling notes and startup blocks
- Context usage notes
- Nudges for commit size, retrospectives, persistence to memory, delegation and plan handoff
- Handoff acknowledgement between sessions
- Tracking of skill loads, memory writes, agent spawns and MCP tool use

## Creating a plugin

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

   Implement only the methods you need. A `@hookimpl` method takes a subset of
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

3. Install your package alongside cline-hooks. The plugin is discovered automatically.

## Extension points

`tests/test_readme_matrix.py` fails if this table drifts from the bundled plugins' hookspecs.

<!-- EXTENSION_POINTS_START -->
| Extension point | Owner | Purpose | Return |
|-----------------|-------|---------|--------|
| `build_commands()` | `BuildToolsPlugin` | Return command names that are considered build tools. | `frozenset[str]` |
| `command_rules()` | `CommandRulesPlugin` | Return CommandRule instances this plugin wants to enforce. | `list[CommandRule]` |
| `ecosystem_tooling_note(workspace_roots)` | `EcosystemPlugin` | Return this plugin's ecosystem tooling note for these workspace roots. | `ToolingNote \| None` |
| `research_tools()` | `ResearchPlugin` | Return the tools that count as research lookups, with their detail extractors. | `dict[str, Callable[[dict[str, Any]], str]]` |
| `startup_blocks(workspace_roots)` | `StartupBlocksPlugin` | Return the startup blocks this plugin injects at session start. | `list[StartupBlock]` |
<!-- EXTENSION_POINTS_END -->

`on_hook` is not an extension point: every plugin receives each hook event in registration order.

## Merge rules

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
| `startup_blocks` | Joined, filtered by flags, sorted by (order, title), each body gets the chars left, over-budget -> fallback note, a fallback note that does not fit is dropped. |

## Owning an extension point

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

## CommandRule

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
