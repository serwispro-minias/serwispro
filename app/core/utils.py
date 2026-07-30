"""Shared utility helpers for SerwisPRO core."""

from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    """Normalize text for consistent security processing."""
    return re.sub(r"\s+", " ", value.strip()).lower()
