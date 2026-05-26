"""Dashboard and approver management routes."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.approver_service import (
    create_approver,
    delete_approver,
    get_all_approvers,
    get_document_count_for_approver,
)
from app.services.dashboard_service import get_dashboard_documents, get_dashboard_summary
from app.services.statistics_service import get_approval_statistics, get_chart_data_for_approvers
from app.services.status_service import ALLOWED_DOCUMENT_STATUSES
from app.services.user_service import get_all_employee_users

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
    db: Session = Depends(get_db),
):
    """User QR management page."""
    users = get_all_employee_users(db)
    summary = get_dashboard_summary(db)

    return templates.TemplateResponse(
        request=request,
        name="dashboard/user_qr_management.html",
        context={
            "page_title": "QR Users",
            "active_menu": "users",
            "users": users,
            "employee_count": len(users),
            **summary,
        },
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
