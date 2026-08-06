from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from app.extensions import db
from app.models.branch import Branch
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrder
from app.models.service_order_photo import ServiceOrderPhoto
from app.order_photos import service as photo_service_module
from app.order_photos.exceptions import ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError, ServiceOrderPhotoValidationError
from app.order_photos.service import ServiceOrderPhotoService


@pytest.fixture()
def order_photos_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderPhoto.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceOrderPhoto.__table__,
                ServiceOrder.__table__,
                Device.__table__,
            ],
        )


def _image_bytes(*, fmt: str = "JPEG", size: tuple[int, int] = (64, 64), color: tuple[int, int, int] = (20, 80, 140)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size=size, color=color).save(out, format=fmt)
    return out.getvalue()


def _create_order(company_id: int, *, branch_id: int | None = None) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Foto Klient",
        email="foto@example.com",
        phone="500100200",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="HP",
        model="M254",
        serial_number=f"SN-PHOTO-{customer.id}",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number=f"SO-PHOTO-{customer.id}",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Problem z wydrukiem",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)
    db.session.commit()
    return int(order.id)


def _upload_file_payload(filename: str = "photo.jpg", content: bytes | None = None):
    return (io.BytesIO(content if content is not None else _image_bytes()), filename)


def test_upload_persists_metadata_and_thumbnail(auth_client, app, company_id, order_photos_schema, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    with app.app_context():
        order_id = _create_order(company_id)

    response = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={
            "photo_type": "RECEPTION",
            "title": "Przyjecie",
            "description": "Stan podczas przyjecia",
            "sort_order": "120",
            "is_visible_for_customer": "y",
            "files": [_upload_file_payload("intake.jpg")],
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        rows = db.session.query(ServiceOrderPhoto).filter_by(service_order_id=order_id).all()
        assert len(rows) == 1
        row = rows[0]

        assert row.company_id == company_id
        assert row.photo_type == "RECEPTION"
        assert row.title == "Przyjecie"
        assert row.description == "Stan podczas przyjecia"
        assert row.mime_type in {"image/jpeg", "image/png", "image/webp"}
        assert row.file_size > 0
        assert row.width > 0
        assert row.height > 0
        assert row.is_visible_for_customer is True

        service = ServiceOrderPhotoService()
        original_path, thumb_path = service.photo_file_paths(upload_root=Path(tmp_path), order_id=order_id, file_name=row.file_name)
        assert original_path.exists()
        assert thumb_path.exists()
        assert thumb_path.suffix.lower() == ".webp"

    thumb_response = auth_client.get(f"/order-photos/{row.id}/thumbnail")
    assert thumb_response.status_code == 200


def test_delete_removes_files_and_soft_deletes(auth_client, app, company_id, order_photos_schema, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    with app.app_context():
        order_id = _create_order(company_id)

    upload_response = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={
            "photo_type": "REPAIR",
            "files": [_upload_file_payload("repair.jpg")],
        },
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 302

    with app.app_context():
        row = db.session.query(ServiceOrderPhoto).filter_by(service_order_id=order_id, is_active=True).one()
        service = ServiceOrderPhotoService()
        original_path, thumb_path = service.photo_file_paths(upload_root=Path(tmp_path), order_id=order_id, file_name=row.file_name)
        assert original_path.exists()
        assert thumb_path.exists()
        photo_id = int(row.id)

    delete_response = auth_client.post(f"/order-photos/{photo_id}/delete", data={"submit": "1"}, follow_redirects=False)
    assert delete_response.status_code == 302

    with app.app_context():
        row = db.session.get(ServiceOrderPhoto, photo_id)
        assert row is not None
        assert row.is_active is False
        assert row.deleted_at is not None

    assert not original_path.exists()
    assert not thumb_path.exists()


def test_upload_rejects_invalid_image_format(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)

    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)

    with app.app_context(), pytest.raises(ServiceOrderPhotoValidationError):
        service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            photo_type="REPAIR",
            title=None,
            description=None,
            taken_at=None,
            sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(b"not-an-image"), filename="bad.jpg")],
            main_photo_index=None,
            upload_root=tmp_path,
        )


def test_upload_rejects_too_large_file(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)

    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)
    monkeypatch.setattr(photo_service_module, "MAX_UPLOAD_SIZE_BYTES", 128)

    payload = _image_bytes(fmt="JPEG", size=(80, 80))

    with app.app_context(), pytest.raises(ServiceOrderPhotoValidationError):
        service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            photo_type="REPAIR",
            title=None,
            description=None,
            taken_at=None,
            sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(payload), filename="large.jpg")],
            main_photo_index=None,
            upload_root=tmp_path,
        )


def test_role_permissions_for_upload_and_delete(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)

    service = ServiceOrderPhotoService()

    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
    with app.app_context():
        created = service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            photo_type="REPAIR",
            title="Rola",
            description=None,
            taken_at=None,
            sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="role.jpg")],
            main_photo_index=None,
            upload_root=tmp_path,
        )
        photo_id = int(created[0].id)

    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
    with app.app_context(), pytest.raises(ServiceOrderPhotoPermissionError):
        service.delete_photo(photo_id=photo_id, company_id=company_id, branch_id=None, upload_root=tmp_path)

    monkeypatch.setattr(service, "_role_names", lambda: {"administrator"})
    with app.app_context():
        row = service.delete_photo(photo_id=photo_id, company_id=company_id, branch_id=None, upload_root=tmp_path)
        assert row.is_active is False


def test_company_scope_is_enforced(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)

    with app.app_context():
        order_id = _create_order(company_id)
        created = service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            photo_type="REPAIR",
            title=None,
            description=None,
            taken_at=None,
            sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="scope.jpg")],
            main_photo_index=None,
            upload_root=tmp_path,
        )
        photo_id = int(created[0].id)

        other_company = Company(name="Other Co", prefix="OTH")
        db.session.add(other_company)
        db.session.commit()
        other_company_id = int(other_company.id)

    with app.app_context(), pytest.raises(ServiceOrderPhotoNotFoundError):
        service.get_photo(photo_id=photo_id, company_id=other_company_id, branch_id=None)


def test_branch_scope_is_enforced(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)

    with app.app_context():
        branch_a = Branch(name="A", code="A-01", company_id=company_id)
        branch_b = Branch(name="B", code="B-01", company_id=company_id)
        db.session.add_all([branch_a, branch_b])
        db.session.flush()
        branch_a_id = int(branch_a.id)
        branch_b_id = int(branch_b.id)

        order_id = _create_order(company_id, branch_id=branch_b_id)
        created = service.upload_photos(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_b_id,
            user_id=1,
            photo_type="FINAL",
            title=None,
            description=None,
            taken_at=None,
            sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="branch.jpg")],
            main_photo_index=None,
            upload_root=tmp_path,
        )
        photo_id = int(created[0].id)

    with app.app_context(), pytest.raises(ServiceOrderPhotoNotFoundError):
        service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=branch_a_id)
