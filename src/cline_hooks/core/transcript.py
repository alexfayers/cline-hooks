"""The transcript-reading capability a frontend may provide.

Every frontend writes its transcript in its own format, and some write none,
so a frontend hangs its own reader off `Protocol.transcript` and the rest keep
the `NULL_TRANSCRIPT` default.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TranscriptReader(ABC):
    """Reads one frontend's transcript format."""

    @abstractmethod
    def context_tokens(self, transcript_path: str) -> int | None:
        """Return the context-token count the transcript's latest turn reports.

        Args:
            transcript_path: Path to the transcript, as named by the payload.

        Returns:
            The token count, or None if it cannot be determined.
        """

    @abstractmethod
    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return the assistant text written since the last real user prompt.

        Args:
            transcript_path: Path to the transcript, as named by the payload.

        Returns:
            This turn's assistant text, or "" if it cannot be read.
        """

    def subagent_context_tokens(self, transcript_path: str, agent_id: str) -> int | None:
        """Return the context-token count from a subagent's own transcript.

        Only meaningful for a frontend that gives each subagent its own
        transcript file; a frontend without one leaves this at the default.

        Args:
            transcript_path: Path to the main session's transcript, as named
                by the payload.
            agent_id: The subagent's own agent id.

        Returns:
            The token count, or None if this frontend has no subagent
            transcript, or it cannot be determined.
        """
        return None

    def is_teammate(self, transcript_path: str) -> bool:
        """Return True if the transcript belongs to an agent-team teammate running as its own session.

        Args:
            transcript_path: Path to the transcript, as named by the payload.

        Returns:
            True for a teammate transcript, False otherwise or if it cannot be determined.
        """
        return False

    def subagent_report(self, transcript_path: str, agent_id: str) -> str:
        """Return the final report a subagent wrote in its own transcript.

        Only meaningful for a frontend that gives each subagent its own
        transcript file; a frontend without one leaves this at the default.

        Args:
            transcript_path: Path to the transcript, as named by the payload.
            agent_id: The subagent's own agent id.

        Returns:
            The subagent's report, or "" if this frontend has no subagent
            transcript, or none can be read.
        """
        return ""


class NullTranscriptReader(TranscriptReader):
    """Reader for frontends that expose no transcript in a format we can read."""

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return None - there is no transcript to read.

        Returns:
            None, always.
        """
        return None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return "" - there is no transcript to read.

        Returns:
            An empty string, always.
        """
        return ""


NULL_TRANSCRIPT: TranscriptReader = NullTranscriptReader()
