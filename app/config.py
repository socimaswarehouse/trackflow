"""Application configuration for TRACKFLOW."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def get_base_url() -> str:
    """Get the base URL for QR code generation and submission links."""
    return os.getenv("BASE_URL", "http://127.0.0.1:8000")
