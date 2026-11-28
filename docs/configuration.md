# Configuration

| Variable | Effect |
|----------|--------|
| `CLINE_HOOKS_DATA_DIR` | Where state files and `cline-hooks.log` live. Defaults to `cline-hooks/state` in `$LLM_PROMPTS_HOME`, else in `$XDG_DATA_HOME/llm-prompts` or `~/.local/share/llm-prompts`. The first run copies the files of the old platform data directory there and keeps the old files. The log rotates at 10 MB and keeps 3 backups. |
| `LLM_PROMPTS_HOME` | The shared root that holds one folder per tool, shared with llm-prompts and mcp-memory. |
| `CLINE_HOOKS_FRONTEND` | Assistant name to load. Unset, it is detected from the payload. |
| `CLINE_HOOKS_PUSH_BLOCK_MARKERS` | Comma-separated file or directory names. `git push` is blocked in a repo that has one of them at or above its root. Empty by default. |
| `CLINE_HOOKS_MAX_MEMORY_MB` | Data-segment (`RLIMIT_DATA`: heap and private writable mappings, not reserved address space) cap for one hook process and the git commands it runs, in MB. Defaults to 640. A hook that runs out of memory or out of its 30 seconds of CPU time allows the tool call. |
| `CLINE_HOOKS_DEV_BIN_DIR` | Directory searched first for `cline-hook` when installing, even if it is a virtual environment. Prints a warning when used. Unset, installs use only binaries outside virtual environments. |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Any non-empty value turns on the delegation nudges. |
| `PI_CODING_AGENT_DIR` | Pi's agent directory, used by `install pi`. Defaults to `~/.pi/agent`. |
| `PI_CONTEXT_WORKTREE` | Set by pi-context for a writer delegate. The pi frontend sends it as the hook payload's `cwd` instead of pi's own `ctx.cwd`. |
| `HERDR_PANE_ID` | Read by the handoff acknowledgement plugin to find the session's own Herdr pane. |

## Commands

| Command | Does |
|---------|------|
| `cline-hook` (no arguments) | Reads one hook payload from stdin. This is what the assistants run. |
| `cline-hook install <assistant> [target] [--force]` | Registers the hooks. |
| `cline-hook uninstall <assistant> [target]` | Removes only the cline-hooks entries, leaving other tools' hooks. |
| `cline-hook plugins` | Lists loaded plugins, the extension points each owns and contributes to, whether each is enabled, and whether the plugin set validates. It exits 1 and names each plugin that failed to load on stderr. |
| `cline-hook plugins --disable <Name> [--reason <text>]` | Stops the named plugin running on any hook in every session. The reason and time show in the plugin list. Names match case-insensitively. |
| `cline-hook plugins --enable <Name>` | Lets a disabled plugin run again. It also removes the entry of a disabled plugin that is no longer installed. |
| `cline-hook retro-count --get` / `--reset` | Prints or resets the count of sessions since the last retrospective. |
| `cline-hook unlock [path]` | Drops the session's file and working tree locks, or only the lock on `path`. |
| `cline-hook handoff-ack --clear` | Releases sessions blocked on a handoff acknowledgement. |
