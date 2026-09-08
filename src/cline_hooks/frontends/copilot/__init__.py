"""GitHub Copilot (VS Code) frontend."""

from cline_hooks.frontends.copilot.install import install_copilot
from cline_hooks.frontends.copilot.protocol import CopilotProtocol

__all__ = ["CopilotProtocol", "install_copilot"]
