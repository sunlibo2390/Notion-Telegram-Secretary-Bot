from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))


def to_beijing(value: datetime) -> datetime:
    """Normalize any datetime to Beijing timezone (UTC+8)."""
    if value.tzinfo is None:
        # Treat naive timestamps as already in local Beijing time.
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def format_beijing(value: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return to_beijing(value).strftime(fmt)


def beijing_now() -> datetime:
    return datetime.now(tz=BEIJING_TZ)
