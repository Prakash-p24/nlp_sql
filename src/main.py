from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.core.config import get_logger
from src.api.router import router as api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI JWT Auth starting up")
    yield
    logger.info("FastAPI JWT Auth shutting down")


app = FastAPI(
    title="FastAPI JWT Auth",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health_check")
def health_check():
    return {"message": "FastAPI JWT Auth is running"}
