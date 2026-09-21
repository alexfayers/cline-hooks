from __future__ import annotations

import cline_hooks


def test_main_resolves_off_the_package_root() -> None:
    assert callable(cline_hooks.main)
