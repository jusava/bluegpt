## BlueGPT

Local-first web UI that feels like ChatGPT/Gemini, backed by the OpenAI **Responses API** with an agentic loop and optional MCP tool connections.

### Quickstart

1. Create a virtual env (Python 3.13) and install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
2. Copy `.env.example` to `.env` and set your OpenAI key (and optionally model/base URL):
   ```bash
   cp .env.example .env
   # then edit .env with:
   # OPENAI_API_KEY=sk-...
   # OPENAI_MODEL=gpt-4o-mini   # optional
   # OPENAI_BASE_URL=...        # optional, for self-hosted endpoints
   ```
3. Run the app:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Open `http://localhost:8000/` in a browser.

### MCP integration

You can register HTTP-exposed MCP tools via `MCP_HTTP_TOOLS` (JSON array). Each entry should include a name, description, parameters schema, and an endpoint the server can call:
```bash
export MCP_HTTP_TOOLS='[
  {
    "name": "docs_search",
    "description": "Search internal documentation",
    "endpoint": "http://localhost:9000/tools/docs_search",
    "parameters": {
      "type": "object",
      "properties": { "query": { "type": "string" } },
      "required": ["query"]
    }
  }
]'
```
The tool definitions are surfaced to the OpenAI function-calling interface so the model can invoke them during the agentic loop.

You can also provide a TOML config file (default `mcp.toml`, override with `MCP_CONFIG_FILE`) to register HTTP tools, FastMCP stdio servers (auto-discovery), and manual stdio tools. See the sample `mcp.toml` for structure:
```toml
[mcp]
[[mcp.http]]
name = "docs_search"
description = "Search docs"
endpoint = "http://localhost:9000/tools/docs_search"
parameters.type = "object"

[[mcp.stdio_servers]]
command = "fastmcp"
args = ["run", "app/mcp_fast_time.py:mcp"]
prefix = "fast_"
cwd = "."

[[mcp.stdio_tools]]
name = "utc_time"
description = "UTC via FastMCP stdio"
command = "fastmcp"
args = ["run", "app/mcp_fast_time.py:mcp"]
parameters.type = "object"
parameters.properties = {}
parameters.additionalProperties = false
```

#### Sample MCP HTTP server (UTC time)

1. Start the sample server (separate terminal):
   ```bash
   uv run uvicorn app.mcp_server:app --reload --port 9000
   ```
2. Point the agent to it:
   ```bash
   export MCP_HTTP_TOOLS='[
     {
       "name": "mcp_utc_time",
       "description": "Return current UTC time via MCP sample server",
       "endpoint": "http://127.0.0.1:9000/tools/utc_time",
       "parameters": { "type": "object", "properties": {}, "additionalProperties": false }
     }
   ]'
   ```
3. Restart the main app and ask the chat to use `mcp_utc_time`.

#### Sample FastMCP stdio server (UTC time)

1. Start the FastMCP server (stdio transport by default):
   ```bash
   fastmcp run app/mcp_fast_time.py:mcp
   ```
2. Point the agent to it using `MCP_STDIO_TOOLS`:
   ```bash
   export MCP_STDIO_TOOLS='[
     {
       "name": "utc_time",
       "description": "UTC via FastMCP stdio",
       "command": "fastmcp",
       "args": ["run", "app/mcp_fast_time.py:mcp"],
       "parameters": { "type": "object", "properties": {}, "additionalProperties": false }
     }
   ]'
   ```
3. Restart the main app and ask the chat to call `utc_time`. The client launches the FastMCP server via stdio when needed.

You can also let the agent discover tools from a FastMCP stdio server automatically (no manual tool definitions) by setting `MCP_STDIO_SERVERS`:
```bash
export MCP_STDIO_SERVERS='[
  {
    "command": "fastmcp",
    "args": ["run", "app/mcp_fast_time.py:mcp"],
    "prefix": "fast_",        # optional: add a prefix to discovered tool names
    "env": {},                # optional
    "cwd": "."                # optional
  }
]'
```
On startup, the agent will launch the server over stdio, discover its tools, and register them for use.

### API

- `POST /api/chat` → `{chat_id, reply, tools}`  
- `POST /api/chat/stream` (SSE over fetch) → streaming reply chunks, `done` event carries `chat_id`  
- `GET /api/sessions` → simple list of recent chat ids/titles  
- `GET /` → Chat-style frontend

### Notes

- The backend uses the OpenAI Responses API (function/tool calling) with a local loop that submits tool outputs before returning text.
- The backend keeps chat history in memory per `chat_id`. Restarting the server clears it.
- The UI streams responses and falls back to non-streaming if SSE is unavailable.
- Styling is intentionally opinionated to echo the modern chat experience without needing a JS bundler.
