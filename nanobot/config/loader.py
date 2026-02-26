"""Configuration loading utilities."""

import json
import os
from pathlib import Path
from typing import Any

from nanobot.config.schema import Config

# Environment variable prefix and delimiter
ENV_PREFIX = "NANOBOT_"
ENV_DELIMITER = "__"


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def _parse_env_value(value: str) -> Any:
    """Parse environment variable value to appropriate Python type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.startswith(("[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def _get_env_overrides() -> dict[str, Any]:
    """
    Extract NANOBOT_* environment variables and convert to nested dict.

    Examples:
        NANOBOT_AGENTS__DEFAULTS__MODEL=GLM-4.6 -> {"agents": {"defaults": {"model": "GLM-4.6"}}}
        NANOBOT_CHANNELS__TELEGRAM__ENABLED=true -> {"channels": {"telegram": {"enabled": True}}}
        NANOBOT_PROVIDERS__OPENAI__API_KEY=sk-xxx -> {"providers": {"openai": {"api_key": "sk-xxx"}}}
    """
    result: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX):].lower().split(ENV_DELIMITER)
        parsed = _parse_env_value(value)
        current = result
        for part in path[:-1]:
            current = current.setdefault(part, {})
        current[path[-1]] = parsed
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge dicts. Override takes precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration with environment variable overrides.

    Priority (highest to lowest):
        1. Environment variables (NANOBOT_*)
        2. Config file (config.json)
        3. Default values

    Examples:
        export NANOBOT_AGENTS__DEFAULTS__MODEL=GLM-4.6
        export NANOBOT_CHANNELS__TELEGRAM__ENABLED=true
        export NANOBOT_CHANNELS__TELEGRAM__TOKEN=your-bot-token
        export NANOBOT_PROVIDERS__OPENAI__API_KEY=sk-xxx
        export NANOBOT_GATEWAY__PORT=8080
    """
    path = config_path or get_config_path()

    # Load from file
    file_data: dict[str, Any] = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            file_data = data
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration with environment overrides.")

    # Merge: env overrides take precedence
    env_overrides = _get_env_overrides()
    merged = _deep_merge(file_data, env_overrides)

    return Config.model_validate(merged) if merged else Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
