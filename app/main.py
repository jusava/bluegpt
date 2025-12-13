import uvicorn

from .web import create_app

app = create_app()


# Convenience for local dev server: uvicorn app.main:app --reload
def run(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run()
