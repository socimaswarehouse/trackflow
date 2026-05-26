"""QR code generation helpers for approver access points."""

from io import BytesIO
from pathlib import Path

import qrcode

QR_CODES_DIR = Path(__file__).resolve().parents[1] / "static" / "qrcodes"


def generate_qr_code(slug: str, target_url: str) -> str:
    """Generate QR code for approver submission URL.
    
    Args:
        slug: Approver slug for filename
        target_url: Full URL to encode in QR code
        
    Returns:
        Relative path to generated QR image
    """
    if not slug or not target_url:
        raise ValueError("Slug and target_url are required")
    
    QR_CODES_DIR.mkdir(parents=True, exist_ok=True)

    file_name = f"{slug}.png"
    absolute_path = QR_CODES_DIR / file_name

    qr_image = qrcode.make(target_url)
    qr_image.save(absolute_path)

    return (Path("static") / "qrcodes" / file_name).as_posix()


def generate_qr_png_bytes(target_url: str) -> bytes:
    """Generate QR code PNG bytes for inline/dynamic rendering."""
    if not target_url:
        raise ValueError("target_url is required")

    qr_image = qrcode.make(target_url)
    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")
    return buffer.getvalue()
