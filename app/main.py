"""Application entry point for TRACKFLOW."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database.initializer import initialize_database
from app.routes.base import router as base_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.qr_routes import router as qr_router
from app.routes.submission_routes import router as submission_router

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup and shutdown lifecycle manager."""
    initialize_database()
    yield


app = FastAPI(
    title="TRACKFLOW",
    description="QR Document Tracking & Submission System.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=BASE_DIR / "uploads"), name="uploads")

app.include_router(base_router)
app.include_router(dashboard_router)
app.include_router(qr_router)
app.include_router(submission_router)
