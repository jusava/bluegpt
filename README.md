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

You can provide a TOML config file (default `mcp.toml`, override with `MCP_CONFIG_FILE`) to register FastMCP stdio servers (auto-discovery). Tools are negotiated from the server; no manual tool definitions. See the sample `mcp.toml` for structure (config only; env discovery removed):
```toml
[mcp]
[[mcp.stdio_servers]]
command = "fastmcp"
args = ["run", "app/mcp_fast_time.py:mcp"]
prefix = "fast_"
cwd = "."
```

#### Sample FastMCP stdio server (time)

1. Start the FastMCP server (stdio transport by default):
   ```bash
   fastmcp run app/mcp_fast_time.py:mcp
   ```
2. Configure the agent via `mcp.toml` (`[[mcp.stdio_servers]]` as above).
3. Restart the main app and ask the chat to call `current_time` or `find_timezone`. The client launches the FastMCP server via stdio when needed.

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
