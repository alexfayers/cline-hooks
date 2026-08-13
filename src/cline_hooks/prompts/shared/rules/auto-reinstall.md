# Auto-reinstall

When you edit steering files, skills, or workflow source files, `llm-prompts update` runs automatically via the auto-reinstall hook. You do not need to run it manually.

The hook watches all files tracked in the `~/.config/llm-prompts/installed.json` manifest. When a write to one of them is detected, it throttles to at most once every 5 seconds (via a stamp file, not a delay timer) and runs `llm-prompts update` synchronously, blocking briefly (up to a 30s timeout) before the tool call result returns.
