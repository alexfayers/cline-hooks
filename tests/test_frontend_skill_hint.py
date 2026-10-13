from __future__ import annotations

from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.pi.protocol import PiProtocol


def _hint(protocol: type[ClaudeCodeProtocol | PiProtocol], skills: list[str]) -> str:
    assert protocol.frontend_spec is not None
    return protocol.frontend_spec.skill_hint(skills)


def test_claude_code_names_the_skill_tool() -> None:
    assert _hint(ClaudeCodeProtocol, ["tdd", "git-tidy"]) == (
        "Skills that may fit this task: `tdd`, `git-tidy`. "
        "If one applies, load it with the Skill tool before you start. Ignore any that don't fit."
    )


def test_pi_names_each_skill_file() -> None:
    assert PiProtocol.frontend_spec is not None
    assert PiProtocol.frontend_spec.skills_dir is not None
    skills_dir = PiProtocol.frontend_spec.skills_dir()
    assert _hint(PiProtocol, ["tdd", "git-tidy"]) == (
        f"Skills that may fit this task: `tdd` (`{skills_dir}/tdd/SKILL.md`), "
        f"`git-tidy` (`{skills_dir}/git-tidy/SKILL.md`). "
        "If one applies, read it before you start. Ignore any that don't fit."
    )
