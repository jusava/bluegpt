# Agentic Loop Notes

This document captures how the agentic flow in BlueGPT works, how tools are discovered, and how to hook in MCP servers.

## Architecture

- **Frontend:** Chat-style UI (`app/static/*`) that calls `/api/chat/stream` for streaming completions and `/api/chat` as a fallback.
- **Backend:** FastAPI (`app/main.py`) with an `AgentManager`/`AgentSession` (`app/agent.py`) that orchestrates OpenAI Responses API calls and tool loops.
- **Tools:** Collected in a `ToolRegistry` (`app/tools.py`); includes optional MCP tools (HTTP or FastMCP stdio) discovered from config. Tools are exposed to OpenAI via function/tool schemas.

## Request Flow

1. Frontend posts a user message to `/api/chat/stream` (SSE) or `/api/chat`.
2. The agent session appends the user message, then calls `client.responses.create(...)` with the current history and tool schemas.
3. If the model requests tool calls, the backend:
   - Records the assistant tool_calls message.
   - Executes each tool via `registry.execute`.
   - Submits outputs back with `client.responses.submit_tool_outputs`.
   - Repeats until the model returns text.
4. Final text is streamed to the UI in chunks (small buffer splits) or returned as JSON.

## Tool Registration

Tool sources are merged into a single registry on startup:

- **Built-in:** none by default.
- **FastMCP stdio:** Config: `[[mcp.stdio_servers]]` in `mcp.toml`. The server is launched via stdio using the provided `command/args/env/cwd`; tools are discovered with `list_tools` and registered (optional `prefix` applied). No manual tool definitions.

Order of loading (later entries do not override earlier unless the tool name matches), all from config:
1. `mcp.toml` stdio_servers (auto-discovered).

## Config Files and Env

- `MCP_CONFIG_FILE` (default `mcp.toml`): optional TOML config for MCP tools/servers.
- `.env`: load OpenAI vars and any MCP env JSON payloads.
- Sample `mcp.toml` is included at repo root.

## FastMCP Quickstart (stdio)

Sample server: `mcps/time_helper.py` (tools: `current_time`, `find_timezone`).

Config options (auto-discover only):
```toml
[[mcp.stdio_servers]]
command = "fastmcp"
args = ["run", "mcps/time_helper.py:mcp"]
prefix = ""
```

## Running Locally

```bash
uv run uvicorn app.main:app --reload
# Frontend: http://localhost:8000/
```

Ensure `OPENAI_API_KEY` is set (via `.env`). For MCP stdio, ensure `fastmcp` CLI is in PATH (same venv recommended).

## Troubleshooting

- Streaming shows raw SSE lines: hard-refresh; the SSE parser is in `app/static/app.js`.
- No MCP tools: check logs for discovery warnings; validate paths/commands in env or `mcp.toml`; ensure `fastmcp` is installed.
- Running loop during startup: discovery now runs in a separate thread to avoid `asyncio.run` conflicts.
