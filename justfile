@_default: lint type-check test

@_uv:
    uv -V 2> /dev/null || { echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'; exit 1;}

lint: _uv
    uv run ruff check --fix --show-fixes src/ tests/
    uv run ruff format src/ tests/

lint-check: _uv
    uv run ruff check src/ tests/

type-check: _uv
    uv run mypy src/ tests/

@_pnpm:
    pnpm install --frozen-lockfile --silent

ts-lint: _pnpm
    pnpm exec biome check src/cline_hooks/frontends/pi/extension.ts src/cline_hooks/frontends/opencode/plugin.ts

ts-type-check: _pnpm
    pnpm exec tsc -p tsconfig.json

test: _uv
    uv run pytest -vv --nf

test-cov: _uv
    uv run coverage run -m pytest -vv --nf -s
    uv run coverage report --show-missing

# Records the Claude Code hook entries before the upgrade smoke test.
upgrade-seed:
    #!/bin/sh
    set -eu
    settings="$HOME/.claude/settings.json"
    record="${XDG_STATE_HOME:-$HOME/.local/state}/cline-hooks-upgrade-smoke/hooks.json"
    if ! jq -e '[.hooks[]?[]?.hooks[]? | select(.type == "command")] | length > 0' "$settings" > /dev/null; then
        echo "upgrade-seed: $settings has no hook commands. Run 'cline-hook install claude-code' first." >&2
        exit 1
    fi
    mkdir -p "$(dirname "$record")"
    jq '.hooks' "$settings" > "$record"
    echo "upgrade-seed: recorded the hook entries of $settings in $record"

# Checks that every Claude Code hook command still exists and accepts a PreToolUse payload.
upgrade-smoke:
    #!/bin/sh
    set -eu
    settings="$HOME/.claude/settings.json"
    record="${XDG_STATE_HOME:-$HOME/.local/state}/cline-hooks-upgrade-smoke/hooks.json"
    fail() { echo "upgrade-smoke: $*" >&2; exit 1; }
    [ -f "$record" ] || fail "$record is missing. Run 'just upgrade-seed' first."
    missing="$(jq -r --slurpfile now "$settings" 'keys[] | select(($now[0].hooks[.] // []) | length == 0)' "$record")"
    [ -z "$missing" ] || fail "$settings lost the hook events: $(echo $missing)"
    commands="$(jq -r '[.hooks[]?[]?.hooks[]? | select(.type == "command") | .command] | unique[]' "$settings")"
    [ -n "$commands" ] || fail "$settings has no hook commands."
    payload="$(jq -cn --arg cwd "$PWD" '{session_id: "upgrade-smoke", transcript_path: "", cwd: $cwd, hook_event_name: "PreToolUse", tool_name: "Read", tool_input: {file_path: ($cwd + "/README.md")}}')"
    echo "$commands" | while IFS= read -r command; do
        set -f
        set -- $command
        set +f
        while [ $# -gt 0 ]; do
            case "$1" in *=*) shift ;; *) break ;; esac
        done
        [ $# -gt 0 ] || fail "the hook command '$command' names no program."
        case "$1" in
            */*) [ -f "$1" ] && [ -x "$1" ] || fail "the hook command '$command' runs $1, which is missing or not executable." ;;
            *) command -v "$1" > /dev/null || fail "the hook command '$command' runs $1, which is not on PATH." ;;
        esac
        if ! output="$(printf '%s' "$payload" | sh -c "$command" 2>&1)"; then
            printf '%s\n' "$output" >&2
            fail "the hook command '$command' failed on a PreToolUse payload."
        fi
        echo "upgrade-smoke: ok: $command"
    done
