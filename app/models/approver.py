"""Approver ORM model."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.session import Base


class Approver(Base):
    __tablename__ = "approvers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    slug = Column(String(255), nullable=False)
    qr_code_path = Column(String(255), nullable=True)
    approval_name = Column(String(255), nullable=False)
    title = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    email = Column(String(180), nullable=True)
    phone = Column(String(30), nullable=True)
    qr_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="approver_profile")
    assigned_documents = relationship(
        "Document",
        back_populates="approver",
        foreign_keys="Document.approver_id",
    )
