from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

from fastmcp import FastMCP

mcp = FastMCP("BlueGPT FastMCP Time")


@mcp.tool()
def current_time(timezone_name: str | None = None) -> str:
    """Return the current time in ISO-8601 format for the given timezone (IANA/`pytz`-style). Defaults to UTC."""
    try:
        tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:  # noqa: BLE001
        return f"Unknown timezone '{timezone_name}'. Provide an IANA/pytz timezone like 'Europe/Helsinki'."
    return datetime.now(tz).isoformat()


@mcp.tool()
def find_timezone(query: str) -> str:
    """Lookup a timezone by city or country keyword; returns a matching IANA/pytz timezone name."""
    normalized = (query or "").strip().lower().replace(" ", "_")
    if not normalized:
        return "No timezone query provided."

    zones = sorted(available_timezones())
    # Exact matches first.
    for tz in zones:
        lowered = tz.lower()
        if lowered == normalized or lowered.endswith(f"/{normalized}"):
            return tz

    # Fuzzy contains match as a fallback.
    for tz in zones:
        if normalized in tz.lower():
            return tz

    return f"No timezone found for '{query}'. Try a city like 'Helsinki' or a full zone like 'Europe/Helsinki'."


if __name__ == "__main__":
    # Defaults to stdio transport; override with transport="http" if needed.
    mcp.run()
