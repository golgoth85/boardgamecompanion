from contextlib import asynccontextmanager

from fastapi import FastAPI

from boardgamecompanion import __version__
from boardgamecompanion.settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    yield


app = FastAPI(
    title="BoardGameCompanion",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "storage": {
            "config": str(settings.config_dir),
            "import": str(settings.import_dir),
            "manuals": str(settings.manuals_dir),
        },
    }
