from typing import Any, Dict, List, Optional

from fastmcp.client.transports import StdioTransport

from .base import _BaseMCPClient


class MCPProcessClient(_BaseMCPClient):
    """Persistent stdio client for a FastMCP server using the official FastMCP Client."""

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd

        transport = StdioTransport(
            command=self.command,
            args=self.args,
            env=env,
            cwd=cwd,
            keep_alive=True,
        )
        super().__init__(transport, client_name="bluegpt-stdio")

    def _transport_running(self) -> bool:
        task = getattr(self.transport, "_connect_task", None)
        if task is None:
            return True
        return not task.done()

