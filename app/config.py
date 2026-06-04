"""Application configuration for TRACKFLOW."""

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def get_base_url() -> str:
    base_url = os.getenv("BASE_URL")

    if not base_url:
        raise ValueError("BASE_URL is not set in environment variables")

    return _normalize_base_url(base_url)


def get_public_base_url(request: Any | None = None) -> str:
    """Resolve the public base URL, preferring the current request host."""
    if request is not None:
        forwarded_host = _first_header_value(request.headers.get("x-forwarded-host"))
        forwarded_proto = _first_header_value(request.headers.get("x-forwarded-proto"))
        host = forwarded_host or request.headers.get("host")

        if host:
            scheme = forwarded_proto or request.url.scheme
            return _normalize_base_url(f"{scheme}://{host}")

    return get_base_url()


def get_admin_nik() -> str:
    return os.getenv("ADMIN_NIK", "1234567890")


def get_admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", "admin123")


def _first_header_value(value: str | None) -> str | None:
    if not value:
        return None

    return value.split(",", 1)[0].strip() or None


def _normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")
