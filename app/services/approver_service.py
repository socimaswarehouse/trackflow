"""Approver service queries."""

from datetime import datetime
from secrets import token_hex

from sqlalchemy.orm import Session

from app.config import get_base_url
from app.models.approver import Approver
from app.models.document import Document
from app.models.user import User
from app.utils.slug_generator import generate_slug


def get_approver_by_slug(db: Session, slug: str) -> Approver | None:
    return db.query(Approver).filter(Approver.slug == slug).first()


def get_all_approvers(db: Session) -> list[Approver]:
    return (
        db.query(Approver)
        .order_by(Approver.created_at.desc(), Approver.id.desc())
        .all()
    )


def create_approver(
    db: Session,
    approval_name: str,
    department: str | None = None,
) -> Approver:
    base_url = get_base_url()
    slug = _build_unique_slug(db, approval_name)
    timestamp = datetime.utcnow()
    email = f"{slug}@trackflow.local"

    user = User(
        full_name=approval_name,
        email=email,
        password_hash=token_hex(32),
        role="approver",
        department=department,
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(user)
    db.flush()

    approver = Approver(
        user_id=user.id,
        approval_name=approval_name,
        slug=slug,
        department=department,
        email=email,
        qr_url=f"{base_url}/submit/{slug}",
        is_active=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(approver)
    db.commit()
    db.refresh(approver)
    return approver


def get_document_count_for_approver(db: Session, approver_id: int) -> int:
    """Return the number of documents assigned to an approver."""
    return db.query(Document).filter(Document.approver_id == approver_id).count()


def delete_approver(db: Session, slug: str, delete_documents: bool = False) -> None:
    """Delete an approver by slug.

    Args:
        db: Database session.
        slug: Approver slug.
        delete_documents: If True, also delete all assigned documents
            and their related files/logs. If False, unlink documents
            (set approver_id to NULL) so they remain in the system.
    """
    approver = get_approver_by_slug(db, slug)
    if not approver:
        raise ValueError(f"Approver with slug '{slug}' not found.")

    if delete_documents:
        # Delete status_logs and document_files for each document first
        docs = (
            db.query(Document)
            .filter(Document.approver_id == approver.id)
            .all()
        )
        for doc in docs:
            for log in doc.status_logs:
                db.delete(log)
            for f in doc.files:
                db.delete(f)
            db.delete(doc)
    else:
        # Unlink documents — they remain but without approver
        db.query(Document).filter(
            Document.approver_id == approver.id
        ).update({"approver_id": None})

    if approver.user_id:
        user = db.query(User).filter(User.id == approver.user_id).first()
        if user:
            db.delete(user)

    db.delete(approver)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ValueError("Gagal menghapus approver karena kendala database.")


def update_approver_qr_path(
    db: Session,
    approver: Approver,
    qr_code_path: str,
) -> Approver:
    base_url = get_base_url()
    approver.qr_code_path = qr_code_path
    approver.qr_url = f"{base_url}/submit/{approver.slug}"
    db.add(approver)
    db.commit()
    db.refresh(approver)
    return approver


def _build_unique_slug(db: Session, approval_name: str) -> str:
    base_slug = generate_slug(approval_name)
    if not base_slug:
        raise ValueError("Approval name produced an invalid slug.")

    slug = base_slug
    counter = 2

    while db.query(Approver).filter(Approver.slug == slug).first() is not None:
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug
