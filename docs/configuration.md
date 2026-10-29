# Configuration

| Variable | Effect |
|----------|--------|
| `CLINE_HOOKS_DATA_DIR` | Where state files and `cline-hooks.log` live. Defaults to the platform data directory. The log rotates at 10 MB and keeps 3 backups. |
| `CLINE_HOOKS_FRONTEND` | Assistant name to load. Unset, it is detected from the payload. |
| `CLINE_HOOKS_PUSH_BLOCK_MARKERS` | Comma-separated file or directory names. `git push` is blocked in a repo that has one of them at or above its root. Empty by default. |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Any non-empty value turns on the delegation nudges. |
| `PI_CODING_AGENT_DIR` | Pi's agent directory, used by `install pi`. Defaults to `~/.pi/agent`. |
| `HERDR_PANE_ID` | Read by the handoff acknowledgement plugin to find the session's own Herdr pane. |

## Commands

| Command | Does |
|---------|------|
| `cline-hook` (no arguments) | Reads one hook payload from stdin. This is what the assistants run. |
| `cline-hook install <assistant> [target] [--force]` | Registers the hooks. |
| `cline-hook plugins` | Lists loaded plugins, the extension points each owns and contributes to, and whether the plugin set validates. |
| `cline-hook retro-count --get` / `--reset` | Prints or resets the count of sessions since the last retrospective. |
| `cline-hook handoff-ack --clear` | Releases sessions blocked on a handoff acknowledgement. |
