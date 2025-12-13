"""Backend call example using the AgentSession directly (no HTTP).
Run with: uv run python backend_example.py
"""
import asyncio

from app.agent import AgentManager


async def main() -> None:
    # Manager uses defaults from config files.
    manager = AgentManager()
    session = manager.get_or_create()

    reply1 = await session.run("Hello!")
    print("First reply:\n", reply1)

    reply2 = await session.run("What time is it in Helsinki?")
    print("\nSecond reply:\n", reply2)


if __name__ == "__main__":
    asyncio.run(main())
