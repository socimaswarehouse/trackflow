"""Submission routes for QR-based operational document tracking."""

import json
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
    find_open_document_by_pam,
    get_open_pam_options,
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
    db: Session = Depends(get_db),
):
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    form_data = await request.form()
    
    # Extract & sanitize PAM number
    pam_number = form_data.get("pam_number", "").strip()
    
    # Extract invoice data from JSON (from frontend tabbed system)
    invoice_data_json_str = form_data.get("invoice_data_json", "[]").strip()
    try:
        invoice_data_list = json.loads(invoice_data_json_str) if invoice_data_json_str else []
    except json.JSONDecodeError:
        invoice_data_list = []
    
    # Extract invoices from frontend data
    invoices = [inv.get("invoiceNumber", "") for inv in invoice_data_list if inv.get("invoiceNumber", "").strip()]
    invoice_number_str = json.dumps(invoices)
    
    qty_price = form_data.get("qty_price", "").strip()
    qty_currency = form_data.get("qty_currency", "IDR").strip()
    tc_type_val = form_data.get("tc_type", "").strip()
    tc = "Yes" if tc_type_val in ("Import", "Export") else "No"
    status = form_data.get("status", "Pending").strip()
    notes = form_data.get("notes", "").strip()
    
    # Extract TC fields
    tc_details_json = None
    tc_details_dict = {}
    kode_bl_val = None
    no_si_val = None
    no_si_list = []
    vessel_name_val = None
    
    if tc == "Yes":
        tc_type_val = form_data.get("tc_type", "").strip()

        # Build tc_details from per-invoice subCharges in invoice_data_list
        # (HTML form checkboxes are reset after each invoice save, so we read
        # from the already-collected invoice_data_list instead)
        tc_details_dict = {}
        if invoice_data_list:
            for inv_item in invoice_data_list:
                for charge in inv_item.get("subCharges", []):
                    charge_key = charge.get("name", "").lower().replace(" ", "_").replace("-", "_")
                    if charge_key and charge_key not in tc_details_dict:
                        tc_details_dict[charge_key] = {
                            "checked": True,
                            "label": charge.get("name", ""),
                            "amount": charge.get("amount", ""),
                        }
        tc_details_json = json.dumps(tc_details_dict) if tc_details_dict else None

        if tc_type_val == "Import":
            # Extract BL from first invoice or from form
            if invoice_data_list and len(invoice_data_list) > 0:
                kode_bl_val = invoice_data_list[0].get("blOrSi", "").strip()
            else:
                kode_bl_val = form_data.get("kode_bl", "").strip()
            no_si_val = json.dumps([])
        elif tc_type_val == "Export":
            kode_bl_val = None
            # Extract SI from all invoices
            if invoice_data_list and len(invoice_data_list) > 0:
                no_si_list = [inv.get("blOrSi", "").strip() for inv in invoice_data_list if inv.get("blOrSi", "").strip()]
            else:
                no_si_list = []
            no_si_val = json.dumps(no_si_list)
        
        # Extract vessel name from first invoice or form
        if invoice_data_list and len(invoice_data_list) > 0:
            vessel_name_val = invoice_data_list[0].get("vesselName", "").strip()
        else:
            vessel_name_val = form_data.get("vessel_name", "").strip()
        
    # Save the full per-invoice detail JSON (including blOrSi, vesselName,
    # subCharges per invoice) into invoice_numbers_json so that the dashboard
    # can display distinct details per invoice.
    invoice_numbers_json_str = invoice_data_json_str if invoice_data_list else invoice_number_str

    cleaned_form_data = {
        "document_type": "PAM",
        "invoice_number": invoice_number_str,
        "qty_price": qty_price,
        "qty_currency": qty_currency,
        "tc": tc,
        "status": status,
        "notes": notes,
        "pam_number": pam_number,
        "invoice_numbers_json": invoice_numbers_json_str,
        "tc_type": tc_type_val,
        "tc_details": tc_details_json,
        "kode_bl": kode_bl_val,
        "no_si": no_si_val,
        "vessel_name": vessel_name_val,
    }

    # Pass raw forms for ease of re-rendering in case of validation errors
    form_data_for_render = {
        **cleaned_form_data,
        "invoice_list": invoices if invoices else [""],
        "tc_details_dict": tc_details_dict,
        "no_si_list": no_si_list if no_si_list else [""],
        "invoice_data_json": invoice_data_json_str,
    }

    validation_error = _validate_document_submission(cleaned_form_data)
    if validation_error:
        return _render_user_submission_page(
            request=request,
            user=user,
            active_document=_get_user_active_document(request, db, user.id),
            success_message=None,
            error_message=validation_error,
            form_data=form_data_for_render,
            status_code=422,
        )

    document_data = DocumentSubmissionSchema(
        document_type=cleaned_form_data["document_type"],
        invoice_number=cleaned_form_data["invoice_number"],
        qty_price=cleaned_form_data["qty_price"],
        tc=cleaned_form_data["tc"],
        status=cleaned_form_data["status"],
        notes=cleaned_form_data["notes"] or None,
        pam_number=cleaned_form_data["pam_number"],
        invoice_numbers_json=cleaned_form_data["invoice_numbers_json"],
        tc_type=cleaned_form_data["tc_type"],
        tc_details=cleaned_form_data["tc_details"],
        kode_bl=cleaned_form_data["kode_bl"],
        no_si=cleaned_form_data["no_si"],
        vessel_name=cleaned_form_data["vessel_name"],
    )

    try:
        document = create_document(
            db=db,
            submitter_id=user.id,
            document_data=document_data,
            currency=cleaned_form_data.get("qty_currency", "IDR"),
        )
    except ValueError as exc:
        return _render_user_submission_page(
            request=request,
            user=user,
            active_document=_get_user_active_document(request, db, user.id),
            success_message=None,
            error_message=str(exc),
            form_data=form_data_for_render,
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
        db=db,
    )


@router.post("/submit/{slug}", tags=["Submission"])
async def submit_approver_handoff(
    request: Request,
    slug: str,
    pam_number: str = Form(...),
    attachment: UploadFile | None = File(default=None),
    camera_attachment: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    approver = get_approver_by_slug(db, slug)
    if approver is None:
        raise HTTPException(status_code=404, detail="Approver not found")

    cleaned_pam_number = pam_number.strip()
    active_document = find_open_document_by_pam(db, cleaned_pam_number)
    uploaded_attachment = _pick_uploaded_attachment(camera_attachment, attachment)

    if not cleaned_pam_number:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=None,
            success_message=None,
            error_message="PAM Number wajib diisi sebelum upload bukti dokumen.",
            form_pam_number=pam_number,
            status_code=422,
            db=db,
        )

    if active_document is None:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=None,
            success_message=None,
            error_message=(
                "PAM Number tidak ditemukan di Document Data Submission "
                "atau dokumen tersebut sudah selesai/rejected."
            ),
            form_pam_number=cleaned_pam_number,
            status_code=422,
            db=db,
        )

    if uploaded_attachment is None or not uploaded_attachment.filename:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=active_document,
            success_message=None,
            error_message="Foto atau file dokumen wajib diupload saat scan QR approver.",
            form_pam_number=cleaned_pam_number,
            status_code=422,
            db=db,
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
            form_pam_number=cleaned_pam_number,
            status_code=422,
            db=db,
        )

    file_content = await uploaded_attachment.read()
    if len(file_content) > MAX_FILE_SIZE:
        return _render_approver_upload_page(
            request=request,
            approver=approver,
            active_document=active_document,
            success_message=None,
            error_message="Attachment is too large. Maximum file size is 10 MB.",
            form_pam_number=cleaned_pam_number,
            status_code=422,
            db=db,
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
    form_data: dict[str, any] | None = None,
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
    form_pam_number: str | None = None,
    status_code: int = 200,
    db: Session | None = None,
):
    pam_options = get_open_pam_options(db) if db is not None else []
    return templates.TemplateResponse(
        request=request,
        name="approver_upload_form.html",
        context={
            "approver": approver,
            "active_document": active_document,
            "success_message": success_message,
            "error_message": error_message,
            "pam_options": pam_options,
            "form_pam_number": (
                form_pam_number
                if form_pam_number is not None
                else active_document.pam_number
                if active_document is not None
                else ""
            ),
        },
        status_code=status_code,
    )


def _default_form_data() -> dict[str, any]:
    return {
        "document_type": "PAM",
        "invoice_number": "",
        "qty_price": "",
        "tc": "No",
        "status": "Pending",
        "notes": "",
        "pam_number": "",
        "invoice_list": [""],
        "tc_type": "",
        "tc_details_dict": {},
        "kode_bl": "",
        "no_si_list": [""],
        "vessel_name": "",
        "invoice_data_json": "[]",
    }


def _validate_document_submission(form_data: dict[str, any]) -> str | None:
    try:
        document_data = DocumentSubmissionSchema(
            document_type=form_data["document_type"],
            invoice_number=form_data["invoice_number"],
            qty_price=form_data["qty_price"],
            tc=form_data["tc"],
            status=form_data["status"],
            notes=form_data["notes"] or None,
            pam_number=form_data.get("pam_number"),
            invoice_numbers_json=form_data.get("invoice_numbers_json"),
            tc_type=form_data.get("tc_type"),
            tc_details=form_data.get("tc_details"),
            kode_bl=form_data.get("kode_bl"),
            no_si=form_data.get("no_si"),
            vessel_name=form_data.get("vessel_name"),
        )
    except ValidationError:
        return "PAM Number, Invoice Number, Qty/Price, and Status are required."

    if not document_data.pam_number or "/SCM/" not in document_data.pam_number:
        return "Document PAM Number is required and must follow the format ***/SCM/Bulan/Tahun."

    # Validate that we have at least one non-empty invoice number
    try:
        inv_list = json.loads(document_data.invoice_number) if document_data.invoice_number else []
        if not inv_list or not any(inv.strip() for inv in inv_list):
            return "At least one Invoice Number is required."
    except Exception:
        return "Invoice Number must be a valid list."

    if document_data.qty_price and not str(document_data.qty_price).strip():
        return "Qty / Price is required."

    if document_data.tc not in ALLOWED_TC_OPTIONS:
        return "TC must be Yes or No."

    if document_data.tc == "Yes":
        if document_data.tc_type not in ("Export", "Import"):
            return "Please select Import or Export for Shipment Type."
        if document_data.tc_type == "Import":
            if not document_data.kode_bl or not document_data.kode_bl.strip():
                return "No BL is required when Shipment Type is Import."
        if document_data.tc_type == "Export":
            try:
                si_list = json.loads(document_data.no_si) if document_data.no_si else []
                if not si_list or not any(si.strip() for si in si_list):
                    return "At least one No SI is required when Shipment Type is Export."
            except Exception:
                return "No SI must be a valid list."
        if not document_data.vessel_name or not document_data.vessel_name.strip():
            return "Vessel Name is required when Shipment Type is selected."

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

    if document.invoice_number:
        try:
            invs = json.loads(document.invoice_number)
            document.invoice_display = ", ".join(invs)
        except Exception:
            document.invoice_display = document.invoice_number
    else:
        document.invoice_display = ""

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
