"""Permanent approver QR routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_base_url
from app.database.session import get_db
from app.services.approver_service import (
    get_approver_by_slug,
    update_approver_qr_path,
)
from app.utils.qr_generator import generate_qr_code

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


@router.get("/generate-qr/{slug}", tags=["QR"])
def generate_approver_qr(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    base_url = get_base_url()
    qr_status = "Existing QR"
    qr_path = approver.qr_code_path

    if not _is_existing_qr_available(qr_path):
        target_url = f"{base_url}/submit/{approver.slug}"
        qr_path = generate_qr_code(approver.slug, target_url)
        approver = update_approver_qr_path(db, approver, qr_path)
        qr_status = "New QR Generated"

    return templates.TemplateResponse(
        request=request,
        name="qr_detail.html",
        context={
            "approver": approver,
            "qr_status": qr_status,
            "qr_image_url": f"/{qr_path}",
            "target_url": f"{base_url}/submit/{approver.slug}",
        },
    )


def _is_existing_qr_available(qr_path: str | None) -> bool:
    if not qr_path:
        return False

    absolute_path = Path(__file__).resolve().parents[1] / qr_path
    return absolute_path.exists()
