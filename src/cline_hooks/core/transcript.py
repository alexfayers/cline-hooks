"""The transcript-reading capability a frontend may provide.

A hook payload names the conversation transcript it came from, but every
frontend writes that transcript in its own format - and some expose none at
all. Reading one is therefore a per-frontend capability rather than shared
logic: a frontend implements `TranscriptReader` and hangs it off its
`Protocol.transcript`, and frontends without a readable transcript keep the
`NULL_TRANSCRIPT` default, whose answers ("no token count", "no text") every
caller already handles.
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
            The context-token count, or None if it cannot be determined.
        """

    @abstractmethod
    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return the assistant text written since the last real user prompt.

        Args:
            transcript_path: Path to the transcript, as named by the payload.

        Returns:
            The assistant text for this turn, or "" if it cannot be read.
        """


class NullTranscriptReader(TranscriptReader):
    """Reader for frontends that expose no transcript in a format we can read."""

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return None - no transcript to count tokens from.

        Returns:
            None, always.
        """
        return None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return "" - no transcript to read assistant text from.

        Returns:
            An empty string, always.
        """
        return ""


NULL_TRANSCRIPT: TranscriptReader = NullTranscriptReader()
