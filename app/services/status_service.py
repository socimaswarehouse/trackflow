"""Document tracking and status workflow services."""

from datetime import datetime

from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.document import Document
from app.models.status_log import StatusLog
from app.models.user import User

ALLOWED_DOCUMENT_STATUSES = ("Pending", "Approved", "Rejected")

STATUS_DISPLAY_TO_DB = {
    "Pending": "PENDING",
    "Approved": "APPROVED",
    "Rejected": "REJECTED",
}

STATUS_DB_TO_DISPLAY = {
    "SUBMITTED": "Pending",
    "PENDING": "Pending",
    "APPROVED": "Approved",
    "COMPLETED": "Approved",
    "REJECTED": "Rejected",
}


def get_all_documents(db: Session) -> list[Document]:
    documents = (
        db.query(Document)
        .options(joinedload(Document.approver))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .all()
    )
    return [attach_display_status(document) for document in documents]


def get_document_by_id(db: Session, document_id: int) -> Document | None:
    document = (
        db.query(Document)
        .options(
            joinedload(Document.approver),
            selectinload(Document.files),
            selectinload(Document.status_logs).joinedload(StatusLog.updater),
        )
        .filter(Document.id == document_id)
        .first()
    )

    if document is None:
        return None

    document.status_logs.sort(key=lambda item: item.created_at, reverse=True)
    return attach_display_status(document)


def update_document_status(
    db: Session,
    document_id: int,
    new_status: str,
    notes: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Document | None:
    database_status = to_database_status(new_status)
    if database_status is None:
        raise ValueError("Invalid document status.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        return None

    actor_id = _get_default_actor_id(db)
    timestamp = datetime.utcnow()
    old_status = document.status

    document.status = database_status
    document.updated_at = timestamp

    status_log = StatusLog(
        document_id=document.id,
        changed_by=actor_id,
        old_status=old_status,
        new_status=database_status,
        remarks=notes,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=timestamp,
    )

    db.add(status_log)
    db.commit()
    db.refresh(document)
    return attach_display_status(document)


def to_database_status(status: str | None) -> str | None:
    if not status:
        return None

    cleaned_status = status.strip()
    if cleaned_status in STATUS_DISPLAY_TO_DB:
        return STATUS_DISPLAY_TO_DB[cleaned_status]

    uppercase_status = cleaned_status.upper()
    if uppercase_status in STATUS_DB_TO_DISPLAY:
        return uppercase_status

    return None


def to_display_status(status: str | None) -> str:
    if not status:
        return "-"

    return STATUS_DB_TO_DISPLAY.get(status.strip().upper(), status.strip().title())


def attach_display_status(document: Document) -> Document:
    document.status_display = to_display_status(document.status)
    return document


def _get_default_actor_id(db: Session) -> int:
    user = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.id.asc())
        .first()
    )
    if user is None:
        raise ValueError("No active user available for status update.")

    return user.id
