"""Generic, frontend-agnostic engine for parsing a frontend's hook payload.

A frontend speaking the standard snake_case shape declares what differs about
it as class attributes on a `StandardPayloadProtocol` subclass; a frontend
reusing another's spec inherits those attributes by subclassing it.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, cast

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)

from cline_hooks.core.models import (
    HOOK_INPUTS,
    HookFields,
    HookInput,
    PostToolUseFields,
    PreToolUseFields,
)
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_SESSION_ID_KEY = "session_id"
_SESSION_ENV_KEYS_KEY = "session_env_keys"

_TOOL_HOOK_FIELDS: Mapping[CanonicalHook, type[HookFields]] = {
    CanonicalHook.PRE_TOOL_USE: PreToolUseFields,
    CanonicalHook.POST_TOOL_USE: PostToolUseFields,
}


def ensure_dict(value: dict[str, Any] | str | list[Any] | None) -> dict[str, Any]:
    """Normalise a value that should be a dict.

    Args:
        value: The raw value (may be dict, str, list, or None).

    Returns:
        A dict, falling back to {} for non-dict types.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def mcp_parameters(
    native_name: str, tool_input: dict[str, Any], prefix: str, separator: str
) -> dict[str, Any]:
    """Build use_mcp_tool-style parameters from a frontend's native MCP tool name.

    Args:
        native_name: The frontend's native tool name, prefixed per `prefix`.
        tool_input: The tool input from the frontend's hook event.
        prefix: The frontend's MCP tool-name prefix.
        separator: The frontend's MCP server/tool separator.

    Returns:
        Parameters dict matching the use_mcp_tool schema.
    """
    parts = native_name.removeprefix(prefix).split(separator, 1)
    server_name = parts[0]
    tool_name = parts[1] if len(parts) > 1 else ""
    return {
        "server_name": server_name,
        "tool_name": tool_name,
        "arguments": json.dumps(tool_input),
    }


def map_tool_name(native_name: str, protocol_cls: type[StandardPayloadProtocol]) -> str:
    """Map a frontend's native tool name to its canonical equivalent.

    Args:
        native_name: The tool name from the frontend's hook event.
        protocol_cls: The frontend's StandardPayloadProtocol subclass.

    Returns:
        The canonical tool name used by handlers.
    """
    if native_name.startswith(protocol_cls.mcp_prefix):
        return CanonicalTool.MCP
    return protocol_cls.tool_map.get(native_name, native_name)


def env_from(info: ValidationInfo) -> Mapping[str, str]:
    """Return the process environment passed via validation context.

    Args:
        info: The active validation info.

    Returns:
        The env mapping passed as `context={"env": ...}`, or {} if absent.
    """
    context = info.context or {}
    return cast("Mapping[str, str]", context.get("env", {}))


def _session_env_keys_from(info: ValidationInfo) -> tuple[str, ...]:
    """Return the frontend's session-id env var names from validation context.

    Returns:
        The env var names passed in context, in priority order, or ().
    """
    context = info.context or {}
    return cast("tuple[str, ...]", context.get(_SESSION_ENV_KEYS_KEY, ()))


def _cwd_to_workspace_roots(value: Any) -> list[str]:
    """Wrap a cwd string as a single-element list, or [] if it is falsy.

    Returns:
        A one-element list containing the value, or an empty list.
    """
    return [value] if value else []


class PayloadEnvelope(BaseModel):
    """Canonical envelope fields common to every standard hook payload."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    taskId: str = Field(default="", validation_alias=_SESSION_ID_KEY)
    workspaceRoots: Annotated[list[str], BeforeValidator(_cwd_to_workspace_roots)] = (
        Field(default_factory=list, validation_alias="cwd")
    )
    transcriptPath: str = Field(default="", validation_alias="transcript_path")
    agentType: str = Field(default="", validation_alias="agent_type")

    @model_validator(mode="before")
    @classmethod
    def _resolve_session_id(cls, data: Any, info: ValidationInfo) -> Any:
        """Resolve the session-id chain into the `session_id` key.

        Args:
            data: The raw payload data.
            info: The active validation info, carrying the process env and the
                frontend's session-id env var names.

        Returns:
            The data with `session_id` set to the first truthy of the raw
            value, each env var in turn, or a hash of `cwd`.
        """
        if not isinstance(data, dict):
            return data
        value = data.get(_SESSION_ID_KEY)
        if not value:
            env = env_from(info)
            for env_key in _session_env_keys_from(info):
                value = env.get(env_key)
                if value:
                    break
            else:
                value = None
        if not value:
            cwd = data.get("cwd", "")
            value = hashlib.sha256(cwd.encode()).hexdigest()[:16] if cwd else ""
        return {**data, _SESSION_ID_KEY: value}


class ToolParams(BaseModel):
    """Base model for a tool's canonical parameters, tolerant of unknown input."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


Flag = Annotated[bool, BeforeValidator(bool)]


def diff_envelope(*keys: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a before-validator that wraps the first truthy content key as a diff.

    Args:
        *keys: Tool-input keys to check, in priority order.

    Returns:
        A validator setting `diff` to the SEARCH/REPLACE-wrapped content of
        the first truthy key, leaving it unset if none are truthy.
    """

    def validate(data: dict[str, Any]) -> dict[str, Any]:
        for key in keys:
            content = data.get(key, "")
            if content:
                return {
                    **data,
                    "diff": f"------- SEARCH\n=======\n{content}\n+++++++ REPLACE",
                }
        return data

    return validate


def _tool_parameters(
    raw_tool: str,
    tool: str,
    tool_input: dict[str, Any],
    protocol_cls: type[StandardPayloadProtocol],
) -> dict[str, Any]:
    """Normalise a tool call's raw input into canonical parameters.

    Args:
        raw_tool: The frontend's native tool name.
        tool: The canonical tool name `raw_tool` maps to.
        tool_input: The raw tool input from the hook event.
        protocol_cls: The frontend's StandardPayloadProtocol subclass.

    Returns:
        The canonical parameters, or the raw input where the frontend declares
        no model for this tool.
    """
    if raw_tool.startswith(protocol_cls.mcp_prefix):
        return mcp_parameters(
            raw_tool, tool_input, protocol_cls.mcp_prefix, protocol_cls.mcp_separator
        )
    params_cls = protocol_cls.tool_models.get(cast("CanonicalTool", tool))
    if params_cls is None:
        return tool_input
    return params_cls.model_validate(tool_input).model_dump(exclude_none=True)


def _tool_hook_fields(
    data: dict[str, Any],
    hook: CanonicalHook,
    tool: str,
    params: dict[str, Any],
    protocol_cls: type[StandardPayloadProtocol],
) -> HookFields:
    """Build the payload fields for a PreToolUse or PostToolUse event.

    Args:
        data: The raw payload data.
        hook: The canonical tool hook being parsed.
        tool: The canonical tool name.
        params: The canonical tool parameters.
        protocol_cls: The frontend's StandardPayloadProtocol subclass.

    Returns:
        The frontend's declared fields model, or the canonical one where it
        declares none.
    """
    merged: dict[str, Any] = {**data, "toolName": tool, "parameters": params}
    if hook is CanonicalHook.POST_TOOL_USE:
        response = ensure_dict(data.get("tool_response", {}))
        result = response.get("result")
        merged["success"] = bool(response.get("success", True))
        merged["result"] = (
            result if result is None or isinstance(result, str) else str(result)
        )
    fields_cls = protocol_cls.hook_models.get(hook) or _TOOL_HOOK_FIELDS[hook]
    return fields_cls.model_validate(merged)


def parse_standard_payload(
    payload: RawPayload, protocol_cls: type[StandardPayloadProtocol]
) -> HookInput:
    """Parse a raw payload into a HookInput using the frontend's declared models.

    Args:
        payload: The raw hook invocation data.
        protocol_cls: The frontend's StandardPayloadProtocol subclass.

    Returns:
        The most specific matching HookInput subclass.
    """
    data = payload.data or {}
    hook = protocol_cls.canonical_hook(data.get(protocol_cls.hook_event_key, ""))
    context = {
        "env": payload.env,
        _SESSION_ENV_KEYS_KEY: protocol_cls.session_env_keys,
    }

    fields = protocol_cls.envelope_model.model_validate(
        data, context=context
    ).model_dump()
    fields["hookName"] = hook

    if hook in _TOOL_HOOK_FIELDS:
        raw_tool = data.get("tool_name", "")
        if not raw_tool:
            return HookInput.build(fields)
        tool_hook = cast("CanonicalHook", hook)
        tool = map_tool_name(raw_tool, protocol_cls)
        params = _tool_parameters(
            raw_tool, tool, ensure_dict(data.get("tool_input", {})), protocol_cls
        )
        input_cls = HOOK_INPUTS[tool_hook]
        fields[input_cls.payload_field] = _tool_hook_fields(
            data, tool_hook, tool, params, protocol_cls
        )
        return input_cls.build(fields)

    fields_cls = protocol_cls.hook_models.get(cast("CanonicalHook", hook))
    if fields_cls is not None:
        input_cls = HOOK_INPUTS[hook]
        fields[input_cls.payload_field] = fields_cls.model_validate(
            data, context=context
        ).model_dump()
        return input_cls.build(fields)

    return HookInput.build(fields)


class StandardPayloadProtocol(Protocol):
    """A Protocol whose parse() is driven by declarative pydantic payload models.

    Attributes:
        envelope_model: Model for the fields every hook payload carries.
        hook_models: Per-hook payload field models, keyed by canonical hook.
        tool_models: Per-tool parameter models, keyed by canonical tool.
        session_env_keys: Env vars holding the session id, in priority order,
            for payloads that omit it.
        mcp_prefix: Prefix marking a native tool name as an MCP tool call.
        mcp_separator: Separator between server and tool in that name.
        hook_event_key: Payload key naming the native hook event.
    """

    envelope_model: ClassVar[type[PayloadEnvelope]] = PayloadEnvelope
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {}
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {}
    session_env_keys: ClassVar[tuple[str, ...]] = ()
    mcp_prefix: ClassVar[str]
    mcp_separator: ClassVar[str]
    hook_event_key: ClassVar[str] = "hook_event_name"

    def parse(self, payload: RawPayload) -> HookInput:
        """Parse the payload using this frontend's declared models.

        Returns:
            The most specific matching HookInput subclass.
        """
        return parse_standard_payload(payload, type(self))
