import os
import uvicorn

from .web import create_app

app = create_app()


# Convenience for local dev server: uvicorn app.main:app --reload
def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("RELOAD", False)),
    )


if __name__ == "__main__":
    run()
