"""ORM model exports for TRACKFLOW."""

from app.models.approver import Approver
from app.models.document import Document
from app.models.document_file import DocumentFile
from app.models.status_log import StatusLog
from app.models.user import User

__all__ = [
    "Approver",
    "Document",
    "DocumentFile",
    "StatusLog",
    "User",
]


def load_models() -> tuple[type[Approver], type[Document], type[DocumentFile], type[StatusLog], type[User]]:
    """Ensure all ORM models are imported and registered with SQLAlchemy."""
    return Approver, Document, DocumentFile, StatusLog, User
