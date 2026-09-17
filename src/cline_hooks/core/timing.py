"""Return the current local time for the UserPromptSubmit TIME note."""

from __future__ import annotations

from datetime import datetime

TIME_FORMAT = "%a %d %b %Y %H:%M %Z"


def local_now() -> datetime:
    """Return the current local time, timezone-aware.

    Returns:
        The current local wall-clock time with timezone info attached.
    """
    return datetime.now().astimezone()
