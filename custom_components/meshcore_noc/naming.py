"""Managed repeater naming helpers."""

from __future__ import annotations

import re

_MESHCORE_PREFIX = re.compile(
    r"^\s*meshcore(?:\s+(?:repeater|client))?\s*:?\s*",
    re.IGNORECASE,
)
_TRAILING_SHORT_ID = re.compile(r"\s*\([0-9a-f]{6}\)\s*$", re.IGNORECASE)


def managed_device_name(display_name: str, stable_id: str) -> str:
    """Return a normalized friendly name without changing stable identity."""
    normalized = _MESHCORE_PREFIX.sub("", display_name, count=1)
    normalized = _TRAILING_SHORT_ID.sub("", normalized, count=1)
    normalized = " ".join(normalized.split())
    return normalized or stable_id
