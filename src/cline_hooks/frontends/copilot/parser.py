"""GitHub Copilot CLI payload spec."""

from __future__ import annotations

from pydantic import Field

from cline_hooks.core.models import PreCompactFields
from cline_hooks.core.payload import payload_model
from cline_hooks.core.vocabulary import CanonicalHook, Frontend


@payload_model(Frontend.COPILOT, CanonicalHook.PRE_COMPACT)
class CopilotPreCompact(PreCompactFields):
    """Copilot's PreCompact fields; snake_case counters alias the camelCase names."""

    conversationLength: int = Field(default=0, validation_alias="conversation_length")
    estimatedTokens: int = Field(default=0, validation_alias="estimated_tokens")
