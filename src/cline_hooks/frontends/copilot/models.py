"""GitHub Copilot's payload models: where its raw hook JSON differs from canonical."""

from __future__ import annotations

from pydantic import Field

from cline_hooks.core.models import PreCompactFields


class CopilotPreCompact(PreCompactFields):
    """Copilot's PreCompact fields; snake_case counters alias the camelCase names."""

    conversationLength: int = Field(default=0, validation_alias="conversation_length")
    estimatedTokens: int = Field(default=0, validation_alias="estimated_tokens")
