import os
import tomllib
from pathlib import Path
from typing import Any, Dict

DEFAULT_APP_CONFIG: Dict[str, Any] = {
    "default_model": "gpt-5-mini",
    "available_models": ["gpt-5.1", "gpt-5-mini"],
}


def _load_toml(path: Path) -> Dict[str, Any]:
    # Let errors propagate if the file is missing or malformed.
    return tomllib.loads(path.read_text())


def load_app_config(path: str | None = None) -> Dict[str, Any]:
    config_path = Path(path or os.getenv("APP_CONFIG_FILE", "config/config.toml"))
    data = _load_toml(config_path)
    app_cfg = data.get("app", {})
    return {
        "default_model": app_cfg.get("default_model", DEFAULT_APP_CONFIG["default_model"]),
        "available_models": app_cfg.get("available_models", DEFAULT_APP_CONFIG["available_models"]),
    }


def load_prompts_config(path: str | None = None) -> Dict[str, str]:
    config_path = Path(path or os.getenv("PROMPTS_CONFIG_FILE", "config/prompts.toml"))
    data = _load_toml(config_path)
    prompts_cfg = data.get("prompts", {})
    system_prompt = prompts_cfg.get(
        "system",
        "You are BlueGPT, a concise assistant. Use provided tools when they improve factual accuracy. "
        "Keep answers brief but helpful. If a tool call fails, explain the failure and continue.",
    )
    return {"system": system_prompt}
