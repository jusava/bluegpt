# Agentic Loop Notes

This document captures how the agentic flow in BlueGPT works, how tools are discovered, and how to hook in MCP servers.

## Architecture

- **Frontend:** Static chat UI (`app/static/*`) that uses `/api/chat/stream` (SSE) and surfaces tool/reasoning events, model selector, generation controls, and tool toggles.
- **Backend:** FastAPI (`app/main.py` entrypoint; `app/web/*` routes) with `AgentManager`/`AgentSession` (`app/agent/*`) orchestrating OpenAI Responses API calls, reasoning output, and the local tool loop. Sessions live in memory per `chat_id`.
- **Tools:** `ToolRegistry` (`app/tools/registry.py`) auto-discovers FastMCP tools from `config/mcp.toml`. If a server entry only has `url`, BlueGPT passes that value directly to the FastMCP `Client` (transport inferred); if the entry has additional fields, it is passed as a full MCPConfig structure. Discovered tools are exposed to OpenAI as function tools.
- **Config:** `app/common/config.py` loads TOML files for app defaults, prompts, and UI samples. MCP server config is loaded in `app/tools/mcp.py`.

## Request Flow

1. Frontend posts a user message to `/api/chat/stream` (preferred) or `/api/chat` with optional `chat_id` and `system_prompt`.
2. `AgentManager.get_or_create` ensures a session seeded with the system prompt, current model, reasoning effort, text verbosity, and max output tokens.
3. `AgentSession._generate` calls `client.responses.create` with history, active tools (`registry.list_for_responses()`), `reasoning=Reasoning(effort=..., summary="auto")`, and `max_output_tokens`.
4. Response output is appended to the message list. For `reasoning` items, a SSE `reasoning` event is emitted. For `function_call` items: emit `tool_start`, execute via `registry.execute` (FastMCP stdio), emit `tool_result`, append `function_call_output`, and loop again with the augmented history.
5. When a turn produces no tool calls, the assistant text is appended and streamed back via `chunk_text` to yield pseudo-streamed chunks; `/api/chat` aggregates the same flow without SSE.
6. UI bubbles show text plus expandable status entries for `tool_start`, `tool_result`, and `reasoning`.

## Tool Registration

- Loaded at startup in `build_default_registry()`, reading `config/mcp.toml`.
- Each `mcp.servers` entry is connected via the FastMCP `Client` (stdio starts a subprocess; http connects to a URL). Tools are registered with their original name and schema, marked `source="mcp:{server_name}"`.
- `prefix` is not applied; names must match what the MCP server returns.
- Tool activation toggles are stored in-memory; `/api/tools/{name}/active` and the UI settings panel flip them on/off for subsequent turns.

## Config Files and Env

- `config/config.toml` → defaults for model list, reasoning effort options, text verbosity, and max output tokens.
- `config/prompts.toml` → system prompt for new chats.
- `config/samples.toml` → UI suggestion cards.
- `config/mcp.toml` → FastMCP stdio/HTTP servers to auto-discover tools from.
- `.env` may be used to set `OPENAI_API_KEY` (required).
  All paths are resolved relative to the project root (the directory containing `pyproject.toml`), not the current working directory.

## FastMCP Quickstart (stdio)

- Sample server: `mcps/time_helper.py` exposes `current_time` and `find_timezone`.
- With the sample `config/mcp.toml`, the FastAPI app launches the FastMCP process on boot and registers its tools automatically.
- To run the server manually for testing: `fastmcp run mcps/time_helper.py:mcp`.

## Running Locally

```bash
uv run uvicorn app.main:app --reload
# Frontend: http://localhost:8000/
```

Ensure `OPENAI_API_KEY` is set (via `.env`). For MCP stdio, ensure `fastmcp` CLI is in PATH (same venv recommended).
If you use the shorthand `url = "path/to/server.py"` config, ensure you're running under a Python environment with `fastmcp` installed.

## Troubleshooting

- No MCP tools: check startup logs for FastMCP launch failures; validate `config/mcp.toml` path and that `fastmcp` is installed.
- Streaming shows raw SSE lines: hard-refresh; the SSE parser is in `app/static/ui/stream.js`.
