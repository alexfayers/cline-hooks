"""Claude Code frontend."""

from cline_hooks.frontends.claude_code.install import install_claude_code
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol

__all__ = ["ClaudeCodeProtocol", "install_claude_code"]
