## BlueGPT

Local-first chat UI powered by the OpenAI **Responses API**, a FastAPI backend, and an agentic loop that can call FastMCP tools over stdio or HTTP.

### Features
- Agent loop with Responses API tool calling and reasoning traces streamed to the UI.
- FastMCP stdio/HTTP tool discovery from `config/mcp.toml`; toggle tools on/off from the Settings panel or `/api/tools`.
- Config-driven defaults for model, reasoning effort, prompts, and sample suggestions.
- Lightweight static frontend that streams text chunks and shows tool/reasoning events.
- In-memory chat sessions with quick session switching (cleared on restart).

### Quickstart
1. Create a virtual env (Python 3.13) and install deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
   (Alternatively, `uv run uvicorn app.main:app --reload` if you use uv.)
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL`):
   ```bash
   cp .env.example .env
   ```
3. Run the app:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Open `http://localhost:8000/` in a browser.

### Configuration
- `config/config.toml` (override with `APP_CONFIG_FILE`): default model, allowed models, reasoning effort defaults, text verbosity, and max output tokens.
- `config/prompts.toml` (override with `PROMPTS_CONFIG_FILE`): system prompt injected into new chats.
- `config/samples.toml` (override with `SAMPLES_CONFIG_FILE`): quick-start suggestion cards shown in the UI.
- `config/mcp.toml` (override with `MCP_CONFIG_FILE`): FastMCP servers to auto-discover tools from. Shorthand entries with only `url` are passed directly to `fastmcp.Client(...)` (transport inferred); entries with extra fields are treated as full MCP server configs. Example:
  ```toml
  [mcp]
  [[mcp.servers]]
  name = "time_helper"
  url = "mcps/time_helper.py"
  # env = { EXAMPLE = "1" }
  ```
  Each server is discovered at backend boot and its tools are registered without renaming, so tool names match the server definitions.

### MCP quickstart
- The repo includes `mcps/time_helper.py` (FastMCP) exposing `current_time` and `find_timezone`.
- With the sample `config/mcp.toml`, the FastAPI app will launch the stdio FastMCP process automatically on startup.
- If you want to run it manually over stdio: `fastmcp run mcps/time_helper.py:mcp`.
- For an HTTP example, start `mcps/time_helper_http.py` (serves on `http://127.0.0.1:9001/mcp`) and add another `[[mcp.servers]]` entry.

### API
- `GET /health` → health probe.
- `GET /` → static chat UI.
- `GET /api/sessions` → list of in-memory chats.
- `GET /api/chat/{chat_id}` → return text history for a chat.
- `POST /api/chat` → non-streaming reply `{chat_id, reply, tools}`.
- `POST /api/chat/stream` → SSE stream of text chunks plus `tool_start`, `tool_result`, and `reasoning` events; `done` event carries `chat_id`.
- `GET /api/tools` → tool summaries; `POST /api/tools/{name}/active` to toggle.
- `GET|POST /api/model` → read/update the active model (resets reasoning effort to the first allowed option).
- `GET|POST /api/generation` → read/update reasoning effort, text verbosity, and max output tokens.
- `GET /api/samples` → UI suggestion payload.

### Project layout
- `app/main.py` FastAPI surface and endpoints.
- `app/agent.py` agent loop, OpenAI client wiring, and in-memory session store.
- `app/tools/` FastMCP stdio/HTTP integration and tool registry.
- `app/static/*` static frontend (no bundler).
- `config/*.toml` configuration files; see above for overrides.
- `mcps/` sample FastMCP servers; `tests/` basic smoke tests.

### Notes
- Tool/process discovery happens at startup; check logs if a FastMCP process fails to launch.
- Run tests with `pytest`.
