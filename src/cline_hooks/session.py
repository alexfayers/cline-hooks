from __future__ import annotations

from dataclasses import dataclass, field
import hashlib


@dataclass(frozen=True)
class SessionContext:
    """Frontend-agnostic session information for hook handlers."""

    session_id: str
    workspace_roots: list[str] = field(default_factory=list)
    cwd: str = ""

    @classmethod
    def from_cline(cls, task_id: str, workspace_roots: list[str]) -> SessionContext:
        """Build from Cline hook input.

        Args:
            task_id: The Cline task identifier.
            workspace_roots: The workspace root paths.

        Returns:
            A SessionContext with the Cline task ID as session ID.
        """
        return cls(
            session_id=task_id,
            workspace_roots=workspace_roots,
            cwd=workspace_roots[0] if workspace_roots else "",
        )

    @classmethod
    def from_kiro(cls, cwd: str) -> SessionContext:
        """Build from Kiro hook input, synthesising a session ID from cwd.

        Args:
            cwd: The current working directory from the Kiro hook event.

        Returns:
            A SessionContext with a deterministic session ID derived from cwd.
        """
        session_id = hashlib.sha256(cwd.encode()).hexdigest()[:16]
        return cls(session_id=session_id, workspace_roots=[cwd], cwd=cwd)
