# cline-hooks

Cline hooks framework for enforcing coding standards and workflow rules.

## Installation

Install from GitHub and link hooks to your Cline hooks directory:

```bash
uv tool install git+https://github.com/alexfayers/cline-hooks
cline-hook install ~/Documents/Cline/Hooks
```

Or clone and install locally:

```bash
git clone https://github.com/alexfayers/cline-hooks
cd cline-hooks
bash install-hooks.sh ~/Documents/Cline/Hooks
```

Windows local install:

```powershell
git clone https://github.com/alexfayers/cline-hooks
Set-Location cline-hooks
.\install-hooks.ps1 "$HOME\Documents\Cline\Hooks"
```

## Plugins

Extend behaviour by implementing `ClineHooksPlugin` and registering via entry points:

```toml
[project.entry-points."cline_hooks"]
my-plugin = "my_package:MyPlugin"
```
