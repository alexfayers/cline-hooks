"""Cline input parser."""

from __future__ import annotations

import json
from typing import Any, cast

from cline_hooks.core.models import HookInput, _filter_fields, inheritors


def parse_cline_data(raw_data: str) -> HookInput:
    """Parse raw JSON from Cline into a typed HookInput subclass.

    Args:
        raw_data: The raw JSON string from Cline.

    Returns:
        The most specific matching HookInput subclass.
    """
    data: dict[str, Any] = json.loads(raw_data)
    hook_name = data.get("hookName")

    for subclass in inheritors(HookInput):
        if getattr(subclass, "hookName", None) == hook_name:
            return cast("HookInput", subclass(**_filter_fields(subclass, data)))

    return HookInput(**_filter_fields(HookInput, data))
