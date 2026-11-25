from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from cline_hooks._main import _run_hook
from cline_hooks.core.plugin import plugins_override
from cline_hooks.plugins.bash_timeout import DEFAULT_BASH_TIMEOUT_SECONDS, BashTimeoutPlugin

PI_CALL = {"hook_event_name": "tool_call", "tool_name": "bash", "agent_id": "x"}
CLAUDE_CALL = {"hook_event_name": "PreToolUse", "tool_name": "Bash"}


def _run(capsys: pytest.CaptureFixture[str], call: dict[str, str], tool_input: dict[str, object]) -> str:
    payload = {"session_id": "s1", "cwd": "/tmp", **call, "tool_input": tool_input}
    with (
        plugins_override([BashTimeoutPlugin()]),
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    return capsys.readouterr().out


def test_pi_bash_call_without_a_timeout_gets_the_default_beside_its_command(capsys: pytest.CaptureFixture[str]) -> None:
    output = json.loads(_run(capsys, PI_CALL, {"command": "ls"}))
    assert output["updated_input"] == {"command": "ls", "timeout": DEFAULT_BASH_TIMEOUT_SECONDS}


def test_pi_bash_call_keeps_its_own_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, PI_CALL, {"command": "ls", "timeout": 5}) == ""


def test_other_frontends_are_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, CLAUDE_CALL, {"command": "ls"}) == ""
