from app.tools.config import _server_specs_from_config


def test_server_specs_shorthand_url() -> None:
    config = {"servers": [{"name": "one", "url": "https://example.com/mcp"}]}
    assert _server_specs_from_config(config) == [("one", "https://example.com/mcp")]


def test_server_specs_full_config() -> None:
    config = {
        "servers": [
            {
                "name": "local_server",
                "transport": "stdio",
                "command": "python",
                "args": ["./server.py", "--verbose"],
                "cwd": ".",
            }
        ]
    }

    specs = _server_specs_from_config(config)
    assert len(specs) == 1
    name, spec = specs[0]
    assert name == "local_server"
    assert spec == {
        "mcpServers": {
            "local_server": {
                "transport": "stdio",
                "command": "python",
                "args": ["./server.py", "--verbose"],
                "cwd": ".",
            }
        }
    }
