from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from app.extensions import db
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrder
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.order_photos.retention import _exclusive_file_lock, cleanup_expired_order_photos
from app.service_orders.status_retention import update_terminal_status_entry_time


@pytest.fixture()
def photo_retention_schema(app):
    tables = [Customer.__table__, Device.__table__, ServiceOrder.__table__, ServiceOrderStatusHistory.__table__, ServiceOrderPhoto.__table__]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _make_order(company_id: int, status: str, entered_at: datetime | None) -> ServiceOrder:
    customer = Customer(company_id=company_id, full_name=f"Retention {uuid4().hex[:8]}")
    db.session.add(customer)
    db.session.flush()
    device = Device(company_id=company_id, customer_id=customer.id, device_type="Printer", manufacturer="Test", model="A")
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(
        company_id=company_id,
        customer_id=customer.id,
        device_id=device.id,
        order_number=f"RET-{uuid4().hex[:12]}",
        status=status,
        priority="NORMAL",
        intake_date=datetime(2026, 1, 1).date(),
        issue_description="Photo retention test",
        terminal_status_entered_at=entered_at,
    )
    db.session.add(order)
    db.session.flush()
    return order


def _attach_photo(order: ServiceOrder, root: Path, *, taken_at: datetime | None = None) -> tuple[ServiceOrderPhoto, Path, Path]:
    file_name = f"{uuid4().hex}.jpg"
    directory = root / "service_orders" / str(order.id) / "photos"
    thumbs = directory / "thumbnails"
    thumbs.mkdir(parents=True, exist_ok=True)
    original = directory / file_name
    thumbnail = thumbs / f"{Path(file_name).stem}_thumb.webp"
    image = Image.new("RGB", (20, 20), (10, 20, 30))
    image.save(original, format="JPEG")
    image.save(thumbnail, format="WEBP")
    row = ServiceOrderPhoto(
        service_order_id=order.id,
        company_id=order.company_id,
        branch_id=order.branch_id,
        photo_type="REPAIR",
        file_name=file_name,
        original_file_name="image.jpg",
        mime_type="image/jpeg",
        file_size=original.stat().st_size,
        width=20,
        height=20,
        taken_at=taken_at,
        sort_order=100,
        is_visible_for_customer=False,
    )
    db.session.add(row)
    db.session.flush()
    return row, original, thumbnail


def test_retention_removes_only_photos_of_orders_terminal_for_60_days(app, company_id, photo_retention_schema, tmp_path):
    now = datetime(2026, 10, 25, 12, 0, 0)
    with app.app_context():
        expired = _make_order(company_id, "ISSUED", now - timedelta(days=61))
        recent = _make_order(company_id, "CLOSED", now - timedelta(days=59))
        active = _make_order(company_id, "IN_REPAIR", now - timedelta(days=90))
        foreign_company = Company(name="Retention Foreign Co", prefix="RFC")
        db.session.add(foreign_company)
        db.session.flush()
        foreign = _make_order(foreign_company.id, "ISSUED", now - timedelta(days=90))
        expired_photo, expired_file, expired_thumb = _attach_photo(expired, tmp_path, taken_at=now - timedelta(days=300))
        recent_photo, recent_file, recent_thumb = _attach_photo(recent, tmp_path, taken_at=now - timedelta(days=400))
        active_photo, active_file, active_thumb = _attach_photo(active, tmp_path, taken_at=now - timedelta(days=500))
        foreign_photo, foreign_file, foreign_thumb = _attach_photo(foreign, tmp_path)
        expired_id, recent_id, active_id, foreign_id = expired_photo.id, recent_photo.id, active_photo.id, foreign_photo.id
        db.session.commit()

        result = cleanup_expired_order_photos(upload_root=tmp_path, now=now)

        assert result == {"lock_acquired": True, "orders_scanned": 2, "photos_deleted": 2, "errors": 0}
        assert not expired_file.exists() and not expired_thumb.exists()
        assert recent_file.exists() and recent_thumb.exists()
        assert active_file.exists() and active_thumb.exists()
        assert not foreign_file.exists() and not foreign_thumb.exists()
        assert db.session.get(ServiceOrderPhoto, expired_id).is_active is False
        assert db.session.get(ServiceOrderPhoto, recent_id).is_active is True
        assert db.session.get(ServiceOrderPhoto, active_id).is_active is True
        assert db.session.get(ServiceOrderPhoto, foreign_id).is_active is False


def test_photo_age_does_not_set_retention_deadline_and_missing_files_are_reconciled(app, company_id, photo_retention_schema, tmp_path):
    now = datetime(2026, 10, 25, 12, 0, 0)
    with app.app_context():
        expired_order = _make_order(company_id, "CANCELLED", now - timedelta(days=61))
        photo, original, thumbnail = _attach_photo(expired_order, tmp_path, taken_at=now - timedelta(days=1))
        missing_order = _make_order(company_id, "CLOSED", now - timedelta(days=70))
        missing_photo, missing_original, missing_thumb = _attach_photo(missing_order, tmp_path)
        missing_original.unlink()
        missing_thumb.unlink()
        ids = photo.id, missing_photo.id
        db.session.commit()

        result = cleanup_expired_order_photos(upload_root=tmp_path, now=now)
        assert result["photos_deleted"] == 2
        assert db.session.get(ServiceOrderPhoto, ids[0]).is_active is False
        assert db.session.get(ServiceOrderPhoto, ids[1]).is_active is False


def test_reopened_order_is_not_selected_for_cleanup(app, company_id, photo_retention_schema, tmp_path):
    now = datetime(2026, 10, 25, 12, 0, 0)
    with app.app_context():
        order = _make_order(company_id, "ISSUED", now - timedelta(days=90))
        photo, original, thumbnail = _attach_photo(order, tmp_path)
        order.status = "IN_REPAIR"
        order.terminal_status_entered_at = None
        db.session.commit()
        result = cleanup_expired_order_photos(upload_root=tmp_path, now=now)
        assert result["orders_scanned"] == 0
        assert photo.is_active is True
        assert original.exists() and thumbnail.exists()


def test_file_lock_skips_second_cleanup_invocation(tmp_path):
    lock = tmp_path / ".cleanup.lock"
    name = f"SerwisPROPhotoRetentionTest{uuid4().hex}"
    with _exclusive_file_lock(lock, lock_name=name) as first:
        assert first is True
        with _exclusive_file_lock(lock, lock_name=name) as second:
            assert second is False


def test_failed_file_unlink_leaves_photo_active_for_retry(app, company_id, photo_retention_schema, tmp_path, monkeypatch):
    now = datetime(2026, 10, 25, 12)
    with app.app_context():
        order = _make_order(company_id, "CANCELLED", now - timedelta(days=61))
        photo, original, thumbnail = _attach_photo(order, tmp_path)
        photo_id = photo.id
        db.session.commit()

    original_unlink = Path.unlink
    failed_once = {"value": False}

    def fail_first_original(path: Path, *args, **kwargs):
        if path == original and not failed_once["value"]:
            failed_once["value"] = True
            raise PermissionError("simulated file lock")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first_original)
    with app.app_context():
        first = cleanup_expired_order_photos(upload_root=tmp_path, now=now)
        persisted = db.session.get(ServiceOrderPhoto, photo_id)
        assert persisted is not None and persisted.is_active is True
    assert first["errors"] == 1
    assert original.exists()
    monkeypatch.setattr(Path, "unlink", original_unlink)

    with app.app_context():
        second = cleanup_expired_order_photos(upload_root=tmp_path, now=now)
        persisted = db.session.get(ServiceOrderPhoto, photo_id)
        assert persisted is not None and persisted.is_active is False
    assert second["photos_deleted"] == 1
    assert not original.exists() and not thumbnail.exists()


def test_cli_cleanup_command_is_registered_and_reports_summary(app, company_id, photo_retention_schema, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    result = app.test_cli_runner().invoke(args=["cleanup-service-order-photos"])
    assert result.exit_code == 0
    assert "Order-photo retention" in result.output or "Service-order photo cleanup:" in result.output


def test_terminal_status_clock_preserves_repeated_terminal_and_resets_after_reopen():
    from types import SimpleNamespace

    order = SimpleNamespace(terminal_status_entered_at=None)
    first = datetime(2026, 1, 1, 10)
    later = datetime(2026, 2, 10, 12)
    update_terminal_status_entry_time(order, old_status="IN_REPAIR", new_status="ISSUED", now=first)
    assert order.terminal_status_entered_at == first
    update_terminal_status_entry_time(order, old_status="ISSUED", new_status="CLOSED", now=later)
    assert order.terminal_status_entered_at == first
    update_terminal_status_entry_time(order, old_status="CLOSED", new_status="IN_REPAIR", now=later)
    assert order.terminal_status_entered_at is None
    update_terminal_status_entry_time(order, old_status="IN_REPAIR", new_status="CANCELLED", now=later)
    assert order.terminal_status_entered_at == later


def test_service_order_update_does_not_reset_terminal_retention_clock(app, company_id, photo_retention_schema, monkeypatch):
    from app.service_orders.repository import ServiceOrderRepository
    from app.service_orders.service import ServiceOrderService

    service = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer = Customer(company_id=company_id, full_name="Retention transition customer")
        db.session.add(customer)
        db.session.flush()
        device = Device(company_id=company_id, customer_id=customer.id)
        db.session.add(device)
        db.session.flush()
        order = ServiceOrder(
            company_id=company_id, customer_id=customer.id, device_id=device.id,
            order_number="RET-UPDATE-1", status="IN_REPAIR", priority="NORMAL",
            intake_date=datetime(2026, 1, 1).date(), issue_description="Status transitions",
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id

        first_time = datetime(2026, 1, 1, 8)
        later_time = datetime(2026, 3, 15, 9)
        monkeypatch.setattr("app.service_orders.status_retention.datetime", type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: first_time)}))
        service.update_service_order(order_id, {
            "customer_id": customer.id, "device_id": device.id, "order_number": order.order_number,
            "status": "ISSUED", "priority": "NORMAL", "intake_date": order.intake_date,
            "issue_description": order.issue_description,
        }, company_id=company_id, branch_id=None)
        first = db.session.get(ServiceOrder, order_id).terminal_status_entered_at
        assert first == first_time

        monkeypatch.setattr("app.service_orders.status_retention.datetime", type("FakeDateTime", (), {"now": staticmethod(lambda tz=None: later_time)}))
        service.update_service_order(order_id, {
            "customer_id": customer.id, "device_id": device.id, "order_number": order.order_number,
            "status": "ISSUED", "priority": "NORMAL", "intake_date": order.intake_date,
            "issue_description": order.issue_description,
        }, company_id=company_id, branch_id=None)
        assert db.session.get(ServiceOrder, order_id).terminal_status_entered_at == first

