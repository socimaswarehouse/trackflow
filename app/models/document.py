"""Document ORM model."""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.session import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    doc_number = Column(String(50), nullable=False)
    document_type = Column(String(50), nullable=False, default="Invoice")
    invoice_number = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    submitter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("approvers.id"), nullable=True)
    status = Column(String(100), nullable=False)
    qty_price = Column(String(255), nullable=True)
    tc = Column(String(3), nullable=False, default="No")
    pam_number = Column(String(100), nullable=True)
    invoice_numbers_json = Column(Text, nullable=True)
    tc_type = Column(String(10), nullable=True)
    tc_details = Column(Text, nullable=True)
    kode_bl = Column(String(255), nullable=True)
    no_si = Column(Text, nullable=True)
    vessel_name = Column(String(255), nullable=True)
    amount = Column(Numeric(20, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    notes = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    priority = Column(String(50), nullable=False, default="NORMAL")
    due_date = Column(Date, nullable=True)
    submitted_at = Column(DateTime, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    submitter = relationship(
        "User",
        back_populates="submitted_documents",
        foreign_keys=[submitter_id],
    )
    approver = relationship(
        "Approver",
        back_populates="assigned_documents",
        foreign_keys=[approver_id],
    )
    files = relationship("DocumentFile", back_populates="document")
    status_logs = relationship("StatusLog", back_populates="document")
