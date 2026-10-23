from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

HARNESS = Path(__file__).parent / "pi_extension_harness.mjs"
TEMPLATE = Path(__file__).parents[1] / "src" / "cline_hooks" / "frontends" / "pi" / "extension.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _run_extension(tmp_path: Path, hook_stdout: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    binary = tmp_path / "cline-hook"
    binary.write_text(
        f"#!/bin/sh\ncase \"$(cat)\" in *'\"hook_event_name\":\"tool_call\"'*) printf '%s' '{hook_stdout}';;"
        ' *\'"source":"compact"\'*) printf recap;;'
        ' *\'"source":"startup"\'*) printf \'{"message":"ctx","system_message":"hello %s"}\' $CLINE_HOOKS_FRONTEND;;'
        " esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    script = tmp_path / "cline-hooks.ts"
    script.write_text(TEMPLATE.read_text(encoding="utf-8").replace("__CLINE_HOOK_BINARY__", str(binary)))
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(tool_input), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(HARNESS), str(script), str(input_file)],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def test_the_updated_input_is_copied_into_the_tool_input(tmp_path: Path) -> None:
    hook_stdout = json.dumps({"updated_input": {"task": "do it. hint"}, "message": "ctx"})
    result = _run_extension(tmp_path, hook_stdout, {"task": "do it", "definition": "worker"})
    assert result["input"] == {"task": "do it. hint", "definition": "worker"}
    assert result["content"][-1]["text"] == "ctx"


def test_plain_text_context_leaves_the_tool_input_alone(tmp_path: Path) -> None:
    result = _run_extension(tmp_path, "REMINDER: plain", {"task": "do it"})
    assert result["input"] == {"task": "do it"}
    assert result["content"][-1]["text"] == "REMINDER: plain"
    assert result["structuredContent"] == {"ok": True}


def test_a_compaction_is_relayed_as_a_compact_task_start(tmp_path: Path) -> None:
    assert _run_extension(tmp_path, "", {"task": "do it"})["queued"][-1] == "recap"


def test_a_session_start_user_message_is_shown_and_its_context_queued(tmp_path: Path) -> None:
    result = _run_extension(tmp_path, "", {"task": "do it"})
    assert result["notified"] == ["hello pi"]
    assert "ctx" in result["queued"]
