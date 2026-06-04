"""Permanent QR routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_public_base_url
from app.database.session import get_db
from app.services.approver_service import (
    get_approver_by_slug,
    update_approver_qr_path,
)
from app.services.user_service import get_user_by_id
from app.utils.qr_generator import generate_qr_code, generate_qr_png_bytes

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

    base_url = get_public_base_url(request)
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
            "entity_name": approver.approval_name,
            "entity_subtitle": approver.department,
            "entity_label": "Approver",
            "qr_status": qr_status,
            "qr_image_src": f"/qr-image/approver/{approver.slug}",
            "qr_image_url": f"/{qr_path}",
            "target_url": f"{base_url}/submit/{approver.slug}",
            "open_page_url": f"{base_url}/submit/{approver.slug}",
            "open_page_label": "Open Upload Page",
            "page_description": "Scan QR approver ini untuk upload bukti bahwa dokumen fisik sudah berada di approver tersebut.",
        },
    )


@router.get("/generate-user-qr/{user_id}", tags=["QR"])
def generate_user_qr(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    base_url = get_public_base_url(request)
    qr_slug = f"user-{user.id}"
    target_url = f"{base_url}/submit/user/{user.id}"
    qr_path = generate_qr_code(qr_slug, target_url)

    return templates.TemplateResponse(
        request=request,
        name="qr_detail.html",
        context={
            "entity_name": user.full_name,
            "entity_subtitle": user.department,
            "entity_label": "User",
            "qr_status": "QR Ready",
            "qr_image_src": f"/qr-image/user/{user.id}",
            "qr_image_url": f"/{qr_path}",
            "target_url": f"{base_url}/submit/user/{user.id}",
            "open_page_url": f"{base_url}/submit/user/{user.id}",
            "open_page_label": "Open Submission Page",
            "page_description": "Scan QR user ini untuk mengisi data dokumen lebih dulu sebelum dokumen fisik diserahkan ke approver.",
        },
    )


def _is_existing_qr_available(qr_path: str | None) -> bool:
    if not qr_path:
        return False

    absolute_path = Path(__file__).resolve().parents[1] / qr_path
    return absolute_path.exists()


@router.get("/qr-image/approver/{slug}", tags=["QR"])
def get_approver_qr_image(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    base_url = get_public_base_url(request)
    target_url = f"{base_url}/submit/{approver.slug}"
    return Response(
        content=generate_qr_png_bytes(target_url),
        media_type="image/png",
    )


@router.get("/qr-image/user/{user_id}", tags=["QR"])
def get_user_qr_image(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    base_url = get_public_base_url(request)
    target_url = f"{base_url}/submit/user/{user.id}"
    return Response(
        content=generate_qr_png_bytes(target_url),
        media_type="image/png",
    )
