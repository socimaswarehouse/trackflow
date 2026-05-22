"""Application configuration for TRACKFLOW."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def get_base_url() -> str:
    base_url = os.getenv("BASE_URL")

    if not base_url:
        raise ValueError("BASE_URL is not set in environment variables")

    return base_url