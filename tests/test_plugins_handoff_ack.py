from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.plugins.handoff_ack import HandoffAckPlugin, clear_acks

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from cline_hooks.core.plugin import HookResult

OLD_PANE = "w1:p1"
NEW_PANE = "w1:p2"
OLD_NAME = "old-session"
ACK_COMMAND = f'herdr agent prompt {OLD_PANE} "HANDOFF-ACK {OLD_PANE}"'


def _herdr_get(command: list[str], **_: object) -> MagicMock:
    targets = {OLD_PANE: OLD_PANE, OLD_NAME: OLD_PANE, NEW_PANE: NEW_PANE}
    pane_id = targets.get(command[3])
    completed = MagicMock(returncode=0)
    completed.stdout = json.dumps({"result": {"agent": {"pane_id": pane_id}}} if pane_id else {"error": {}})
    return completed


@pytest.fixture(autouse=True)
def herdr_agents(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("HERDR_PANE_ID", NEW_PANE)
    mocker.patch("cline_hooks.handlers.herdr_guard.shutil.which", return_value="/usr/bin/herdr")
    return mocker.patch("cline_hooks.handlers.herdr_guard.subprocess.run", side_effect=_herdr_get)


def _hook(hook_name: str, task_id: str = "t", **kwargs: object) -> HookResult | None:
    return HandoffAckPlugin().on_hook(hook_name, logger=logging.getLogger("test"), task_id=task_id, **kwargs)


def _prompt(message: str, task_id: str = "t") -> HookResult | None:
    return _hook(CanonicalHook.USER_PROMPT_SUBMIT, task_id, message=message)


def _pre_tool(tool_name: str, task_id: str = "t", **parameters: object) -> HookResult | None:
    return _hook(CanonicalHook.PRE_TOOL_USE, task_id, tool_name=tool_name, parameters=parameters)


def _pre_shell(command: str, task_id: str = "t") -> HookResult | None:
    return _hook(PluginScope.PRE_SHELL, task_id, command=command)


def _shell_tool(command: str, task_id: str = "t") -> HookResult | None:
    return _pre_tool(CanonicalTool.SHELL, task_id, command=command)


def _send(message: str | dict[str, str], task_id: str = "t") -> HookResult | None:
    return _pre_tool(CanonicalTool.SEND_MESSAGE, task_id, to="peer", message=message)


def _sent(message: str | dict[str, str], task_id: str = "t") -> None:
    _hook(
        PluginScope.TRACK_TOOL_USE,
        task_id,
        tool_name=CanonicalTool.SEND_MESSAGE,
        parameters={"to": "peer", "message": message},
    )


def _spawn(task: str | dict[str, str], task_id: str = "t", key: str = "task") -> HookResult | None:
    return _pre_tool(CanonicalTool.SPAWN_AGENT, task_id, **{key: task})


def _spawned(task: str | dict[str, str], task_id: str = "t", key: str = "task") -> None:
    _hook(
        PluginScope.TRACK_TOOL_USE,
        task_id,
        tool_name=CanonicalTool.SPAWN_AGENT,
        parameters={key: task},
    )


def _handoff_prompt(target: str) -> str:
    return f"HANDOFF-ACK {target}\nUse the pickup skill to resume HANDOFF.md."


HANDOFF_COMMAND = f'herdr agent prompt {NEW_PANE} "{_handoff_prompt(OLD_PANE)}"'


def _peer(body: str) -> str:
    return (
        "Another Claude session sent a message:\n"
        '<cross-session-message from="uds:/tmp/cc-socks/1.sock" from-name="old" from-mode="prompting">\n'
        f"{body}\n"
        "</cross-session-message>\n\nReply with SendMessage."
    )


def _arm(target: str = OLD_PANE, task_id: str = "t") -> None:
    _prompt(_handoff_prompt(target), task_id)


class TestNewSessionBlock:
    def test_blocks_other_tools_after_a_handoff_prompt_until_the_ack_is_sent(self) -> None:
        _arm()
        result = _pre_tool(CanonicalTool.READ, path="/x")
        assert result is not None
        assert result.block is not None
        assert f'herdr agent prompt {OLD_PANE} "HANDOFF-ACK {OLD_PANE}"' in result.block

    @pytest.mark.parametrize("marker_target", [NEW_PANE, "w9:p9", "hook."])
    def test_a_marker_not_naming_another_agent_does_not_arm_the_block(self, marker_target: str) -> None:
        _prompt(_handoff_prompt(marker_target))
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_a_marker_naming_another_agent_by_name_arms_the_block_on_its_pane(self) -> None:
        _prompt(f"HANDOFF-ACK {OLD_NAME}.\nUse the pickup skill.")
        result = _pre_tool(CanonicalTool.READ, path="/x")
        assert result is not None
        assert result.block is not None
        assert f'herdr agent prompt {OLD_NAME} "HANDOFF-ACK {OLD_NAME}"' in result.block

    def test_a_handoff_prompt_wrapped_as_a_peer_message_arms_the_block(self) -> None:
        _prompt(_peer(_handoff_prompt(OLD_PANE)))
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_a_marker_mid_body_of_a_peer_message_does_not_arm_the_block(self) -> None:
        _prompt(_peer(f"Report:\nHANDOFF-ACK {OLD_PANE}\nUse the pickup skill."))
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_allows_every_tool_when_no_handoff_prompt_arrived(self) -> None:
        _prompt("Hello")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None
        assert _shell_tool("ls") is None

    def test_blocks_non_ack_shell_commands(self) -> None:
        _arm()
        result = _shell_tool("ls")
        assert result is not None
        assert result.block is not None

    def test_the_block_message_does_not_name_the_escape_hatch(self) -> None:
        _arm()
        result = _pre_tool(CanonicalTool.READ, path="/x")
        assert result is not None
        assert result.block is not None
        assert "handoff-ack" not in result.block
        assert "--clear" not in result.block

    def test_a_quoted_report_with_the_marker_mid_text_does_not_arm_the_block(self) -> None:
        _prompt(f"Here is the report from the other session:\nHANDOFF-ACK {OLD_PANE}\nUse the pickup skill.")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_a_first_line_marker_without_a_pickup_cue_does_not_arm_the_block(self) -> None:
        _prompt(f"HANDOFF-ACK {OLD_PANE}\nThe report follows.")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_a_marker_followed_by_text_on_its_line_does_not_arm_the_block(self) -> None:
        _prompt(f"HANDOFF-ACK {OLD_PANE} was quoted in my report\nUse the pickup skill.")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_blank_lines_before_the_first_line_marker_still_arm_the_block(self) -> None:
        _prompt(f"\n{_handoff_prompt(OLD_PANE)}")
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_clearing_acks_unblocks_every_session(self) -> None:
        _arm(task_id="t1")
        _arm(task_id="t2")
        clear_acks()
        assert _pre_tool(CanonicalTool.READ, task_id="t1", path="/x") is None
        assert _pre_tool(CanonicalTool.READ, task_id="t2", path="/x") is None

    def test_allows_the_ack_command(self) -> None:
        _arm()
        assert _shell_tool(ACK_COMMAND) is None

    @pytest.mark.parametrize(
        "command",
        [
            f'herdr agent prompt {NEW_PANE} "HANDOFF-ACK {OLD_PANE}"',
            f'herdr agent prompt {OLD_PANE} "hello"',
            f'herdr agent prompt {OLD_PANE} "HANDOFF-ACK {OLD_PANE}" && rm x',
            f'herdr agent prompt {OLD_PANE} "HANDOFF-ACK {OLD_PANE}"; ls',
        ],
    )
    def test_blocks_a_command_that_is_not_exactly_the_ack(self, command: str) -> None:
        _arm()
        result = _shell_tool(command)
        assert result is not None
        assert result.block is not None

    def test_unblocks_once_the_ack_command_succeeded(self) -> None:
        _arm()
        _hook(PluginScope.TRACK_TOOL_USE, tool_name=CanonicalTool.SHELL, parameters={"command": ACK_COMMAND})
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_stays_blocked_after_an_unrelated_tool_was_tracked(self) -> None:
        _arm()
        _hook(PluginScope.TRACK_TOOL_USE, tool_name=CanonicalTool.SHELL, parameters={"command": "ls"})
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_another_session_is_not_blocked(self) -> None:
        _arm(task_id="t1")
        assert _pre_tool(CanonicalTool.READ, task_id="t2", path="/x") is None

    @pytest.mark.parametrize("hook_name", [CanonicalHook.TASK_COMPLETE, CanonicalHook.TASK_CANCEL])
    def test_ending_the_session_clears_the_obligation(self, hook_name: str) -> None:
        _arm()
        _hook(hook_name)
        assert _pre_tool(CanonicalTool.READ, path="/x") is None


class TestOldSessionTabClose:
    @pytest.fixture(autouse=True)
    def sender_pane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERDR_PANE_ID", OLD_PANE)

    def test_a_pasted_ack_releases_the_tab_even_with_text_around_the_marker(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt(f"HANDOFF-ACK {OLD_PANE} - pickup confirmed. Plan: read HANDOFF.md.")
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_a_prose_prompt_quoting_the_marker_to_another_pane_does_not_rearm_a_released_tab(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt(f"HANDOFF-ACK {OLD_PANE}")
        _pre_shell(f'herdr agent prompt w9:p9 "FYI the first line was HANDOFF-ACK {OLD_PANE} and pickup ran"')
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_blocks_closing_the_tab_after_sending_a_handoff_until_the_ack_arrives(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        result = _pre_shell("herdr tab close w1:t1")
        assert result is not None
        assert result.block is not None
        assert f"HANDOFF-ACK {OLD_PANE}" in result.block

    def test_a_handoff_sent_through_a_printf_subshell_blocks_closing_the_tab(self) -> None:
        printf_prompt = f"$(printf 'HANDOFF-ACK {OLD_PANE}\\nUse the pickup skill.'; cat f)"
        _pre_shell(f'herdr agent prompt {NEW_PANE} "{printf_prompt}"')
        assert _pre_shell("herdr tab close w1:t1") is not None

    @pytest.mark.parametrize(
        "prompt",
        [
            "HANDOFF-ACK w9:p9\nUse the pickup skill.",
            f"HANDOFF-ACK {OLD_PANE}\nThe report follows.",
            "Please carry HANDOFF-ACK and deadlock details\nUse the pickup skill.",
        ],
    )
    def test_a_prompt_that_is_not_a_handoff_naming_this_pane_does_not_block_closing_the_tab(self, prompt: str) -> None:
        _pre_shell(f'herdr agent prompt {NEW_PANE} "{prompt}"')
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_clearing_acks_releases_every_awaiting_tab_close(self) -> None:
        _pre_shell(HANDOFF_COMMAND, task_id="t1")
        _pre_shell(HANDOFF_COMMAND, task_id="t2")
        clear_acks()
        assert _pre_shell("herdr tab close w1:t1", task_id="t1") is None
        assert _pre_shell("herdr tab close w1:t1", task_id="t2") is None

    def test_allows_closing_the_tab_when_no_handoff_was_sent(self) -> None:
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_allows_closing_the_tab_once_the_ack_prompt_arrives(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt(f"HANDOFF-ACK {OLD_PANE}")
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_an_ack_does_not_arm_the_new_session_block_in_the_sender(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt(f"HANDOFF-ACK {OLD_PANE}")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_an_ack_for_another_pane_does_not_release_the_tab(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt("HANDOFF-ACK w9:p9")
        assert _pre_shell("herdr tab close w1:t1") is not None

    def test_sending_the_ack_does_not_record_a_pending_handoff(self) -> None:
        _pre_shell(ACK_COMMAND)
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_subagents_closing_the_tab_are_blocked_by_the_parent_session(self) -> None:
        _pre_shell(HANDOFF_COMMAND, task_id="t")
        assert _pre_shell("herdr tab close w1:t1", task_id="t:agent1") is not None

    @pytest.mark.parametrize("hook_name", [CanonicalHook.TASK_COMPLETE, CanonicalHook.TASK_CANCEL])
    def test_ending_the_session_clears_the_pending_handoff(self, hook_name: str) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _hook(hook_name)
        assert _pre_shell("herdr tab close w1:t1") is None


class TestPeerMessageHandoff:
    @pytest.fixture(autouse=True)
    def sender_pane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERDR_PANE_ID", OLD_PANE)

    def test_a_handoff_sent_as_a_peer_message_blocks_closing_the_tab_until_the_ack_arrives(self) -> None:
        assert _send(_handoff_prompt(OLD_PANE)) is None
        result = _pre_shell("herdr tab close w1:t1")
        assert result is not None
        assert result.block is not None
        assert f"HANDOFF-ACK {OLD_PANE}" in result.block

    def test_a_message_whose_marker_names_another_pane_records_no_handoff(self) -> None:
        _send(_handoff_prompt(NEW_PANE))
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_a_message_mentioning_the_own_marker_in_prose_records_no_handoff(self) -> None:
        _send(f"FYI the first line was HANDOFF-ACK {OLD_PANE} and the receiver ran pickup")
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_an_object_message_records_no_handoff(self) -> None:
        _send({"type": "shutdown_request", "reason": f"HANDOFF-ACK {OLD_PANE}"})
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_a_peer_message_ack_releases_the_tab(self) -> None:
        _send(_handoff_prompt(OLD_PANE))
        _prompt(_peer(f"HANDOFF-ACK {OLD_PANE}"))
        assert _pre_shell("herdr tab close w1:t1") is None

    def test_a_peer_message_ack_for_another_pane_keeps_the_tab_blocked(self) -> None:
        _send(_handoff_prompt(OLD_PANE))
        _prompt(_peer("HANDOFF-ACK w9:p9"))
        assert _pre_shell("herdr tab close w1:t1") is not None

    def test_a_peer_message_ack_releases_a_handoff_sent_through_the_shell(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        _prompt(_peer(f"HANDOFF-ACK {OLD_PANE}"))
        assert _pre_shell("herdr tab close w1:t1") is None


class TestPeerMessageAck:
    def test_sending_the_ack_by_message_is_allowed_while_it_is_owed(self) -> None:
        _arm()
        assert _send(f"HANDOFF-ACK {OLD_PANE}") is None

    @pytest.mark.parametrize(
        "message",
        ["hello", "HANDOFF-ACK w9:p9", {"type": "shutdown_request", "reason": f"HANDOFF-ACK {OLD_PANE}"}],
    )
    def test_any_other_message_is_blocked_while_the_ack_is_owed(self, message: str | dict[str, str]) -> None:
        _arm()
        result = _send(message)
        assert result is not None
        assert result.block is not None

    def test_the_ack_message_releases_the_block_once_sent(self) -> None:
        _arm()
        _sent(f"HANDOFF-ACK {OLD_PANE}")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_a_sent_message_that_is_not_the_ack_keeps_the_block(self) -> None:
        _arm()
        _sent("hello")
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_sending_the_ack_by_message_records_no_pending_handoff(self) -> None:
        _arm()
        _send(f"HANDOFF-ACK {OLD_PANE}")
        _sent(f"HANDOFF-ACK {OLD_PANE}")
        assert _pre_shell("herdr tab close w1:t1") is None


class TestSubagentAck:
    @pytest.mark.parametrize("key", ["task", "prompt"])
    def test_a_spawn_whose_task_carries_the_ack_command_is_allowed_while_it_is_owed(self, key: str) -> None:
        _arm()
        assert _spawn(f"Run exactly: {ACK_COMMAND}", key=key) is None

    @pytest.mark.parametrize(
        "task",
        [
            "hello",
            f"Reply HANDOFF-ACK {OLD_PANE}",
            'herdr agent prompt w9:p9 "HANDOFF-ACK w9:p9"',
            {"note": ACK_COMMAND},
        ],
    )
    def test_any_other_spawn_is_blocked_while_the_ack_is_owed(self, task: str | dict[str, str]) -> None:
        _arm()
        result = _spawn(task)
        assert result is not None
        assert result.block is not None

    def test_a_spawn_carrying_the_ack_command_releases_the_block_once_tracked(self) -> None:
        _arm()
        _spawned(f"Run exactly: {ACK_COMMAND}")
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_a_spawn_without_the_ack_command_keeps_the_block(self) -> None:
        _arm()
        _spawned("hello")
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_a_failed_spawn_keeps_the_block(self) -> None:
        _arm()
        _hook(
            PluginScope.TOOL_FAILED,
            tool_name=CanonicalTool.SPAWN_AGENT,
            parameters={"task": f"Run exactly: {ACK_COMMAND}"},
        )
        assert _pre_tool(CanonicalTool.READ, path="/x") is not None

    def test_a_shell_less_lead_acknowledges_through_a_subagent_without_deadlocking(self) -> None:
        _arm(task_id="lead")
        assert _pre_tool(CanonicalTool.READ, task_id="lead", path="/x") is not None
        assert _spawn(f"Run exactly: {ACK_COMMAND}", task_id="lead") is None
        assert _shell_tool(ACK_COMMAND, task_id="delegate") is None
        assert _pre_shell(ACK_COMMAND, task_id="delegate") is None
        _spawned(f"Run exactly: {ACK_COMMAND}", task_id="lead")
        assert _pre_tool(CanonicalTool.READ, task_id="lead", path="/x") is None

    def test_a_same_session_subagent_may_run_the_ack_and_releases_its_session(self) -> None:
        _arm()
        assert _spawn(f"Run exactly: {ACK_COMMAND}") is None
        assert _pre_tool(CanonicalTool.READ, task_id="t:agent1", path="/x") is not None
        assert _shell_tool(ACK_COMMAND, task_id="t:agent1") is None
        _hook(
            PluginScope.TRACK_TOOL_USE,
            "t:agent1",
            tool_name=CanonicalTool.SHELL,
            parameters={"command": ACK_COMMAND},
        )
        assert _pre_tool(CanonicalTool.READ, path="/x") is None

    def test_the_block_message_offers_the_subagent_path(self) -> None:
        _arm()
        result = _pre_tool(CanonicalTool.READ, path="/x")
        assert result is not None
        assert result.block is not None
        assert "subagent" in result.block


class TestClearIsUserOnly:
    @pytest.mark.parametrize(
        "command",
        [
            "cline-hook handoff-ack --clear",
            "cline-hook handoff-ack",
            "uv run cline-hook handoff-ack --clear",
            "/x/.venv/bin/cline-hook handoff-ack --clear",
            "cd /x && uv run --project /y cline-hook handoff-ack --clear",
            "uvx cline-hook handoff-ack --clear",
        ],
    )
    def test_blocks_an_agent_running_the_clear_command(self, command: str) -> None:
        result = _pre_shell(command)
        assert result is not None
        assert result.block is not None

    def test_blocks_an_agent_awaiting_an_ack_from_running_the_clear_command(self) -> None:
        _pre_shell(HANDOFF_COMMAND)
        result = _pre_shell("cline-hook handoff-ack --clear")
        assert result is not None
        assert result.block == "Only the user may clear handoff acknowledgements. MUST NOT run this command."

    @pytest.mark.parametrize("command", ["ls", "rg handoff-ack src", 'git commit -m "document cline-hook handoff-ack"'])
    def test_allows_commands_that_only_mention_the_clear_command(self, command: str) -> None:
        assert _pre_shell(command) is None
