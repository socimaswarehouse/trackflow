"""User ORM model."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    submitted_documents = relationship(
        "Document",
        back_populates="submitter",
        foreign_keys="Document.submitter_id",
    )
    approver_profile = relationship(
        "Approver",
        back_populates="user",
        uselist=False,
    )
    status_updates = relationship(
        "StatusLog",
        back_populates="updater",
        foreign_keys="StatusLog.changed_by",
    )
