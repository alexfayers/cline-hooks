from __future__ import annotations

import io
import json
import logging
from pathlib import Path
import re
import shutil
import stat
import subprocess
from unittest.mock import patch

import pytest

from cline_hooks._main import _run_hook
from cline_hooks.core.plugin import HookResult, plugins_override
from cline_hooks.core.protocol import Protocol, set_protocol
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.frontends.codex.protocol import CodexProtocol
from cline_hooks.frontends.pi import PiProtocol
from cline_hooks.plugins.build_redirect import BuildRedirectPlugin
from cline_hooks.plugins.build_tools import BuildToolsPlugin

PI_CALL = {"hook_event_name": "tool_call", "tool_name": "bash", "agent_id": "x"}
BASH = shutil.which("bash") or "bash"


def _hook_output(capsys: pytest.CaptureFixture[str], command: str) -> dict[str, object] | None:
    payload = {"session_id": "s1", "cwd": "/tmp", **PI_CALL, "tool_input": {"command": command, "timeout": 5}}
    with (
        plugins_override([BuildToolsPlugin(), BuildRedirectPlugin()]),
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    output = capsys.readouterr().out
    return json.loads(output) if output else None


def _rewritten(capsys: pytest.CaptureFixture[str], command: str) -> str:
    output = _hook_output(capsys, command)
    assert output is not None
    updated = output["updated_input"]
    assert isinstance(updated, dict)
    assert updated["timeout"] == 5
    return str(updated["command"])


def _run_in_shell(command: str, build_status: int = 3) -> subprocess.CompletedProcess[str]:
    script = f"just() {{ echo out; echo err >&2; echo done; return {build_status}; }}; {command}"
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, check=False)


def test_build_piped_into_a_filter_is_redirected_to_a_log_the_filter_reads(capsys: pytest.CaptureFixture[str]) -> None:
    command = _rewritten(capsys, "just test 2>&1 | tail -n 2")
    pattern = r"\{ .*just test 2>&1 > (\S+) 2>&1 \|\| build_status=\$\?; tail -n 2 < (\S+) \|\| .*\}"
    match = re.fullmatch(pattern, command)
    assert match is not None
    assert match[1] == match[2]
    result = _run_in_shell(command)
    assert result.stdout == "err\ndone\n"
    assert Path(match[1]).read_text(encoding="utf-8") == "out\nerr\ndone\n"


def test_the_rewritten_command_exits_with_the_builds_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_in_shell(_rewritten(capsys, "just | tail -n 1")).returncode == 3


def test_a_failing_filter_fails_a_passing_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_in_shell(_rewritten(capsys, "just | grep nothing"), build_status=0).returncode == 1


def test_each_run_gets_its_own_log_in_a_private_directory(capsys: pytest.CaptureFixture[str]) -> None:
    commands = [_rewritten(capsys, "just | tail") for _ in range(2)]
    logs = [Path(str(re.search(r"> (\S+\.log)", command)[1])) for command in commands]  # type: ignore[index]
    assert logs[0] != logs[1]
    assert all(stat.S_IMODE(log.parent.stat().st_mode) == 0o700 for log in logs)


def _on_hook(command: str, protocol: Protocol) -> HookResult | None:
    set_protocol(protocol)
    kwargs = {"command": command, "parameters": {"command": command}}
    with plugins_override([BuildToolsPlugin()]):
        return BuildRedirectPlugin().on_hook(PluginScope.PRE_SHELL, logger=logging.getLogger(), **kwargs)


def test_a_frontend_that_cannot_rewrite_the_command_gets_the_block_with_redirect_instructions() -> None:
    result = _on_hook("just | tail", CodexProtocol())
    assert result is not None
    assert result.updated_input is None
    assert result.block is not None
    assert "> <log file> 2>&1" in result.block


def test_a_failed_build_still_shows_the_filtered_output_under_set_e(capsys: pytest.CaptureFixture[str]) -> None:
    result = _run_in_shell(f"set -e; {_rewritten(capsys, 'just | tail -n 1')}; echo after")
    assert (result.stdout, result.returncode) == ("done\n", 3)


def test_a_filter_with_no_match_does_not_stop_a_failed_build_under_set_e(capsys: pytest.CaptureFixture[str]) -> None:
    result = _run_in_shell(f"set -e; {_rewritten(capsys, 'just | grep nothing')}; echo after")
    assert (result.stdout, result.returncode) == ("", 3)


@pytest.mark.parametrize(
    "command",
    ["just 2>build.err | tail", "just | tail > summary.txt", "just &> all.log | grep x", "just | grep x | cat"],
)
def test_a_pipeline_that_is_not_a_plain_build_into_a_filter_is_blocked(command: str) -> None:
    result = _on_hook(command, PiProtocol())
    assert result is not None
    assert result.updated_input is None
    assert result.block is not None
    assert "> <log file> 2>&1" in result.block


def test_the_note_names_the_log(capsys: pytest.CaptureFixture[str]) -> None:
    output = _hook_output(capsys, "just | grep out")
    assert output is not None
    log = re.search(r"Full output: (\S+\.log)", str(output["message"]))
    assert log is not None
    assert log[1] in str(output["updated_input"])


def test_the_rewrite_keeps_the_command_around_the_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    command = _rewritten(capsys, "cd /tmp && just | grep -c out; echo end")
    assert _run_in_shell(command).stdout == "1\nend\n"


def test_two_builds_in_one_command_get_their_own_logs(capsys: pytest.CaptureFixture[str]) -> None:
    command = _rewritten(capsys, "just | head -n 1; just | tail -n 1")
    assert len(set(re.findall(r"build-\d+\.log", command))) == 2
    assert _run_in_shell(command).stdout == "out\ndone\n"


@pytest.mark.parametrize(
    "command",
    [
        "ps aux | grep python",
        "just --help | head",
        "just build | grep x package.json",
        "just build > build.log; grep x build.log",
        "just build | cat",
        "just build",
        "echo $(just | tail)",
        "just | tail <<EOF",
    ],
)
def test_other_commands_are_left_alone(capsys: pytest.CaptureFixture[str], command: str) -> None:
    assert _hook_output(capsys, command) is None
