"""Antigravity frontend."""

from __future__ import annotations

from cline_hooks.frontends.antigravity.install import install_antigravity
from cline_hooks.frontends.antigravity.parser import parse_antigravity_data
from cline_hooks.frontends.antigravity.protocol import AntigravityProtocol

__all__ = ["AntigravityProtocol", "install_antigravity", "parse_antigravity_data"]
