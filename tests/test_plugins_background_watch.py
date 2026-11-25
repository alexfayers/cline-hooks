from __future__ import annotations

import io
import json
import subprocess
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks._main import _run_hook
from cline_hooks.core.plugin import HookResult, HooksPlugin, load_plugins, plugins_override
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.plugins.background_watch import BackgroundWatchPlugin

if TYPE_CHECKING:
    import logging
    from pathlib import Path

FORK_CALL = {"hook_event_name": "tool_call", "tool_name": "bash", "agent_id": "x"}
WATCH = "llm-prompts watch cmd 'sleep 1' --until ok"


def _run(
    capsys: pytest.CaptureFixture[str], call: dict[str, str], command: str, *, plugins: list[HooksPlugin] | None = None
) -> tuple[str, str]:
    payload = {"session_id": "s1", "cwd": "/tmp", **call, "tool_input": {"command": command, "timeout": 5}}
    with (
        plugins_override(plugins or [BackgroundWatchPlugin()]),
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    captured = capsys.readouterr()
    return captured.out, captured.err


def test_a_forks_foreground_watch_returns_at_once_and_keeps_running(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    marker = tmp_path / "ran"
    out, _ = _run(capsys, FORK_CALL, f"llm-prompts() {{ sleep 1; touch {marker}; }}; llm-prompts watch cmd")
    updated = json.loads(out)["updated_input"]
    assert isinstance(updated, dict)
    assert updated["timeout"] == 5
    result = subprocess.run(["bash", "-c", updated["command"]], capture_output=True, text=True, timeout=5, check=True)  # ruff: ignore[start-process-with-partial-path]
    assert "background" in result.stdout
    assert not marker.exists()
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists()


def test_the_main_agents_watch_is_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, {**FORK_CALL, "agent_id": ""}, WATCH) == ("", "")


@pytest.mark.parametrize("command", ["ls", "echo llm-prompts watch", "llm-prompts install"])
def test_other_fork_commands_are_unchanged(capsys: pytest.CaptureFixture[str], command: str) -> None:
    assert _run(capsys, FORK_CALL, command) == ("", "")


def test_a_chained_command_the_guards_block_is_still_blocked(capsys: pytest.CaptureFixture[str]) -> None:
    out, err = _run(capsys, FORK_CALL, "rm -f x; llm-prompts watch cmd", plugins=load_plugins())
    assert "updated_input" not in out
    assert "rm -f is not allowed" in err


def test_an_external_guard_after_the_rewrite_in_the_plugin_list_still_sees_the_original_batch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: list[str] = []

    class Guard(HooksPlugin):
        def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
            if hook_name == PluginScope.PRE_SHELL:
                seen.append(str(kwargs["command"]))
            return None

    command = "echo first; llm-prompts watch cmd"
    out, _ = _run(capsys, FORK_CALL, command, plugins=[BackgroundWatchPlugin(), Guard()])
    assert seen == [command]
    assert "updated_input" in out
