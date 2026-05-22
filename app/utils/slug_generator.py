"""Slug generation helpers."""

import re


def generate_slug(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9\s-]", "", normalized)
    normalized = re.sub(r"[\s_-]+", "-", normalized)
    normalized = re.sub(r"^-+|-+$", "", normalized)
    return normalized
