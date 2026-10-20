from __future__ import annotations

import json
import os
import subprocess
import sys

_SCRIPT = """
import json, sys
from cline_hooks.core.frontends import select_protocol
from cline_hooks.core.protocol import RawPayload

protocol = select_protocol(RawPayload.from_stdin(sys.argv[1]))
print(json.dumps({
    "protocol": protocol.__name__,
    "modules": sorted(name for name in sys.modules if name.startswith("cline_hooks.frontends.")),
}))
"""

_PI_PAYLOAD = json.dumps({"hook_event_name": "tool_call"})
_HEAVY_SUFFIXES = (".install", ".models", ".transcript")


def _select(payload: str, frontend: str | None) -> dict[str, object]:
    env = {key: value for key, value in os.environ.items() if key != "CLINE_HOOKS_FRONTEND"}
    if frontend is not None:
        env["CLINE_HOOKS_FRONTEND"] = frontend
    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT, payload], capture_output=True, text=True, check=True, env=env, timeout=60
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def test_a_named_frontend_is_the_only_one_imported() -> None:
    result = _select("{}", "pi")
    assert result["protocol"] == "PiProtocol"
    assert all(name.startswith("cline_hooks.frontends.pi") for name in result["modules"])  # type: ignore[attr-defined]


def test_an_unknown_name_falls_back_to_detection() -> None:
    assert _select(_PI_PAYLOAD, "no-such-frontend")["protocol"] == "PiProtocol"


def test_detection_imports_no_installer_model_or_transcript() -> None:
    result = _select(_PI_PAYLOAD, None)
    assert result["protocol"] == "PiProtocol"
    assert not [name for name in result["modules"] if name.endswith(_HEAVY_SUFFIXES)]  # type: ignore[attr-defined]
