"""Generic, frontend-agnostic engine for parsing a frontend's hook payload."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, TypeVar, cast

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
    HookInput,
    PostToolUseFields,
    PreToolUseFields,
)
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, Frontend

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_SESSION_ID_KEY = "session_id"


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


PAYLOAD_MODELS: dict[tuple[Frontend, str], type[BaseModel]] = {}


def payload_model(
    frontend: Frontend, *keys: CanonicalHook | CanonicalTool
) -> Callable[[type[_ModelT]], type[_ModelT]]:
    """Register a payload model for a frontend's envelope, hook, or tool.

    Called with no keys, registers the frontend's envelope model.

    Args:
        frontend: The frontend this model applies to.
        *keys: The canonical hooks or tools this model applies to.

    Returns:
        A decorator that registers the decorated class and returns it unchanged.
    """

    def decorator(cls: type[_ModelT]) -> type[_ModelT]:
        for key in keys or ("",):
            PAYLOAD_MODELS[(frontend, key)] = cls
        return cls

    return decorator


def model_for(
    protocol_cls: type[StandardPayloadProtocol], key: str = ""
) -> type[BaseModel] | None:
    """Find the most specific registered payload model for a protocol.

    Args:
        protocol_cls: The frontend's StandardPayloadProtocol subclass.
        key: The canonical hook or tool to look up, or "" for the envelope.

    Returns:
        The most specific registered model, or None if none is registered.
    """
    for frontend in protocol_cls.frontends:
        model = PAYLOAD_MODELS.get((frontend, key))
        if model is not None:
            return model
    return None


def env_from(info: ValidationInfo) -> Mapping[str, str]:
    """Return the process environment passed via validation context.

    Args:
        info: The active validation info.

    Returns:
        The env mapping passed as `context={"env": ...}`, or {} if absent.
    """
    context = info.context or {}
    return cast("Mapping[str, str]", context.get("env", {}))


def _cwd_to_workspace_roots(value: Any) -> list[str]:
    """Wrap a cwd string as a single-element list, or [] if it is falsy.

    Returns:
        A one-element list containing the value, or an empty list.
    """
    return [value] if value else []


class PayloadEnvelope(BaseModel):
    """Canonical envelope fields common to every hook payload."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    session_env_keys: ClassVar[tuple[str, ...]] = ()

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
            info: The active validation info, carrying the process env.

        Returns:
            The data with `session_id` set to the first truthy of the raw
            value, each configured env var in turn, or a hash of `cwd`.
        """
        if not isinstance(data, dict):
            return data
        value = data.get(_SESSION_ID_KEY)
        if not value:
            env = env_from(info)
            for env_key in cls.session_env_keys:
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


def parse_standard_payload(
    payload: RawPayload, protocol_cls: type[StandardPayloadProtocol]
) -> HookInput:
    """Parse a raw payload into a HookInput using the frontend's registered models.

    Args:
        payload: The raw hook invocation data.
        protocol_cls: The frontend's StandardPayloadProtocol subclass.

    Returns:
        The most specific matching HookInput subclass.
    """
    data = payload.data or {}
    hook = protocol_cls.canonical_hook(data.get(protocol_cls.hook_event_key, ""))
    context = {"env": payload.env}

    envelope_cls = model_for(protocol_cls) or PayloadEnvelope
    fields = envelope_cls.model_validate(data, context=context).model_dump()
    fields["hookName"] = hook

    raw_tool = data.get("tool_name", "")
    tool_input = ensure_dict(data.get("tool_input", {}))
    tool = map_tool_name(raw_tool, protocol_cls) if raw_tool else ""

    if hook in (CanonicalHook.PRE_TOOL_USE, CanonicalHook.POST_TOOL_USE) and tool:
        if raw_tool.startswith(protocol_cls.mcp_prefix):
            params = mcp_parameters(
                raw_tool,
                tool_input,
                protocol_cls.mcp_prefix,
                protocol_cls.mcp_separator,
            )
        else:
            params_cls = model_for(protocol_cls, tool)
            params = (
                tool_input
                if params_cls is None
                else params_cls.model_validate(tool_input).model_dump(exclude_none=True)
            )

        input_cls = HOOK_INPUTS[hook]
        if hook == CanonicalHook.PRE_TOOL_USE:
            fields[input_cls.payload_field] = PreToolUseFields(
                toolName=tool, parameters=params
            )
        else:
            response = ensure_dict(data.get("tool_response", {}))
            result = response.get("result")
            fields[input_cls.payload_field] = PostToolUseFields(
                toolName=tool,
                parameters=params,
                success=bool(response.get("success", True)),
                executionTimeMs=0,
                result=result
                if result is None or isinstance(result, str)
                else str(result),
            )
        return input_cls.build(fields)

    fields_cls = model_for(protocol_cls, hook)
    if fields_cls is not None:
        input_cls = HOOK_INPUTS[hook]
        fields[input_cls.payload_field] = fields_cls.model_validate(
            data, context=context
        ).model_dump()
        return input_cls.build(fields)

    return HookInput.build(fields)


class StandardPayloadProtocol(Protocol):
    """A Protocol whose parse() is driven by registered pydantic payload models."""

    frontends: ClassVar[tuple[Frontend, ...]]
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {}
    mcp_prefix: ClassVar[str]
    mcp_separator: ClassVar[str]
    hook_event_key: ClassVar[str] = "hook_event_name"

    def parse(self, payload: RawPayload) -> HookInput:
        """Parse the payload using this frontend's registered models.

        Returns:
            The most specific matching HookInput subclass.
        """
        return parse_standard_payload(payload, type(self))
