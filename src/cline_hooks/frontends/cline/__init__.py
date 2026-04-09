"""Cline frontend."""

from __future__ import annotations

from cline_hooks.frontends.cline.install import install_cline
from cline_hooks.frontends.cline.models import ClineHookInput
from cline_hooks.frontends.cline.parser import parse_cline_data
from cline_hooks.frontends.cline.protocol import ClineProtocol

__all__ = ["ClineHookInput", "ClineProtocol", "install_cline", "parse_cline_data"]
