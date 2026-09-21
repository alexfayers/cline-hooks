"""Per-request task_id propagation for the daemon's dedicated log file."""

from __future__ import annotations

from contextvars import ContextVar
import logging

task_id: ContextVar[str] = ContextVar("daemon_task_id", default="-")


class TaskIdFilter(logging.Filter):
    """Stamps every log record with the current request's task_id."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the current task_id to the record and always allow it through.

        Returns:
            True, unconditionally.
        """
        record.task_id = task_id.get()
        return True
