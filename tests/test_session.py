from __future__ import annotations

from cline_hooks.core.session import SessionContext


class TestFromCline:
    def test_uses_task_id(self) -> None:
        ctx = SessionContext.from_cline("task-123", ["/project"])
        assert ctx.session_id == "task-123"

    def test_workspace_roots(self) -> None:
        ctx = SessionContext.from_cline("t", ["/a", "/b"])
        assert ctx.workspace_roots == ["/a", "/b"]
        assert ctx.cwd == "/a"

    def test_empty_roots(self) -> None:
        ctx = SessionContext.from_cline("t", [])
        assert ctx.cwd == ""


class TestFromKiro:
    def test_deterministic_session_id(self) -> None:
        ctx1 = SessionContext.from_kiro("/project")
        ctx2 = SessionContext.from_kiro("/project")
        assert ctx1.session_id == ctx2.session_id
        assert len(ctx1.session_id) == 16

    def test_different_cwd_different_id(self) -> None:
        ctx1 = SessionContext.from_kiro("/project-a")
        ctx2 = SessionContext.from_kiro("/project-b")
        assert ctx1.session_id != ctx2.session_id

    def test_workspace_roots_from_cwd(self) -> None:
        ctx = SessionContext.from_kiro("/home/user/project")
        assert ctx.workspace_roots == ["/home/user/project"]
        assert ctx.cwd == "/home/user/project"
