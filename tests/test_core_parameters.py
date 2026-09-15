from __future__ import annotations

import logging

import pytest

from cline_hooks.core.parameters import (
    PARAMETER_MODELS,
    FileEditParameters,
    McpToolUse,
    ReadParameters,
    ShellParameters,
    SkillParameters,
    ToolParameters,
    WebResearchParameters,
    parameter_model,
    parameters_for,
)
from cline_hooks.core.vocabulary import CanonicalTool


class TestRegistry:
    def test_shared_tools_resolve_to_the_same_model(self) -> None:
        assert PARAMETER_MODELS[CanonicalTool.EDIT] is FileEditParameters
        assert PARAMETER_MODELS[CanonicalTool.WRITE] is FileEditParameters
        assert PARAMETER_MODELS[CanonicalTool.WEB_FETCH] is WebResearchParameters
        assert PARAMETER_MODELS[CanonicalTool.WEB_SEARCH] is WebResearchParameters
        assert PARAMETER_MODELS[CanonicalTool.MCP] is McpToolUse

    def test_external_registration_is_reachable(self) -> None:
        before = dict(PARAMETER_MODELS)
        try:

            @parameter_model(CanonicalTool.SPAWN_AGENT)
            class _ExternalParameters(ToolParameters):
                """A parameter model registered outside core."""

            assert PARAMETER_MODELS[CanonicalTool.SPAWN_AGENT] is _ExternalParameters
        finally:
            PARAMETER_MODELS.clear()
            PARAMETER_MODELS.update(before)


class TestParametersFor:
    def test_unregistered_tool_returns_bare_model_with_extras(self) -> None:
        result = parameters_for(CanonicalTool.SPAWN_AGENT, {"agent": "foo"})
        assert isinstance(result, ToolParameters)
        assert result.model_extra == {"agent": "foo"}


class TestExtraKeysSurvive:
    def test_extra_key_lands_in_model_extra(self) -> None:
        built = ShellParameters.build({"command": "ls", "description": "x"})
        assert built.model_extra == {"description": "x"}


class TestFailOpen:
    def test_malformed_known_field_keeps_raw_value_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            built = ReadParameters.build({"path": 123})
        assert built.path == 123  # type: ignore[comparison-overlap]
        assert "Invalid ReadParameters parameters" in caplog.text


class TestReadParametersAlias:
    def test_file_path_alias(self) -> None:
        assert ReadParameters.build({"file_path": "/x"}).path == "/x"

    def test_path_takes_precedence_over_file_path(self) -> None:
        built = ReadParameters.build({"path": "/a", "file_path": "/b"})
        assert built.path == "/a"


class TestSkillParametersAlias:
    def test_skill_name_takes_precedence_over_skill(self) -> None:
        built = SkillParameters.build({"skill_name": "a", "skill": "b"})
        assert built.skill == "a"

    def test_skill_alone(self) -> None:
        assert SkillParameters.build({"skill": "b"}).skill == "b"


class TestMcpToolUse:
    def test_json_string_arguments_decode(self) -> None:
        built = McpToolUse.build(
            {"server_name": "s", "tool_name": "t", "arguments": '{"a": 1}'}
        )
        assert built.arguments == {"a": 1}

    def test_unparseable_json_logs_and_becomes_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            built = McpToolUse.build(
                {"server_name": "s", "tool_name": "t", "arguments": "not json"}
            )
        assert built.arguments == {}
        assert "Failed to parse MCP arguments as JSON" in caplog.text

    def test_missing_arguments_logs_and_becomes_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            built = McpToolUse.build({"server_name": "s", "tool_name": "t"})
        assert built.arguments == {}
        assert "No arguments found for tool t" in caplog.text

    def test_extra_key_is_preserved_and_does_not_raise(self) -> None:
        built = McpToolUse.build(
            {
                "server_name": "s",
                "tool_name": "t",
                "arguments": {},
                "unexpected": "value",
            }
        )
        assert built.model_extra == {"unexpected": "value"}
