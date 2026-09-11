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
