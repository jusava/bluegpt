"""Backend call example using the AgentSession directly (no HTTP).
Run with: uv run python backend_example.py
"""
import asyncio
import os

from app.agent import AgentManager


async def main() -> None:
    # Manager uses default registry/model from env.
    manager = AgentManager()
    session = manager.get_or_create(system_prompt=None, model=os.getenv("OPENAI_MODEL"))

    reply1 = await session.run("Hello!")
    print("First reply:\n", reply1)

    reply2 = await session.run("What time is it in Helsinki?")
    print("\nSecond reply:\n", reply2)

    print("\nTool trace:")
    for t in session.tool_trace:
        print(t)


if __name__ == "__main__":
    asyncio.run(main())
