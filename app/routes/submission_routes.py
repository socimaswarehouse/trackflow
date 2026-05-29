"""Submission routes for QR-based operational document tracking."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models.document import Document
from app.schemas.document_schema import DocumentSubmissionSchema
from app.services.approver_service import get_approver_by_slug
from app.services.document_service import (
    ALLOWED_TC_OPTIONS,
    assign_document_to_approver,
    attach_file_to_document,
    create_document,
    find_open_document_by_invoice,
    get_open_invoice_options,
)
from app.services.status_service import ALLOWED_DOCUMENT_STATUSES, attach_display_status
from app.services.user_service import get_user_by_id

UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ACTIVE_DOCUMENT_COOKIE = "trackflow_active_document_id"
ALLOWED_DOCUMENT_TYPES = ("Invoice", "PAM")

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


@router.get("/submit/user/{user_id}", tags=["Submission"])
def get_user_submission_page(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    active_document = _get_user_active_document(request, db, user.id)
    return _render_user_submission_page(
        request=request,
        user=user,
        active_document=active_document,
        success_message=_build_user_success_message(request),
        error_message=request.query_params.get("error"),
    )


@router.post("/submit/user/{user_id}", tags=["Submission"])
async def submit_user_document(
    request: Request,
    user_id: int,
    document_type: str = Form(...),
    invoice_number: str = Form(...),
    qty_price: str = Form(...),
    tc: str = Form(...),
    status: str = Form(...),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    cleaned_form_data = {
        "document_type": document_type.strip(),
        "invoice_number": invoice_number.strip(),
        "qty_price": qty_price.strip(),
        "tc": tc.strip(),
        "status": status.strip(),
        "notes": notes.strip(),
    }

    validation_error = _validate_document_submission(cleaned_form_data)
    if validation_error:
        return _render_user_submission_page(
            request=request,
            user=user,
            active_document=_get_user_active_document(request, db, user.id),
            success_message=None,
            error_message=validation_error,
            form_data=cleaned_form_data,
            status_code=422,
        )

    document_data = DocumentSubmissionSchema(
        document_type=cleaned_form_data["document_type"],
        invoice_number=cleaned_form_data["invoice_number"],
        qty_price=cleaned_form_data["qty_price"],
        tc=cleaned_form_data["tc"],
        status=cleaned_form_data["status"],
        notes=cleaned_form_data["notes"] or None,
    )

    try:
        document = create_document(
            db=db,
            submitter_id=user.id,
            document_data=document_data,
        )
    except ValueError as exc:
        return _render_user_submission_page(
            request=request,
            user=user,
            active_document=_get_user_active_document(request, db, user.id),
            success_message=None,
            error_message=str(exc),
            form_data=cleaned_form_data,
            status_code=422,
        )

    response = RedirectResponse(
        url=f"/submit/user/{user.id}?success=1&doc={document.doc_number}",
        status_code=303,
    )
    response.set_cookie(
        key=ACTIVE_DOCUMENT_COOKIE,
        value=str(document.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@router.get("/submit/{slug}", tags=["Submission"])
def get_approver_upload_page(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    active_document = _get_active_document_from_request(request, db)
    page_error = request.query_params.get("error")

    return _render_approver_upload_page(
        request=request,
        approver=approver,
        active_document=active_document,
        success_message=_build_approver_success_message(request),
        error_message=page_error,
    )


@router.post("/submit/{slug}", tags=["Submission"])
async def submit_approver_handoff(
    request: Request,
    slug: str,
    invoice_number: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    camera_attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    cleaned_invoice_number = invoice_number.strip()
    active_document = find_open_document_by_invoice(db, cleaned_invoice_number)
    uploaded_attachment = _pick_uploaded_attachment(camera_attachment, attachment)

    if not cleaned_invoice_number:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=None,
            success_message=None,
            error_message="Invoice Number wajib diisi sebelum upload bukti dokumen.",
            form_invoice_number=invoice_number,
            status_code=422,
        )

    if active_document is None:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=None,
            success_message=None,
            error_message=(
                "Invoice Number tidak ditemukan di Document Data Submission "
                "atau dokumen tersebut sudah selesai/rejected."
            ),
            form_invoice_number=cleaned_invoice_number,
            status_code=422,
        )

    if uploaded_attachment is None or not uploaded_attachment.filename:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=active_document,
            success_message=None,
            error_message="Foto atau file dokumen wajib diupload saat scan QR approver.",
            form_invoice_number=cleaned_invoice_number,
            status_code=422,
        )

    try:
        active_document = assign_document_to_approver(
            db=db,
            document=active_document,
            approver=approver,
        )
    except ValueError as exc:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=active_document,
            success_message=None,
            error_message=str(exc),
            form_invoice_number=cleaned_invoice_number,
            status_code=422,
        )

    file_content = await uploaded_attachment.read()
    if len(file_content) > MAX_FILE_SIZE:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=active_document,
            success_message=None,
            error_message="Attachment is too large. Maximum file size is 10 MB.",
            form_invoice_number=cleaned_invoice_number,
            status_code=422,
        )

    saved_path = _save_uploaded_file(uploaded_attachment.filename, file_content)
    attach_file_to_document(
        db=db,
        document_id=active_document.id,
        uploaded_by=active_document.submitter_id,
        original_name=uploaded_attachment.filename,
        stored_name=saved_path.name,
        file_path=f"uploads/{saved_path.name}",
        content_type=uploaded_attachment.content_type or "application/octet-stream",
        file_size=len(file_content),
    )

    response = RedirectResponse(
        url=f"/submit/{approver.slug}?success=1&doc={active_document.doc_number}",
        status_code=303,
    )
    response.set_cookie(
        key=ACTIVE_DOCUMENT_COOKIE,
        value=str(active_document.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


def _save_uploaded_file(original_name: str, content: bytes) -> Path | None:
    """Save uploaded file with UUID name, return path."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    extension = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOADS_DIR / stored_name

    file_path.write_bytes(content)
    return file_path


def _pick_uploaded_attachment(
    camera_attachment: UploadFile | None,
    attachment: UploadFile | None,
) -> UploadFile | None:
    if camera_attachment and camera_attachment.filename:
        return camera_attachment
    if attachment and attachment.filename:
        return attachment
    return None


def _render_user_submission_page(
    request: Request,
    user,
    active_document: Document | None,
    success_message: str | None,
    error_message: str | None,
    form_data: dict[str, str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="user_submission_form.html",
        context={
            "user": user,
            "active_document": active_document,
            "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
            "allowed_document_types": ALLOWED_DOCUMENT_TYPES,
            "allowed_tc_options": ALLOWED_TC_OPTIONS,
            "success_message": success_message,
            "error_message": error_message,
            "form_data": form_data or _default_form_data(),
        },
        status_code=status_code,
    )


def _render_approver_upload_page(
    request: Request,
    approver,
    active_document: Document | None,
    success_message: str | None,
    error_message: str | None,
    form_invoice_number: str | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request=request,
        name="approver_upload_form.html",
        context={
            "approver": approver,
            "active_document": active_document,
            "success_message": success_message,
            "error_message": error_message,
            "invoice_options": get_open_invoice_options(db),
            "form_invoice_number": (
                form_invoice_number
                if form_invoice_number is not None
                else active_document.invoice_number
                if active_document is not None
                else ""
            ),
        },
        status_code=status_code,
    )


def _default_form_data() -> dict[str, str]:
    return {
        "document_type": "Invoice",
        "invoice_number": "",
        "qty_price": "",
        "tc": "No",
        "status": "Pending",
        "notes": "",
    }


def _validate_document_submission(form_data: dict[str, str]) -> str | None:
    try:
        document_data = DocumentSubmissionSchema(
            document_type=form_data["document_type"],
            invoice_number=form_data["invoice_number"],
            qty_price=form_data["qty_price"],
            tc=form_data["tc"],
            status=form_data["status"],
            notes=form_data["notes"] or None,
        )
    except ValidationError:
        return "Document type, invoice number, qty price, and status are required."

    if document_data.document_type not in ALLOWED_DOCUMENT_TYPES:
        return "Document type must be Invoice or PAM."

    if document_data.tc not in ALLOWED_TC_OPTIONS:
        return "TC must be Yes or No."

    if document_data.status not in ALLOWED_DOCUMENT_STATUSES:
        return "Status must be Pending, Approved, or Rejected."

    return None


def _build_user_success_message(request: Request) -> str | None:
    if request.query_params.get("success") != "1":
        return None

    document_number = request.query_params.get("doc")
    if document_number:
        return (
            "Data dokumen berhasil disimpan. "
            f"Reference: {document_number}. Lanjut scan QR approver untuk upload bukti serah dokumen."
        )

    return "Data dokumen berhasil disimpan. Lanjut scan QR approver."


def _build_approver_success_message(request: Request) -> str | None:
    if request.query_params.get("success") != "1":
        return None

    document_number = request.query_params.get("doc")
    if document_number:
        return (
            "Bukti serah dokumen berhasil diupload dan Current Location sudah diperbarui. "
            f"Reference: {document_number}"
        )

    return "Bukti serah dokumen berhasil diupload dan Current Location sudah diperbarui."


def _get_active_document_from_request(
    request: Request,
    db: Session,
) -> Document | None:
    active_document_id = request.cookies.get(ACTIVE_DOCUMENT_COOKIE)
    if not active_document_id or not active_document_id.isdigit():
        return None

    document = (
        db.query(Document)
        .options(joinedload(Document.approver), joinedload(Document.files))
        .filter(Document.id == int(active_document_id))
        .first()
    )
    if document is None:
        return None

    return attach_display_status(document)


def _get_document_for_handoff(
    db: Session,
    document_id: int,
) -> Document | None:
    document = (
        db.query(Document)
        .options(joinedload(Document.approver), joinedload(Document.files))
        .filter(Document.id == document_id)
        .first()
    )
    if document is None:
        return None

    return attach_display_status(document)


def _get_user_active_document(
    request: Request,
    db: Session,
    user_id: int,
) -> Document | None:
    active_document = _get_active_document_from_request(request, db)
    if active_document is None or active_document.submitter_id != user_id:
        return None

    return active_document
