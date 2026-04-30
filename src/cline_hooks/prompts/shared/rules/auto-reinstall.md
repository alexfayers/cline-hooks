# Auto-reinstall

When you edit steering files, skills, or workflow source files, `llm-prompts update` runs automatically via the auto-reinstall hook. You do not need to run it manually.

The hook watches all files tracked in the `~/.config/llm-prompts/installed.json` manifest. When a write is detected, it debounces (5s) and runs `llm-prompts update` in the background.
