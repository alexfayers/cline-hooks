# cline-hooks

One `cline-hook` command that runs lifecycle hooks for AI coding assistants: Antigravity, Claude Code, Codex, Kiro and Pi. Bundled and installed plugins can add notes to a session or block a tool call.

## Install

```bash
uv tool install "git+https://github.com/alexfayers/cline-hooks.git"
```

With [llm-prompts](https://github.com/alexfayers/llm-prompts), add it to `~/.config/llm-prompts/config.toml` and run `llm-prompts setup`:

```toml
[[tools]]
name = "cline-hooks"
source = "git+https://github.com/alexfayers/cline-hooks.git"
```

## Quick start

Register the hooks with each assistant you use:

```bash
cline-hook install claude-code
cline-hook install codex
cline-hook install pi
```

Kiro takes a path: `cline-hook install kiro ~/.kiro/agents/my-agent.json`. `cline-hook install --help` lists every assistant. Add `--force` to repoint entries whose binary still exists.

Other commands:

- `cline-hook plugins` lists loaded plugins
- `cline-hook retro-count --get` / `--reset` shows or resets the retrospective session counter
- `cline-hook handoff-ack --clear` releases sessions blocked on a handoff acknowledgement

## Configuration

- `CLINE_HOOKS_DATA_DIR` sets where state files and the log live
- `CLINE_HOOKS_FRONTEND` loads only the named assistant, instead of detecting it from the payload
- `CLINE_HOOKS_PUSH_BLOCK_MARKERS` blocks `git push` in repos under any of the given file or directory names

The rest are in [docs/configuration.md](docs/configuration.md).

## Docs

- [Frontends](docs/frontends.md): install targets, hook support matrix, adding a frontend
- [Plugins](docs/plugins.md): bundled plugins, writing and registering your own
- [Configuration](docs/configuration.md): env vars and commands

See also [llm-prompts](https://github.com/alexfayers/llm-prompts) and [mcp-memory](https://github.com/alexfayers/mcp-memory).
