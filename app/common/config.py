import os
import tomllib
from pathlib import Path
from typing import Any, Dict


def _load_toml(path: Path) -> Dict[str, Any]:
    # Let errors propagate if the file is missing or malformed.
    return tomllib.loads(path.read_text())


def load_app_config(path: str | None = None) -> Dict[str, Any]:
    # Hardcoded path, no env var fallback
    config_path = Path(path or "config/config.toml")
    data = _load_toml(config_path)

    app_cfg = data["app"]
    reasoning_cfg = data["reasoning"]

    return {
        "default_model": app_cfg["default_model"],
        "available_models": app_cfg["available_models"],
        "reasoning_effort": app_cfg["reasoning_effort"],
        "text_verbosity": app_cfg["text_verbosity"],
        "max_output_tokens": app_cfg["max_output_tokens"],
        "openai_base_url": app_cfg["openai_base_url"],
        "reasoning_effort_options": reasoning_cfg["allowed"],
    }


def load_prompts_config(path: str | None = None) -> Dict[str, str]:
    config_path = Path(path or "config/prompts.toml")
    data = _load_toml(config_path)
    return {"system": data["prompts"]["system"]}


def load_samples_config(path: str | None = None) -> list[Dict[str, str]]:
    config_path = Path(path or "config/samples.toml")
    data = _load_toml(config_path)

    samples = data["samples"]
    # We expect a list of dicts with specific keys
    return [
        {
            "title": str(item["title"]),
            "description": str(item["description"]),
            "prompt": str(item["prompt"]),
        }
        for item in samples
    ]
