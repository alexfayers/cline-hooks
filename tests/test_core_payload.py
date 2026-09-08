from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping
from typing import ClassVar, NoReturn, get_args

from pydantic import BaseModel, model_validator

from cline_hooks.core.models import HOOK_INPUTS, HookFields
from cline_hooks.core.payload import (
    PAYLOAD_MODELS,
    Flag,
    PayloadEnvelope,
    StandardPayloadProtocol,
    ToolParams,
    diff_envelope,
    ensure_dict,
    map_tool_name,
    mcp_parameters,
    model_for,
    payload_model,
)
from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, Frontend


class _ConcreteProtocol(StandardPayloadProtocol):
    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        return False

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        sys.exit(2)


class TestPayloadModelRegistry:
    class _ClaudeOnly(_ConcreteProtocol):
        frontends: ClassVar[tuple[Frontend, ...]] = (Frontend.CLAUDE_CODE,)

    class _CopilotThenClaude(_ConcreteProtocol):
        frontends: ClassVar[tuple[Frontend, ...]] = (
            Frontend.COPILOT,
            Frontend.CLAUDE_CODE,
        )

    def test_registers_and_resolves_for_matching_frontend(self) -> None:
        before = dict(PAYLOAD_MODELS)
        try:
            PAYLOAD_MODELS.clear()

            @payload_model(Frontend.CLAUDE_CODE, CanonicalHook.STOP)
            class _Model(BaseModel):
                pass

            assert model_for(self._ClaudeOnly, CanonicalHook.STOP) is _Model
        finally:
            PAYLOAD_MODELS.clear()
            PAYLOAD_MODELS.update(before)

    def test_resolves_through_frontend_chain_fallback(self) -> None:
        before = dict(PAYLOAD_MODELS)
        try:
            PAYLOAD_MODELS.clear()

            @payload_model(Frontend.CLAUDE_CODE, CanonicalHook.STOP)
            class _Model(BaseModel):
                pass

            assert model_for(self._CopilotThenClaude, CanonicalHook.STOP) is _Model
        finally:
            PAYLOAD_MODELS.clear()
            PAYLOAD_MODELS.update(before)

    def test_most_specific_frontend_wins_when_both_registered(self) -> None:
        before = dict(PAYLOAD_MODELS)
        try:
            PAYLOAD_MODELS.clear()

            @payload_model(Frontend.COPILOT, CanonicalHook.PRE_COMPACT)
            class _CopilotModel(BaseModel):
                pass

            @payload_model(Frontend.CLAUDE_CODE, CanonicalHook.PRE_COMPACT)
            class _ClaudeModel(BaseModel):
                pass

            resolved = model_for(self._CopilotThenClaude, CanonicalHook.PRE_COMPACT)
            assert resolved is _CopilotModel
        finally:
            PAYLOAD_MODELS.clear()
            PAYLOAD_MODELS.update(before)

    def test_unregistered_key_returns_none(self) -> None:
        before = dict(PAYLOAD_MODELS)
        try:
            PAYLOAD_MODELS.clear()
            assert model_for(self._ClaudeOnly, CanonicalHook.STOP) is None
        finally:
            PAYLOAD_MODELS.clear()
            PAYLOAD_MODELS.update(before)


class TestPayloadEnvelope:
    def test_payload_session_id_wins(self) -> None:
        result = PayloadEnvelope.model_validate(
            {"session_id": "sid-1", "cwd": "/x"}, context={"env": {}}
        )
        assert result.taskId == "sid-1"

    def test_falls_back_to_first_present_env_key(self) -> None:
        class _Envelope(PayloadEnvelope):
            session_env_keys: ClassVar[tuple[str, ...]] = ("ENV_A", "ENV_B")

        result = _Envelope.model_validate({}, context={"env": {"ENV_B": "b-val"}})
        assert result.taskId == "b-val"

    def test_env_keys_checked_in_declaration_order(self) -> None:
        class _Envelope(PayloadEnvelope):
            session_env_keys: ClassVar[tuple[str, ...]] = ("ENV_A", "ENV_B")

        result = _Envelope.model_validate(
            {}, context={"env": {"ENV_A": "a-val", "ENV_B": "b-val"}}
        )
        assert result.taskId == "a-val"

    def test_falls_back_to_cwd_hash(self) -> None:
        cwd = "/some/dir"
        expected = hashlib.sha256(cwd.encode()).hexdigest()[:16]
        result = PayloadEnvelope.model_validate({"cwd": cwd}, context={"env": {}})
        assert result.taskId == expected

    def test_returns_empty_without_cwd(self) -> None:
        result = PayloadEnvelope.model_validate({}, context={"env": {}})
        assert result.taskId == ""

    def test_cwd_string_becomes_single_element_workspace_roots(self) -> None:
        result = PayloadEnvelope.model_validate({"cwd": "/x"}, context={"env": {}})
        assert result.workspaceRoots == ["/x"]

    def test_falsy_cwd_becomes_empty_workspace_roots(self) -> None:
        result = PayloadEnvelope.model_validate({"cwd": ""}, context={"env": {}})
        assert result.workspaceRoots == []


class TestFlag:
    def test_coerces_truthy_non_bool_value_to_true(self) -> None:
        class _Model(BaseModel):
            flag: Flag = False

        assert _Model.model_validate({"flag": "yes"}).flag is True

    def test_absent_key_falls_back_to_field_default(self) -> None:
        class _DefaultFalse(BaseModel):
            flag: Flag = False

        class _DefaultTrue(BaseModel):
            flag: Flag = True

        assert _DefaultFalse.model_validate({}).flag is False
        assert _DefaultTrue.model_validate({}).flag is True


class _DiffModel(BaseModel):
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("x", "y"))


class TestDiffEnvelope:
    def test_builds_envelope_from_first_truthy_key(self) -> None:
        result = _DiffModel.model_validate({"y": "content"})
        assert result.diff == "------- SEARCH\n=======\ncontent\n+++++++ REPLACE"

    def test_skips_earlier_empty_key_for_later_truthy_key(self) -> None:
        result = _DiffModel.model_validate({"x": "", "y": "second"})
        assert result.diff == "------- SEARCH\n=======\nsecond\n+++++++ REPLACE"

    def test_unset_when_every_key_empty_or_absent(self) -> None:
        assert _DiffModel.model_validate({}).diff is None
        assert _DiffModel.model_validate({"x": "", "y": ""}).diff is None

    def test_field_excluded_from_dump_when_unset(self) -> None:
        dumped = _DiffModel.model_validate({}).model_dump(exclude_none=True)
        assert "diff" not in dumped


class TestEnsureDict:
    def test_dict_passthrough(self) -> None:
        value = {"a": 1}
        assert ensure_dict(value) is value

    def test_json_object_string_parsed(self) -> None:
        assert ensure_dict('{"a": 1}') == {"a": 1}

    def test_json_non_dict_string_falls_back_to_empty(self) -> None:
        assert ensure_dict("[1, 2]") == {}

    def test_invalid_json_string_falls_back_to_empty(self) -> None:
        assert ensure_dict("not json") == {}

    def test_list_falls_back_to_empty(self) -> None:
        assert ensure_dict([1, 2]) == {}

    def test_none_falls_back_to_empty(self) -> None:
        assert ensure_dict(None) == {}


class TestMcpParameters:
    def test_splits_server_and_tool(self) -> None:
        params = mcp_parameters("@server/tool", {"a": 1}, prefix="@", separator="/")
        assert params["server_name"] == "server"
        assert params["tool_name"] == "tool"
        assert params["arguments"] == json.dumps({"a": 1})

    def test_empty_tool_name_when_no_separator(self) -> None:
        params = mcp_parameters("@onlyserver", {}, prefix="@", separator="/")
        assert params["server_name"] == "onlyserver"
        assert params["tool_name"] == ""

    def test_only_one_prefix_removed(self) -> None:
        params = mcp_parameters("@@server/tool", {}, prefix="@", separator="/")
        assert params["server_name"] == "@server"
        assert params["tool_name"] == "tool"


class TestMapToolName:
    def _protocol(self) -> type[StandardPayloadProtocol]:
        """Build a synthetic protocol with a tool_map entry and an MCP prefix.

        Returns:
            A StandardPayloadProtocol subclass suitable for exercising map_tool_name.
        """

        class _Protocol(StandardPayloadProtocol):
            frontends: ClassVar[tuple[Frontend, ...]] = ()
            tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
                "native_shell": CanonicalTool.SHELL
            }
            mcp_prefix: ClassVar[str] = "@"
            mcp_separator: ClassVar[str] = "/"

        return _Protocol

    def test_maps_via_tool_map(self) -> None:
        assert map_tool_name("native_shell", self._protocol()) == CanonicalTool.SHELL

    def test_unmapped_name_unchanged(self) -> None:
        assert (
            map_tool_name("some_unknown_tool", self._protocol()) == "some_unknown_tool"
        )

    def test_mcp_prefixed_name_maps_to_mcp(self) -> None:
        assert map_tool_name("@server/tool", self._protocol()) == CanonicalTool.MCP


def _expected_base_class(key: str) -> type[BaseModel]:
    """Return the canonical base class a PAYLOAD_MODELS key implies.

    Returns:
        PayloadEnvelope for the empty key, ToolParams for a CanonicalTool key, or
        the hook's HookFields subclass from HOOK_INPUTS for a CanonicalHook key.

    Raises:
        AssertionError: If a CanonicalHook key's input class has no HookFields
            payload field.
    """
    if key == "":
        return PayloadEnvelope
    if key in set(CanonicalTool):
        return ToolParams
    input_cls = HOOK_INPUTS[key]
    annotation = input_cls.model_fields[input_cls.payload_field].annotation
    for candidate in get_args(annotation) or (annotation,):
        if isinstance(candidate, type) and issubclass(candidate, HookFields):
            return candidate
    raise AssertionError(f"no HookFields base found for key {key!r}")


class TestPayloadModelsInvariant:
    def test_every_registered_model_subclasses_its_key_base(self) -> None:
        for (_frontend, key), model in PAYLOAD_MODELS.items():
            assert issubclass(model, _expected_base_class(key))
