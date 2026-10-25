from __future__ import annotations

from datetime import datetime, timezone

from app.models.service_order import PHOTO_RETENTION_TERMINAL_STATUSES, ServiceOrder


def update_terminal_status_entry_time(
    order: ServiceOrder,
    *,
    old_status: str | None,
    new_status: str,
    now: datetime | None = None,
) -> None:
    """Maintain the UTC-naive time at which the current terminal period began."""
    old_is_terminal = old_status in PHOTO_RETENTION_TERMINAL_STATUSES
    new_is_terminal = new_status in PHOTO_RETENTION_TERMINAL_STATUSES
    if not new_is_terminal:
        order.terminal_status_entered_at = None
    elif not old_is_terminal:
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is not None:
            current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
        order.terminal_status_entered_at = current_time
