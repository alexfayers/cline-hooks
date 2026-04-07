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

## Plugins

Extend behaviour by implementing `ClineHooksPlugin` and registering via entry points:

```toml
[project.entry-points."cline_hooks"]
my-plugin = "my_package:MyPlugin"
```
