"""Status log ORM model."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.session import Base


class StatusLog(Base):
    __tablename__ = "status_logs"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    old_status = Column(String(100), nullable=True)
    new_status = Column(String(100), nullable=False)
    remarks = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False)

    document = relationship("Document", back_populates="status_logs")
    updater = relationship(
        "User",
        back_populates="status_updates",
        foreign_keys=[changed_by],
    )
