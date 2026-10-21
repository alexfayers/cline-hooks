"""Frontend-agnostic hook decision, mergeable across independent checks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


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
        updated_input: The tool's complete input as it should run, on
            frontends that can change a call's input.
        fallback_notes: Context strings shown only on frontends that cannot
            apply `updated_input`.
    """

    disposition: Disposition = Disposition.ALLOW
    notes: tuple[str, ...] = ()
    user_message: str = ""
    label: str = ""
    updated_input: Mapping[str, Any] | None = None
    fallback_notes: tuple[str, ...] = ()

    @property
    def message(self) -> str | None:
        """The notes joined for display, or None if there are none."""
        return "\n\n".join(self.notes) or None

    @property
    def labelled_message(self) -> str | None:
        """The joined notes prefixed with `label`, or None if there are none."""
        message = self.message
        return f"{self.label}: {message}" if message is not None and self.label else message

    @classmethod
    def allow(
        cls,
        *notes: str,
        label: str = "",
        user_message: str = "",
        updated_input: Mapping[str, Any] | None = None,
        fallback_note: str = "",
    ) -> Outcome:
        """Build an ALLOW outcome, dropping any empty/blank notes.

        Args:
            *notes: Context strings to inject.
            label: Prefix shown ahead of the joined notes.
            user_message: Message surfaced directly to the user.
            updated_input: The tool's complete input as it should run.
            fallback_note: Context shown only where `updated_input` cannot be applied.

        Returns:
            An ALLOW Outcome.
        """
        return cls(
            Disposition.ALLOW,
            notes=tuple(note for note in notes if note.strip()),
            user_message=user_message,
            label=label,
            updated_input=updated_input,
            fallback_notes=(fallback_note,) if fallback_note.strip() else (),
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

    def without_input_update(self) -> Outcome:
        """Drop the input update, showing the fallback notes after the labelled notes instead.

        Returns:
            An Outcome with no `updated_input`, whose notes carry the fallback context.
        """
        notes = tuple(note for note in (self.labelled_message, *self.fallback_notes) if note)
        return replace(self, notes=notes, label="", updated_input=None, fallback_notes=())

    def merge(self, other: Outcome) -> Outcome:
        """Combine this outcome with a later contributor's outcome.

        A BLOCK wins: it discards notes and input updates accumulated before
        it, and nothing after it contributes any. `user_message` accumulates
        regardless. Later input updates overwrite earlier ones key by key.

        Args:
            other: The later contributor's outcome.

        Returns:
            The merged Outcome.
        """
        user_message = "\n\n".join(part for part in (self.user_message, other.user_message) if part)
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
            Disposition.FEEDBACK if Disposition.FEEDBACK in {self.disposition, other.disposition} else Disposition.ALLOW
        )
        updated_input = None
        if self.updated_input is not None or other.updated_input is not None:
            updated_input = {**(self.updated_input or {}), **(other.updated_input or {})}
        return Outcome(
            disposition,
            notes=self.notes + other.notes,
            user_message=user_message,
            label=label,
            updated_input=updated_input,
            fallback_notes=self.fallback_notes + other.fallback_notes,
        )
