"""Dashboard-focused operational monitoring services."""

from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.approver import Approver
from app.models.document import Document
from app.services.status_service import attach_display_status


def get_dashboard_documents(
    db: Session,
    search: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    document_type: str | None = None,
) -> list[Document]:
    query = (
        db.query(Document)
        .options(joinedload(Document.approver), joinedload(Document.files))
        .outerjoin(Approver, Document.approver_id == Approver.id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )

    if search:
        like_query = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Document.invoice_number.ilike(like_query),
                Document.document_type.ilike(like_query),
                Document.qty_price.ilike(like_query),
                Document.notes.ilike(like_query),
                Approver.approval_name.ilike(like_query),
            )
        )

    if status:
        status_mapping = {
            "Pending": ("SUBMITTED", "PENDING"),
            "Approved": ("APPROVED", "COMPLETED"),
            "Rejected": ("REJECTED",),
        }
        mapped_statuses = status_mapping.get(status, (status,))
        query = query.filter(Document.status.in_(mapped_statuses))

    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Document.created_at >= from_date)
        except ValueError:
            pass

    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            query = query.filter(Document.created_at <= to_date)
        except ValueError:
            pass

    if document_type:
        query = query.filter(Document.document_type == document_type)

    documents = query.all()
    return [attach_display_status(document) for document in documents]


def get_dashboard_summary(db: Session) -> dict[str, int]:
    return {
        "document_count": db.query(func.count(Document.id)).scalar() or 0,
        "approver_count": db.query(func.count(Approver.id)).scalar() or 0,
        "approved_count": (
            db.query(func.count(Document.id))
            .filter(Document.status.in_(("APPROVED", "COMPLETED")))
            .scalar()
            or 0
        ),
        "pending_count": (
            db.query(func.count(Document.id))
            .filter(Document.status.in_(("SUBMITTED", "PENDING")))
            .scalar()
            or 0
        ),
        "rejected_count": (
            db.query(func.count(Document.id))
            .filter(Document.status == "REJECTED")
            .scalar()
            or 0
        ),
        "generated_qr_count": (
            db.query(func.count(Approver.id))
            .filter(Approver.qr_code_path.is_not(None))
            .scalar()
            or 0
        ),
    }
