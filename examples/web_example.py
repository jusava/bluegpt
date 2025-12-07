"""Simple script/notebook-style example to call the agent API directly."""
import asyncio
import json
import os

import httpx

BASE_URL = os.getenv("BLUEGPT_BASE_URL", "http://localhost:8000")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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
    asyncio.run(main())
