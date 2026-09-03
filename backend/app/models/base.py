"""Shared model helpers (schema.md section 4).

Primary keys are TEXT UUIDv4, generated application-side. Timestamps are TEXT
ISO-8601 UTC with a ``Z`` suffix so lexicographic order equals chronological
order (schema.md section 2).
"""
from datetime import datetime, timezone
from uuid import uuid4


def new_id() -> str:
    """Return a fresh UUIDv4 as a string, for use as a primary key."""
    return str(uuid4())


def utcnow() -> str:
    """Return the current UTC time as ISO-8601 with a trailing ``Z``."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
