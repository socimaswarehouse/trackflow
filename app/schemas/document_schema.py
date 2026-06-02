"""Document submission schemas."""

from pydantic import BaseModel, Field


class DocumentSubmissionSchema(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=50)
    invoice_number: str = Field(..., min_length=1, max_length=255)
    qty_price: str = Field(..., min_length=1, max_length=255)
    tc: str = Field(..., min_length=1, max_length=3)
    status: str = Field(..., min_length=1, max_length=100)
    notes: str | None = Field(default=None)
    pam_number: str | None = Field(default=None, max_length=100)
    invoice_numbers_json: str | None = Field(default=None)
    tc_type: str | None = Field(default=None, max_length=10)
    tc_details: str | None = Field(default=None)
    kode_bl: str | None = Field(default=None, max_length=255)
    no_si: str | None = Field(default=None)
    vessel_name: str | None = Field(default=None, max_length=255)
