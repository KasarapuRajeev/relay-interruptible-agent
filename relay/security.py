"""Small security helpers shared by provider and tool error paths."""

from __future__ import annotations

import re


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(api[_ -]?key|authorization|bearer)\b\s*[:=]?\s*[\"']?[^\s,;\"']+"
    ),
)


def sanitize_error(value: object, *, limit: int = 300) -> str:
    """Redact likely credentials and bound externally supplied error text."""

    text = str(value).replace("\r", " ").replace("\n", " ")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:limit]
