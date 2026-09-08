"""Kiro frontend."""

from __future__ import annotations

from cline_hooks.frontends.kiro.install import install_kiro
from cline_hooks.frontends.kiro.protocol import KiroProtocol

__all__ = ["KiroProtocol", "install_kiro"]
