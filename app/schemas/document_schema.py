"""Document submission schemas."""

from pydantic import BaseModel, Field


class DocumentSubmissionSchema(BaseModel):
    document_type: str = Field(..., min_length=1, max_length=50)
    invoice_number: str = Field(..., min_length=1, max_length=100)
    qty_price: str = Field(..., min_length=1, max_length=255)
    status: str = Field(..., min_length=1, max_length=100)
    notes: str | None = Field(default=None)
