"""Simple script/notebook-style example to call the agent API directly."""
import argparse
import asyncio
import json

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the BlueGPT HTTP API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL (default: {DEFAULT_BASE_URL})")
    return parser.parse_args()


async def main(base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Start a new chat
        payload = {"message": "Hello!"}
        r = await client.post("/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        chat_id = data["chat_id"]
        print("Chat started:", chat_id)
        print("Assistant reply:", data["reply"])

        # Send a follow-up that should trigger tools
        payload = {"message": "What time is it in Helsinki?", "chat_id": chat_id}
        r = await client.post("/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        print("\nFollow-up reply:", data["reply"])
        print("Tools used:", json.dumps(data.get("tools", []), indent=2))

        # List sessions
        sessions = await client.get("/api/sessions")
        sessions.raise_for_status()
        print("\nSessions:", sessions.json())


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.base_url))
