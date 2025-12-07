from datetime import datetime, timezone

from fastmcp import FastMCP

mcp = FastMCP("BlueGPT FastMCP Time")


@mcp.tool
def utc_time() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    # Defaults to stdio transport; override with transport="http" if needed.
    mcp.run()
