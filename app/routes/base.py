"""Base application routes."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", tags=["System"])
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)
