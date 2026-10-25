from __future__ import annotations

import ctypes
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import select

from app.extensions import db
from app.models.service_order import PHOTO_RETENTION_TERMINAL_STATUSES, ServiceOrder
from app.models.service_order_photo import ServiceOrderPhoto

from .exceptions import ServiceOrderPhotoNotFoundError
from .service import ServiceOrderPhotoService

logger = logging.getLogger(__name__)
_active_lock_names: set[str] = set()
_active_lock_guard = threading.Lock()


@contextmanager
def _exclusive_file_lock(path: Path, *, lock_name: str = "SerwisPROOrderPhotoRetention") -> Iterator[bool]:
    """Cross-process local host lock for scheduled invocations on Windows/POSIX."""
    if os.name == "nt":
        with _active_lock_guard:
            if lock_name in _active_lock_names:
                yield False
                return
            _active_lock_names.add(lock_name)
        kernel = ctypes.windll.kernel32
        mutex = kernel.CreateMutexW(None, False, f"Local\\{lock_name}")
        if not mutex:
            with _active_lock_guard:
                _active_lock_names.discard(lock_name)
            yield False
            return
        wait_result = kernel.WaitForSingleObject(mutex, 0)
        locked = wait_result in (0, 0x80)  # WAIT_OBJECT_0 / WAIT_ABANDONED
        try:
            yield locked
        finally:
            if locked:
                kernel.ReleaseMutex(mutex)
            kernel.CloseHandle(mutex)
            with _active_lock_guard:
                _active_lock_names.discard(lock_name)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        handle.seek(0)
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            locked = False
        yield locked
    finally:
        if locked:
            handle.seek(0)
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def cleanup_expired_order_photos(
    *,
    upload_root: Path,
    now: datetime | None = None,
    retention_days: int = 60,
    photo_service: ServiceOrderPhotoService | None = None,
) -> dict[str, int | bool]:
    """Remove photos only for active orders currently in an aged terminal status.

    Files are unlinked before metadata is soft-deactivated. If a file or DB operation
    fails, the metadata stays active so a later invocation can safely retry. Missing
    files count as already removed and are reconciled on the same run.
    """
    current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
    cutoff = current_time - timedelta(days=retention_days)
    service = photo_service or ServiceOrderPhotoService()
    lock_path = upload_root.resolve() / ".service-order-photo-retention.lock"
    totals: dict[str, int | bool] = {"lock_acquired": False, "orders_scanned": 0, "photos_deleted": 0, "errors": 0}

    with _exclusive_file_lock(lock_path) as acquired:
        if not acquired:
            logger.info("Order-photo retention cleanup skipped: another process holds the lock.")
            return totals
        totals["lock_acquired"] = True
        order_ids = list(
            db.session.scalars(
                select(ServiceOrder.id)
                .where(ServiceOrder.is_active.is_(True))
                .where(ServiceOrder.status.in_(PHOTO_RETENTION_TERMINAL_STATUSES))
                .where(ServiceOrder.terminal_status_entered_at.is_not(None))
                .where(ServiceOrder.terminal_status_entered_at <= cutoff)
                .order_by(ServiceOrder.id.asc())
            ).all()
        )

        for order_id in order_ids:
            try:
                order = db.session.scalar(
                    select(ServiceOrder)
                    .where(ServiceOrder.id == order_id)
                    .where(ServiceOrder.is_active.is_(True))
                    .where(ServiceOrder.status.in_(PHOTO_RETENTION_TERMINAL_STATUSES))
                    .where(ServiceOrder.terminal_status_entered_at.is_not(None))
                    .where(ServiceOrder.terminal_status_entered_at <= cutoff)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if order is None:
                    db.session.rollback()
                    continue
                totals["orders_scanned"] = int(totals["orders_scanned"]) + 1
                order_company_id = order.company_id
                order_branch_id = order.branch_id
                photo_query = (
                    select(ServiceOrderPhoto)
                    .where(ServiceOrderPhoto.service_order_id == order.id)
                    .where(ServiceOrderPhoto.company_id == order_company_id)
                    .where(ServiceOrderPhoto.is_active.is_(True))
                )
                photo_query = photo_query.where(
                    ServiceOrderPhoto.branch_id.is_(None)
                    if order_branch_id is None
                    else ServiceOrderPhoto.branch_id == order_branch_id
                )
                photos = list(db.session.scalars(photo_query.order_by(ServiceOrderPhoto.id.asc())).all())
                removed_rows = []
                for photo in photos:
                    try:
                        original, thumbnail = service.photo_file_paths(
                            upload_root=upload_root,
                            order_id=order.id,
                            file_name=photo.file_name,
                        )
                        original.unlink(missing_ok=True)
                        thumbnail.unlink(missing_ok=True)
                    except (OSError, ServiceOrderPhotoNotFoundError, ValueError):
                        logger.exception(
                            "Photo-retention could not remove photo_id=%s order_id=%s; it will be retried.",
                            photo.id,
                            order.id,
                        )
                        totals["errors"] = int(totals["errors"]) + 1
                        continue

                    photo.is_active = False
                    photo.deleted_at = current_time
                    db.session.add(photo)
                    removed_rows.append(photo)
                try:
                    db.session.commit()
                    totals["photos_deleted"] = int(totals["photos_deleted"]) + len(removed_rows)
                except Exception:
                    db.session.rollback()
                    logger.exception(
                        "Photo-retention metadata commit failed order_id=%s; next run will reconcile removed files.",
                        order_id,
                    )
                    totals["errors"] = int(totals["errors"]) + 1
            except Exception:
                db.session.rollback()
                logger.exception("Photo-retention failed while processing order_id=%s.", order_id)
                totals["errors"] = int(totals["errors"]) + 1

    logger.info(
        "Order-photo retention finished: scanned_orders=%s deleted_photos=%s errors=%s",
        totals["orders_scanned"], totals["photos_deleted"], totals["errors"],
    )
    return totals
