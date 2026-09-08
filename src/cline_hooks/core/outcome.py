"""Frontend-agnostic hook decision, mergeable across independent checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Disposition(StrEnum):
    """The three ways a hook handler can resolve a tool call."""

    ALLOW = "allow"
    BLOCK = "block"
    FEEDBACK = "feedback"


@dataclass(frozen=True, slots=True)
class Outcome:
    """A hook handler's decision, ready to merge with other contributors.

    Attributes:
        disposition: How the tool call should be resolved.
        notes: Context strings to inject into the model-facing response.
        user_message: Message surfaced directly to the user on frontends that
            support a user channel.
        label: Prefix shown ahead of the joined notes.
    """

    disposition: Disposition = Disposition.ALLOW
    notes: tuple[str, ...] = ()
    user_message: str = ""
    label: str = ""

    @property
    def message(self) -> str | None:
        """Return the notes joined for display, or None if there are none."""
        return "\n\n".join(self.notes) or None

    @classmethod
    def allow(cls, *notes: str, label: str = "", user_message: str = "") -> Outcome:
        """Build an ALLOW outcome, dropping any empty/blank notes.

        Args:
            *notes: Context strings to inject.
            label: Prefix shown ahead of the joined notes.
            user_message: Message surfaced directly to the user.

        Returns:
            An ALLOW Outcome.
        """
        return cls(
            Disposition.ALLOW,
            notes=tuple(note for note in notes if note.strip()),
            user_message=user_message,
            label=label,
        )

    @classmethod
    def block(cls, reason: str, *, label: str = "") -> Outcome:
        """Build a BLOCK outcome with the given reason as its single note.

        Args:
            reason: Why the tool call is being blocked.
            label: Prefix shown ahead of the reason.

        Returns:
            A BLOCK Outcome.
        """
        return cls(Disposition.BLOCK, notes=(reason,), label=label)

    @classmethod
    def feedback(cls, message: str, *, label: str = "") -> Outcome:
        """Build a FEEDBACK outcome with the given message as its single note.

        Args:
            message: Non-error feedback to continue the conversation with.
            label: Prefix shown ahead of the message.

        Returns:
            A FEEDBACK Outcome.
        """
        return cls(Disposition.FEEDBACK, notes=(message,), label=label)

    def merge(self, other: Outcome) -> Outcome:
        """Combine this outcome with a later contributor's outcome.

        `self` is the earlier contributor. A BLOCK always wins: once one has
        occurred, nothing after it contributes notes, and a BLOCK discards
        whatever notes were accumulated before it. `user_message` always
        accumulates, even across a BLOCK.

        Args:
            other: The later contributor's outcome.

        Returns:
            The merged Outcome.
        """
        user_message = "\n\n".join(
            part for part in (self.user_message, other.user_message) if part
        )
        label = self.label or other.label

        if self.disposition is Disposition.BLOCK:
            return self

        if other.disposition is Disposition.BLOCK:
            return Outcome(
                Disposition.BLOCK,
                notes=other.notes,
                user_message=user_message,
                label=label,
            )

        disposition = (
            Disposition.FEEDBACK
            if Disposition.FEEDBACK in (self.disposition, other.disposition)
            else Disposition.ALLOW
        )
        return Outcome(
            disposition,
            notes=self.notes + other.notes,
            user_message=user_message,
            label=label,
        )
