"""Dashboard and approver management routes."""
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.config import get_admin_nik, get_admin_password
from app.services.approver_service import (
    create_approver,
    delete_approver,
    get_all_approvers,
    get_document_count_for_approver,
)
from app.services.dashboard_service import get_dashboard_documents, get_dashboard_summary
from app.services.document_service import (
    ALLOWED_TC_OPTIONS,
    create_document,
    delete_document,
    update_document_details,
    _get_default_submitter_id,
)
from app.services.statistics_service import get_approval_statistics, get_chart_data_for_approvers
from app.services.status_service import ALLOWED_DOCUMENT_STATUSES
from app.services.user_service import get_all_employee_users, get_preferred_qr_user
from app.schemas.document_schema import DocumentSubmissionSchema

ALLOWED_DOCUMENT_TYPES = ("Invoice", "PAM")

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


@router.get("/dashboard", tags=["Dashboard"])
def get_dashboard(
    request: Request,
    search: str = Query(default=""),
    status: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    document_type: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Main dashboard page with document tracking and statistics."""
    documents = get_dashboard_documents(
        db,
        search=search or None,
        status=status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        document_type=document_type or None,
    )
    summary = get_dashboard_summary(db)
    stats = get_approval_statistics(db)
    approvers = get_all_approvers(db)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/document_tracking.html",
        context={
            "page_title": "Dashboard",
            "active_menu": "dashboard",
            "documents": documents,
            "approvers": approvers,
            "search_query": search,
            "selected_status": status,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_document_type": document_type,
            "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
            "allowed_document_types": ALLOWED_DOCUMENT_TYPES,
            "allowed_tc_options": ALLOWED_TC_OPTIONS,
            "approval_stats": stats,
            **summary,
        },
    )


@router.get("/dashboard/tracking-log", tags=["Dashboard"])
def get_tracking_log(
    request: Request,
    search: str = Query(default=""),
    status: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    document_type: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Dedicated page for operational tracking records."""
    documents = get_dashboard_documents(
        db,
        search=search or None,
        status=status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        document_type=document_type or None,
    )
    summary = get_dashboard_summary(db)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/tracking_log.html",
        context={
            "page_title": "Tracking Log",
            "active_menu": "tracking_log",
            "documents": documents,
            "search_query": search,
            "selected_status": status,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_document_type": document_type,
            "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
            "allowed_document_types": ALLOWED_DOCUMENT_TYPES,
            "allowed_tc_options": ALLOWED_TC_OPTIONS,
            **summary,
        },
    )


@router.get("/api/dashboard/statistics", tags=["Dashboard API"])
def get_statistics_api(db: Session = Depends(get_db)):
    """Get approval statistics as JSON for charts."""
    stats = get_approval_statistics(db)
    chart_data = get_chart_data_for_approvers(db)

    return JSONResponse({
        "stats": stats,
        "chart": chart_data,
    })


@router.get("/dashboard/approvers", tags=["Dashboard"])
def get_approver_management(
    request: Request,
    db: Session = Depends(get_db),
):
    """Approver management page."""
    approvers = get_all_approvers(db)
    summary = get_dashboard_summary(db)

    # Build a mapping of approver id -> document count for the template
    doc_counts = {
        a.id: get_document_count_for_approver(db, a.id) for a in approvers
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/approver_management.html",
        context={
            "page_title": "Approver Management",
            "active_menu": "approvers",
            "approvers": approvers,
            "doc_counts": doc_counts,
            "form_data": {
                "approval_name": "",
                "department": "",
            },
            "error_message": request.query_params.get("error"),
            "success_message": _build_approver_success_message(request),
            **summary,
        },
    )


@router.get("/dashboard/users", tags=["Dashboard"])
def get_user_qr_management(
    request: Request,
    search: str = Query(default=""),
    status: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    document_type: str = Query(default=""),
    qr_user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """User QR management page."""
    users = get_all_employee_users(db)
    generated_user = _prepare_generated_user_card(db, qr_user_id)
    documents = get_dashboard_documents(
        db,
        search=search or None,
        status=status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        document_type=document_type or None,
    )
    summary = get_dashboard_summary(db)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/user_qr_management.html",
        context={
            "page_title": "Document Request",
            "active_menu": "users",
            "users": users,
            "generated_user": generated_user,
            "documents": documents,
            "employee_count": len(users),
            "search_query": search,
            "selected_status": status,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_document_type": document_type,
            "allowed_statuses": ALLOWED_DOCUMENT_STATUSES,
            "allowed_document_types": ALLOWED_DOCUMENT_TYPES,
            "allowed_tc_options": ALLOWED_TC_OPTIONS,
            "success_message": _build_user_qr_success_message(request),
            "error_message": request.query_params.get("error"),
            **summary,
        },
    )


@router.get("/dashboard/users/export", tags=["Dashboard"])
def export_user_qr_documents(
    search: str = Query(default=""),
    status: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    document_type: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Export Document Request tracking data using the active table filters."""
    documents = get_dashboard_documents(
        db,
        search=search or None,
        status=status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        document_type=document_type or None,
    )
    csv_content = _build_document_request_export_csv(documents)
    filename = f"trackflow_document_request_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/dashboard/users/verify-access", tags=["Dashboard API"])
def verify_access(
    nik: str = Form(...),
    password: str = Form(...),
):
    """Verify NIK and password for Document Request page."""
    admin_nik = get_admin_nik()
    admin_password = get_admin_password()

    if nik == admin_nik and password == admin_password:
        return JSONResponse({"status": "success", "message": "Access granted"})

    return JSONResponse(
        {"status": "error", "message": "NIK atau Password salah."},
        status_code=401,
    )


@router.get("/dashboard/users/generate-qr", tags=["Dashboard"])
def generate_user_qr_from_dashboard(
    db: Session = Depends(get_db),
):
    generated_user = get_preferred_qr_user(db)
    if generated_user is None:
        return RedirectResponse(
            url="/dashboard/users?error=Belum ada user aktif untuk dibuatkan QR.",
            status_code=303,
        )

    return RedirectResponse(url=f"/generate-user-qr/{generated_user.id}", status_code=303)


@router.get("/dashboard/users/create-submission", tags=["Dashboard"])
def open_user_document_submission(
    db: Session = Depends(get_db),
):
    submission_user = get_preferred_qr_user(db)
    if submission_user is None:
        return RedirectResponse(
            url="/dashboard/users?error=Belum ada user aktif untuk membuat document submission.",
            status_code=303,
        )

    return RedirectResponse(url=f"/submit/user/{submission_user.id}", status_code=303)


@router.post("/dashboard/users/documents/add", tags=["Dashboard"])
def post_add_user_document(
    document_type: str = Form(...),
    invoice_number: str = Form(...),
    qty_price: str = Form(...),
    qty_currency: str = Form(default="IDR"),
    tc: str = Form(...),
    status: str = Form(...),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
):
    cleaned_document_type = document_type.strip()
    cleaned_invoice_number = invoice_number.strip()
    cleaned_qty_price = qty_price.strip()
    cleaned_qty_currency = qty_currency.strip() or "IDR"
    cleaned_tc = tc.strip()
    cleaned_status = status.strip()
    cleaned_notes = notes.strip()

    if cleaned_document_type not in ALLOWED_DOCUMENT_TYPES:
        return RedirectResponse(
            url="/dashboard/users?error=Document type must be Invoice or PAM.",
            status_code=303,
        )

    if cleaned_status not in ALLOWED_DOCUMENT_STATUSES:
        return RedirectResponse(
            url="/dashboard/users?error=Status must be Pending, Approved, or Rejected.",
            status_code=303,
        )

    if cleaned_tc not in ALLOWED_TC_OPTIONS:
        return RedirectResponse(
            url="/dashboard/users?error=TC must be Yes or No.",
            status_code=303,
        )

    if not cleaned_invoice_number or not cleaned_qty_price:
        return RedirectResponse(
            url="/dashboard/users?error=Invoice number and qty/price are required.",
            status_code=303,
        )

    try:
        submitter_id = _get_default_submitter_id(db)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/dashboard/users?error={str(exc)}",
            status_code=303,
        )

    document_data = DocumentSubmissionSchema(
        document_type=cleaned_document_type,
        invoice_number=cleaned_invoice_number,
        qty_price=cleaned_qty_price,
        tc=cleaned_tc,
        status=cleaned_status,
        notes=cleaned_notes or None,
    )

    try:
        document = create_document(
            db=db,
            submitter_id=submitter_id,
            document_data=document_data,
            currency=cleaned_qty_currency,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/dashboard/users?error={str(exc)}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/dashboard/users?added=1&doc={document.doc_number}",
        status_code=303,
    )


@router.post("/dashboard/users/documents/{document_id}/edit", tags=["Dashboard"])
def post_update_user_qr_document(
    document_id: int,
    document_type: str = Form(...),
    invoice_number: str = Form(...),
    qty_price: str = Form(...),
    qty_currency: str = Form(default="IDR"),
    tc: str = Form(default="Yes"),
    status: str = Form(...),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
):
    cleaned_document_type = document_type.strip()
    cleaned_invoice_number = invoice_number.strip()
    cleaned_qty_price = qty_price.strip()
    cleaned_qty_currency = qty_currency.strip() or "IDR"
    cleaned_tc = tc.strip()
    cleaned_status = status.strip()
    cleaned_notes = notes.strip()

    if cleaned_document_type not in ALLOWED_DOCUMENT_TYPES:
        return RedirectResponse(
            url="/dashboard/users?error=Document type must be Invoice or PAM.",
            status_code=303,
        )

    if cleaned_status not in ALLOWED_DOCUMENT_STATUSES:
        return RedirectResponse(
            url="/dashboard/users?error=Status must be Pending, Approved, or Rejected.",
            status_code=303,
        )

    if cleaned_tc not in ALLOWED_TC_OPTIONS:
        return RedirectResponse(
            url="/dashboard/users?error=TC must be Yes or No.",
            status_code=303,
        )

    if not cleaned_invoice_number or not cleaned_qty_price:
        return RedirectResponse(
            url="/dashboard/users?error=Invoice number and qty/price are required.",
            status_code=303,
        )

    try:
        updated_document = update_document_details(
            db=db,
            document_id=document_id,
            document_type=cleaned_document_type,
            invoice_number=cleaned_invoice_number,
            qty_price=cleaned_qty_price,
            tc=cleaned_tc,
            status=cleaned_status,
            notes=cleaned_notes or None,
            currency=cleaned_qty_currency,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/dashboard/users?error={str(exc)}",
            status_code=303,
        )

    if updated_document is None:
        return RedirectResponse(
            url="/dashboard/users?error=Document not found.",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/dashboard/users?updated=1&doc={updated_document.doc_number}",
        status_code=303,
    )


@router.get("/dashboard/users/documents/{document_id}/delete", tags=["Dashboard"])
def delete_user_qr_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    deleted = delete_document(db, document_id)
    if not deleted:
        return RedirectResponse(
            url="/dashboard/users?error=Document not found.",
            status_code=303,
        )

    return RedirectResponse(
        url="/dashboard/users?deleted=1",
        status_code=303,
    )


@router.post("/dashboard/approvers", tags=["Dashboard"])
def post_create_approver(
    request: Request,
    approval_name: str = Form(...),
    department: str = Form(default=""),
    generate_qr: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Create new approver."""
    cleaned_form_data = {
        "approval_name": approval_name.strip(),
        "department": department.strip(),
    }

    if not cleaned_form_data["approval_name"]:
        approvers = get_all_approvers(db)
        summary = get_dashboard_summary(db)
        return templates.TemplateResponse(
            request=request,
            name="dashboard/approver_management.html",
            context={
                "page_title": "Approver Management",
                "active_menu": "approvers",
                "approvers": approvers,
                "form_data": cleaned_form_data,
                "error_message": "Approval name is required.",
                "success_message": None,
                **summary,
            },
            status_code=422,
        )

    try:
        approver = create_approver(
            db=db,
            approval_name=cleaned_form_data["approval_name"],
            department=cleaned_form_data["department"] or None,
        )
    except ValueError as exc:
        approvers = get_all_approvers(db)
        summary = get_dashboard_summary(db)
        return templates.TemplateResponse(
            request=request,
            name="dashboard/approver_management.html",
            context={
                "page_title": "Approver Management",
                "active_menu": "approvers",
                "approvers": approvers,
                "form_data": cleaned_form_data,
                "error_message": str(exc),
                "success_message": None,
                **summary,
            },
            status_code=422,
        )

    if generate_qr:
        return RedirectResponse(url=f"/generate-qr/{approver.slug}", status_code=303)

    return RedirectResponse(
        url=f"/dashboard/approvers?created=1&slug={approver.slug}",
        status_code=303,
    )


@router.get("/api/approvers/{slug}/delete", tags=["Approvers API"])
def delete_approver_endpoint(
    slug: str,
    mode: str = Query(default="approver_only"),
    db: Session = Depends(get_db),
):
    """Delete an approver by slug.

    Query params:
        mode: 'approver_only' (default) keeps documents,
              'with_documents' also deletes all linked documents.
    """
    try:
        delete_approver(
            db=db,
            slug=slug,
            delete_documents=(mode == "with_documents"),
        )
        return RedirectResponse(
            url="/dashboard/approvers?deleted=1",
            status_code=303,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/dashboard/approvers?error={str(exc)}",
            status_code=303,
        )


def _build_approver_success_message(request: Request) -> str | None:
    """Build success message from query parameters."""
    if request.query_params.get("created") == "1":
        slug = request.query_params.get("slug")
        if slug:
            return f"Approver created successfully. Slug: {slug}"
        return "Approver created successfully."

    if request.query_params.get("deleted") == "1":
        return "Approver deleted successfully."

    return None


def _prepare_generated_user_card(
    db: Session,
    qr_user_id: int | None,
):
    if qr_user_id is None:
        return None

    user = get_preferred_qr_user(db, qr_user_id)
    if user is None:
        return None

    user.qr_image_url = f"/qr-image/user/{user.id}"
    user.qr_target_url = "/dashboard/users"
    return user


def _build_user_qr_success_message(request: Request) -> str | None:
    if request.query_params.get("generated") == "1":
        return "QR user berhasil digenerate dan ditampilkan di halaman ini."

    if request.query_params.get("added") == "1":
        document_number = request.query_params.get("doc")
        if document_number:
            return f"Dokumen berhasil ditambahkan. Reference: {document_number}"
        return "Dokumen berhasil ditambahkan."

    if request.query_params.get("updated") == "1":
        document_number = request.query_params.get("doc")
        if document_number:
            return f"Document {document_number} berhasil diupdate."
        return "Document berhasil diupdate."

    if request.query_params.get("deleted") == "1":
        return "Document berhasil dihapus dari operational tracking table."

    return None


def _build_document_request_export_csv(documents) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Time",
            "Current Location",
            "PAM Number",
            "Invoice Number",
            "Document Type",
            "Qty / Price",
            "Currency",
            "TC",
            "Shipment Type",
            "Vessel Name",
            "No BL",
            "No SI",
            "TC Details",
            "Remarks",
            "Attachment",
            "Status",
            "Reference Number",
        ]
    )

    for document in documents:
        created_at = document.created_at_local or document.created_at
        writer.writerow(
            [
                created_at.strftime("%d %b %Y") if created_at else "",
                created_at.strftime("%H:%M") if created_at else "",
                document.approver.approval_name if document.approver else "Belum diserahkan ke approver",
                _csv_value(document.pam_number),
                _csv_value(getattr(document, "invoice_display", document.invoice_number)),
                _csv_value(document.document_type),
                _csv_value(getattr(document, "qty_price_clean", document.qty_price)),
                _csv_value(document.currency or "IDR"),
                _csv_value(document.tc),
                _csv_value(document.tc_type),
                _csv_value(document.vessel_name),
                _csv_value(document.kode_bl),
                _csv_value(", ".join(getattr(document, "no_si_list_parsed", []) or [])),
                _csv_value(getattr(document, "tc_details_display", "")),
                _csv_value(document.notes),
                _csv_value(", ".join(file.original_name for file in document.files)),
                _csv_value(document.status_display),
                _csv_value(document.doc_number),
            ]
        )

    return output.getvalue()


def _csv_value(value) -> str:
    if value is None:
        return ""

    return str(value).replace("\r", " ").replace("\n", " ").strip()
