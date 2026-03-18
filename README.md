# cline-hooks

Cline hooks framework for enforcing coding standards and workflow rules.

## Installation

```bash
uv tool install cline-hooks
```

## Usage

Run `install-hooks.sh <target-directory>` to symlink the hook binary into a Cline hooks directory.

## Plugins

Extend behaviour by implementing `ClineHooksPlugin` and registering via entry points:

```toml
[project.entry-points."cline_hooks"]
my-plugin = "my_package:MyPlugin"
```
