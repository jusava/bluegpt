import os
import tomllib
from pathlib import Path
from typing import Any, Dict


def _load_mcp_config() -> Dict[str, Any]:
    """Load MCP config from TOML file specified by MCP_CONFIG_FILE."""
    path = Path(os.getenv("MCP_CONFIG_FILE", "config/mcp.toml"))
    data: Dict[str, Any] = tomllib.loads(path.read_text())
    return data["mcp"]
