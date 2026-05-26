"""Document service operations."""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.approver import Approver
from app.models.document import Document
from app.models.document_file import DocumentFile
from app.models.user import User
from app.schemas.document_schema import DocumentSubmissionSchema
from app.services.status_service import attach_display_status, to_database_status

TERMINAL_DOCUMENT_STATUSES = {"APPROVED", "COMPLETED", "REJECTED"}


def create_document(
    db: Session,
    submitter_id: int,
    document_data: DocumentSubmissionSchema,
    approver_id: int | None = None,
) -> Document:
    existing_document = find_open_document_by_invoice(
        db,
        invoice_number=document_data.invoice_number,
    )
    if existing_document is not None:
        raise ValueError(_build_locked_invoice_message(existing_document))

    timestamp = datetime.utcnow()
    database_status = to_database_status(document_data.status)
    if database_status is None:
        raise ValueError("Invalid document status.")

    document = Document(
        doc_number=_generate_doc_number(),
        document_type=document_data.document_type,
        invoice_number=document_data.invoice_number,
        title=f"{document_data.document_type} Tracking",
        submitter_id=submitter_id,
        approver_id=approver_id,
        status=database_status,
        qty_price=document_data.qty_price,
        notes=document_data.notes,
        submitted_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )

    db.add(document)
    db.flush()
    db.commit()
    db.refresh(document)
    return attach_display_status(document)


def find_open_document_by_invoice(
    db: Session,
    invoice_number: str,
) -> Document | None:
    normalized_invoice_number = invoice_number.strip()
    if not normalized_invoice_number:
        return None

    document = (
        db.query(Document)
        .filter(Document.invoice_number == normalized_invoice_number)
        .filter(~Document.status.in_(TERMINAL_DOCUMENT_STATUSES))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .first()
    )
    if document is None:
        return None

    return attach_display_status(document)


def assign_document_to_approver(
    db: Session,
    document: Document,
    approver: Approver,
) -> Document:
    current_status = (document.status or "").upper()

    if document.approver_id and document.approver_id != approver.id:
        current_approver_name = (
            document.approver.approval_name
            if document.approver is not None
            else "approver lain"
        )
        if current_status not in TERMINAL_DOCUMENT_STATUSES:
            raise ValueError(
                "Dokumen invoice "
                f"{document.invoice_number} masih berada di {current_approver_name} "
                "dan belum approved."
            )

    timestamp = datetime.utcnow()
    document.approver_id = approver.id
    document.updated_at = timestamp

    db.add(document)
    db.commit()
    db.refresh(document)
    return attach_display_status(document)


def update_document_details(
    db: Session,
    document_id: int,
    document_type: str,
    invoice_number: str,
    qty_price: str,
    status: str,
    notes: str | None = None,
) -> Document | None:
    document = (
        db.query(Document)
        .options(joinedload(Document.approver))
        .filter(Document.id == document_id)
        .first()
    )
    if document is None:
        return None

    normalized_invoice_number = invoice_number.strip()
    conflict_document = find_open_document_by_invoice(
        db,
        invoice_number=normalized_invoice_number,
    )
    if conflict_document is not None and conflict_document.id != document.id:
        raise ValueError(_build_locked_invoice_message(conflict_document))

    database_status = to_database_status(status)
    if database_status is None:
        raise ValueError("Invalid document status.")

    document.document_type = document_type.strip()
    document.title = f"{document.document_type} Tracking"
    document.invoice_number = normalized_invoice_number
    document.qty_price = qty_price.strip()
    document.status = database_status
    document.notes = notes.strip() if notes else None
    document.updated_at = datetime.utcnow()

    db.add(document)
    db.commit()
    db.refresh(document)
    return attach_display_status(document)


def delete_document(db: Session, document_id: int) -> bool:
    document = (
        db.query(Document)
        .options(selectinload(Document.files), selectinload(Document.status_logs))
        .filter(Document.id == document_id)
        .first()
    )
    if document is None:
        return False

    for file in document.files:
        absolute_path = Path(__file__).resolve().parents[1] / file.file_path
        try:
            absolute_path.unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(file)

    for log in document.status_logs:
        db.delete(log)

    db.delete(document)
    db.commit()
    return True


def attach_file_to_document(
    db: Session,
    document_id: int,
    uploaded_by: int,
    original_name: str,
    stored_name: str,
    file_path: str,
    content_type: str,
    file_size: int,
) -> DocumentFile:
    """Attach an uploaded file to a document record."""
    extension = Path(original_name).suffix.lower().lstrip(".")
    file_type = "image" if content_type.startswith("image/") else "document"

    doc_file = DocumentFile(
        document_id=document_id,
        uploaded_by=uploaded_by,
        original_name=original_name,
        stored_name=stored_name,
        file_path=file_path,
        file_type=file_type,
        mime_type=content_type,
        file_size=file_size,
        file_extension=extension or None,
        is_primary=True,
        created_at=datetime.utcnow(),
    )

    db.add(doc_file)
    db.commit()
    db.refresh(doc_file)
    return doc_file


def _get_default_submitter_id(db: Session) -> int:
    user = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.id.asc())
        .first()
    )
    if user is None:
        raise ValueError("No active user available for document submission")

    return user.id


def _generate_doc_number() -> str:
    return f"DOC-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def _build_locked_invoice_message(document: Document) -> str:
    if document.approver is not None:
        return (
            f"Invoice {document.invoice_number} masih berada di "
            f"{document.approver.approval_name} dan belum approved."
        )

    return (
        f"Invoice {document.invoice_number} sudah pernah disubmit dan masih "
        "menunggu scan QR approver."
    )
