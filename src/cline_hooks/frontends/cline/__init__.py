"""Cline frontend."""

from __future__ import annotations

from cline_hooks.frontends.cline.install import install_cline
from cline_hooks.frontends.cline.protocol import ClineProtocol

__all__ = ["ClineProtocol", "install_cline"]
