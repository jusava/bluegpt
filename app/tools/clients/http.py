from typing import Any, Dict, List, Optional

from fastmcp.client.transports import StreamableHttpTransport

from .base import _BaseMCPClient


class MCPHttpClient(_BaseMCPClient):
    """Persistent HTTP client for a FastMCP server using the official FastMCP Client."""

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        auth: Any = None,
        sse_read_timeout: Any = None,
    ) -> None:
        self.url = url
        self.headers = headers
        self.auth = auth
        self.sse_read_timeout = sse_read_timeout

        transport = StreamableHttpTransport(
            url=self.url,
            headers=headers,
            auth=auth,
            sse_read_timeout=sse_read_timeout,
        )
        super().__init__(transport, client_name="bluegpt-http")

