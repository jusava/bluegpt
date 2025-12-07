import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


def _run(coro):
    return asyncio.run(coro)


def _make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_health_endpoint() -> None:
    async def main():
        async with _make_client() as client:
            resp = await client.get("/health")
            return resp

    resp = _run(main())
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_model_endpoint() -> None:
    async def main():
        async with _make_client() as client:
            resp = await client.get("/api/model")
            return resp

    resp = _run(main())
    assert resp.status_code == 200
    data = resp.json()
    assert "model" in data
    assert "available" in data
    assert isinstance(data["available"], list)
    assert data["model"] in data["available"]
