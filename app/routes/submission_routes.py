"""Submission routes for QR-based operational document tracking."""

import uuid
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.document_schema import DocumentSubmissionSchema
from app.services.approver_service import get_approver_by_slug
from app.services.document_service import attach_file_to_document, create_document
from app.services.status_service import ALLOWED_DOCUMENT_STATUSES

UPLOADS_DIR = Path(__file__).resolve().parents[1] / "uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


@router.get("/submit/{slug}", tags=["Submission"])
def get_submission_page(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    return templates.TemplateResponse(
        request=request,
        name="submission_form.html",
        context={
            "approver": approver,
            "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
            "allowed_document_types": ("Invoice", "PAM"),
            "success_message": _build_success_message(request),
            "error_message": request.query_params.get("upload_error"),
            "form_data": {
                "document_type": "Invoice",
                "invoice_number": "",
                "qty_price": "",
                "status": "Pending",
                "notes": "",
            },
        },
    )


@router.post("/submit/{slug}", tags=["Submission"])
async def submit_document(
    request: Request,
    slug: str,
    document_type: str = Form(...),
    invoice_number: str = Form(...),
    qty_price: str = Form(...),
    status: str = Form(...),
    notes: str = Form(default=""),
    attachment: UploadFile | None = File(default=None),
    camera_attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    cleaned_form_data = {
        "document_type": document_type.strip(),
        "invoice_number": invoice_number.strip(),
        "qty_price": qty_price.strip(),
        "status": status.strip(),
        "notes": notes.strip(),
    }

    try:
        document_data = DocumentSubmissionSchema(
            document_type=cleaned_form_data["document_type"],
            invoice_number=cleaned_form_data["invoice_number"],
            qty_price=cleaned_form_data["qty_price"],
            status=cleaned_form_data["status"],
            notes=cleaned_form_data["notes"] or None,
        )
    except ValidationError:
        return templates.TemplateResponse(
            request=request,
            name="submission_form.html",
            context={
                "approver": approver,
                "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
                "allowed_document_types": ("Invoice", "PAM"),
                "form_data": cleaned_form_data,
                "success_message": None,
                "error_message": "Document type, invoice number, qty price, and status are required.",
            },
            status_code=422,
        )

    if document_data.document_type not in {"Invoice", "PAM"}:
        return templates.TemplateResponse(
            request=request,
            name="submission_form.html",
            context={
                "approver": approver,
                "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
                "allowed_document_types": ("Invoice", "PAM"),
                "form_data": cleaned_form_data,
                "success_message": None,
                "error_message": "Document type must be Invoice or PAM.",
            },
            status_code=422,
        )

    if document_data.status not in ALLOWED_DOCUMENT_STATUSES:
        return templates.TemplateResponse(
            request=request,
            name="submission_form.html",
            context={
                "approver": approver,
                "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
                "allowed_document_types": ("Invoice", "PAM"),
                "form_data": cleaned_form_data,
                "success_message": None,
                "error_message": "Status must be Pending, Approved, or Rejected.",
            },
            status_code=422,
        )

    upload_error_message = None

    try:
        document = create_document(
            db=db,
            approver_id=approver.id,
            document_data=document_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploaded_attachment = _pick_uploaded_attachment(camera_attachment, attachment)
    if uploaded_attachment and uploaded_attachment.filename:
        file_content = await uploaded_attachment.read()
        if len(file_content) > MAX_FILE_SIZE:
            upload_error_message = "Attachment is too large. Maximum file size is 10 MB."
        else:
            saved_path = _save_uploaded_file(uploaded_attachment.filename, file_content)
            if saved_path:
                attach_file_to_document(
                    db=db,
                    document_id=document.id,
                    uploaded_by=document.submitter_id,
                    original_name=uploaded_attachment.filename,
                    stored_name=saved_path.name,
                    file_path=f"uploads/{saved_path.name}",
                    content_type=uploaded_attachment.content_type or "application/octet-stream",
                    file_size=len(file_content),
                )

    return RedirectResponse(
        url=_build_success_redirect_url(
            approver.slug,
            document.doc_number,
            upload_error_message,
        ),
        status_code=303,
    )


def _save_uploaded_file(original_name: str, content: bytes) -> Path | None:
    """Save uploaded file with UUID name, return path."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    extension = Path(original_name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOADS_DIR / stored_name

    file_path.write_bytes(content)
    return file_path


def _build_success_message(request: Request) -> str | None:
    if request.query_params.get("success") != "1":
        return None

    document_number = request.query_params.get("doc")
    if document_number:
        return f"Document submitted successfully. Reference: {document_number}"

    return "Document submitted successfully."


def _build_success_redirect_url(
    slug: str,
    document_number: str,
    upload_error_message: str | None,
) -> str:
    redirect_url = f"/submit/{slug}?success=1&doc={document_number}"
    if upload_error_message:
        redirect_url += f"&upload_error={quote_plus(upload_error_message)}"
    return redirect_url


def _pick_uploaded_attachment(
    camera_attachment: UploadFile | None,
    attachment: UploadFile | None,
) -> UploadFile | None:
    if camera_attachment and camera_attachment.filename:
        return camera_attachment
    if attachment and attachment.filename:
        return attachment
    return None
