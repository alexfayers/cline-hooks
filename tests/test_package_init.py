from __future__ import annotations

import subprocess
import sys

_HEAVY_PREFIXES = (
    "cline_hooks.handlers",
    "cline_hooks.plugins",
    "cline_hooks.core.frontends",
    "cline_hooks.core.dispatch",
    "cline_hooks.frontends",
    "pydantic",
)


def test_importing_the_package_root_stays_light() -> None:
    script = (
        "import sys\n"
        "import cline_hooks\n"
        f"heavy = [name for name in sys.modules if name.startswith({_HEAVY_PREFIXES!r})]\n"
        "print(','.join(sorted(heavy)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == ""


def test_main_is_still_reachable_off_the_package_root() -> None:
    script = "import cline_hooks\nassert callable(cline_hooks.main)\n"
    subprocess.run([sys.executable, "-c", script], check=True, timeout=10)


def test_accessing_an_unknown_attribute_still_raises() -> None:
    script = "import cline_hooks\ncline_hooks.not_a_real_attribute\n"
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "AttributeError" in result.stderr
