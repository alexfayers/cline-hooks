"""Shared configuration for the cline-hooks package."""

from __future__ import annotations

from contextvars import ContextVar
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from platformdirs import user_config_dir

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger("hooks.config")

_hook_env: ContextVar[Mapping[str, str] | None] = ContextVar("_hook_env", default=None)


def set_hook_env(env: Mapping[str, str]) -> None:
    """Set the environment of the hook process this invocation serves."""
    _hook_env.set(env)


def hook_env() -> Mapping[str, str]:
    """Return the environment of the hook process this invocation serves.

    Returns:
        The environment passed to `set_hook_env`, or this process's own if none was set.
    """
    env = _hook_env.get()
    return os.environ if env is None else env


def config_dir() -> Path:
    """Return the platform user-config directory for cline-hooks."""
    return Path(user_config_dir("cline-hooks"))


_CONFIG_PATH = config_dir() / "config.json"


def _load_config_file() -> dict[str, Any]:
    """Read the user config file at `_CONFIG_PATH`.

    Returns:
        The parsed config file contents, or {} if missing or invalid.
    """
    try:
        parsed = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read config file %s; ignoring", _CONFIG_PATH)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("Config file %s is not a JSON object; ignoring", _CONFIG_PATH)
        return {}
    return parsed


def agent_teams_enabled() -> bool:
    """Return whether agent teams are enabled for this session.

    Read from CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS first, which the harness
    gates on presence rather than value, so any non-empty value counts as
    enabled. If that variable is unset, falls back to the `agent_teams_enabled`
    key (a JSON boolean) in the user config file at `_CONFIG_PATH`, then to
    False.
    """
    env = hook_env()
    if "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in env:
        return bool(env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"])
    return bool(_load_config_file().get("agent_teams_enabled", False))


def get_push_block_markers() -> tuple[str, ...]:
    """Return directory/file names marking a workspace where `git push` is blocked.

    Read from CLINE_HOOKS_PUSH_BLOCK_MARKERS (comma-separated) first. If that
    variable is unset, falls back to the `push_block_markers` key (a JSON list
    of strings) in the user config file at `_CONFIG_PATH`, then to empty.
    """
    env = hook_env()
    if "CLINE_HOOKS_PUSH_BLOCK_MARKERS" in env:
        raw = env["CLINE_HOOKS_PUSH_BLOCK_MARKERS"]
        return tuple(marker.strip() for marker in raw.split(",") if marker.strip())
    config_markers = _load_config_file().get("push_block_markers", [])
    if not isinstance(config_markers, list):
        return ()
    return tuple(str(marker).strip() for marker in config_markers if str(marker).strip())
