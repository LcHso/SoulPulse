"""Shared utility functions."""

from datetime import datetime, timezone


def to_utc_iso(dt: datetime | None) -> str:
    """Convert a datetime to a UTC ISO-8601 string with 'Z' suffix.

    SQLite returns naive datetimes (no tzinfo) even when stored as UTC.
    This ensures clients always receive timezone-aware timestamps.
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
