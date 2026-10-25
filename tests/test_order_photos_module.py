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
from app.models.service_order_number_counter import ServiceOrderNumberCounter
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.order_photos import service as photo_service_module
from app.order_photos.exceptions import (
    ServiceOrderPhotoNotFoundError,
    ServiceOrderPhotoPermissionError,
    ServiceOrderPhotoValidationError,
)
from app.order_photos.service import ServiceOrderPhotoService


@pytest.fixture()
def order_photos_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Customer.__table__,
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderStatusHistory.__table__,
                ServiceOrderNumberCounter.__table__,
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
                ServiceOrderNumberCounter.__table__,
                ServiceOrderStatusHistory.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                Customer.__table__,
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


def test_upload_persists_metadata_and_thumbnail(auth_client, app, company_id, order_photos_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    from app.order_photos import routes as photo_routes
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"operator"})

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


def test_delete_removes_files_and_soft_deletes(auth_client, app, company_id, order_photos_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    from app.order_photos import routes as photo_routes
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"administrator"})

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


def test_failed_delete_commit_keeps_photo_files(auth_client, app, company_id, order_photos_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        order_id = _create_order(company_id)
        service = ServiceOrderPhotoService()
        monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)
        row = service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=app.config["TEST_USER_ID"],
            photo_type="REPAIR", title=None, description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="delete-rollback.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )[0]
        photo_id = int(row.id)
        original_path, thumb_path = service.photo_file_paths(upload_root=tmp_path, order_id=order_id, file_name=row.file_name)

    from app.order_photos import routes as photo_routes
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"administrator"})
    monkeypatch.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("simulated commit failure")))
    with app.app_context(), pytest.raises(RuntimeError, match="simulated commit failure"):
        photo_routes.service.delete_photo(photo_id=photo_id, company_id=company_id, branch_id=None, upload_root=tmp_path)
    monkeypatch.undo()

    with app.app_context():
        db.session.rollback()
        persisted = db.session.get(ServiceOrderPhoto, photo_id)
        assert persisted is not None and persisted.is_active is True
    assert original_path.exists()
    assert thumb_path.exists()


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


def test_upload_rejects_excessive_image_dimensions(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)

    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)
    monkeypatch.setattr(photo_service_module, "MAX_IMAGE_PIXELS", 100)

    with app.app_context(), pytest.raises(ServiceOrderPhotoValidationError, match="Wymiary zdjęcia"):
        service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=1,
            photo_type="REPAIR", title=None, description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes(size=(64, 64))), filename="pixels.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )


def test_upload_uses_detected_image_type_not_declared_extension(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)

    with app.app_context():
        row = service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=1,
            photo_type="RECEPTION", title=None, description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes(fmt="PNG")), filename="declared-as-jpeg.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )[0]
        assert row.mime_type == "image/png"
        assert row.file_name.endswith(".png")


def test_upload_rejects_more_than_configured_file_count(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)
    files = [
        photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename=f"image-{index}.jpg")
        for index in range(photo_service_module.MAX_UPLOAD_FILES + 1)
    ]
    with app.app_context(), pytest.raises(ServiceOrderPhotoValidationError, match="maksymalnie"):
        service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=1,
            photo_type="REPAIR", title=None, description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False, files=files, main_photo_index=None, upload_root=tmp_path,
        )


def test_photo_paths_reject_traversal_names(app, tmp_path):
    service = ServiceOrderPhotoService()
    with app.app_context(), pytest.raises(ServiceOrderPhotoNotFoundError):
        service.photo_file_paths(upload_root=tmp_path, order_id=1, file_name="../../outside.jpg")


def test_photo_permissions_fail_closed_when_no_roles_are_available(app, company_id, order_photos_schema, tmp_path, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)

    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_role_names", lambda: set())
    with app.app_context(), pytest.raises(ServiceOrderPhotoPermissionError):
        service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=1,
            photo_type="REPAIR", title=None, description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="denied.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )


def test_customer_gallery_only_lists_and_serves_customer_visible_photos(auth_client, app, company_id, order_photos_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        order_id = _create_order(company_id)
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_ensure_add_permission", lambda: None)
    with app.app_context():
        photos = service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=app.config["TEST_USER_ID"],
            photo_type="RECEPTION", title="Visible intake", description="Front cover visible", taken_at=None,
            sort_order=100, is_visible_for_customer=True,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="visible.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )
        visible_id = photos[0].id
        private = service.upload_photos(
            order_id=order_id, company_id=company_id, branch_id=None, user_id=app.config["TEST_USER_ID"],
            photo_type="REPAIR", title="Private repair", description="Internal note", taken_at=None,
            sort_order=100, is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes(color=(180, 20, 20))), filename="private.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )
        private_id = private[0].id

    from app.order_photos import routes as photo_routes
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"customer"})
    monkeypatch.setattr(photo_routes.service, "is_customer_portal_user", lambda: True)
    gallery = auth_client.get(f"/order-photos/orders/{order_id}/gallery")
    assert gallery.status_code == 200
    assert "Visible intake" in gallery.get_data(as_text=True)
    assert "Private repair" not in gallery.get_data(as_text=True)
    assert "Dodaj zdjęcia" not in gallery.get_data(as_text=True)
    assert auth_client.get(f"/order-photos/{visible_id}/thumbnail").status_code == 200
    assert auth_client.get(f"/order-photos/{private_id}/thumbnail").status_code == 404
    assert auth_client.get(f"/order-photos/{private_id}/file").status_code == 404


def test_gallery_renders_empty_state_for_order_without_photos(auth_client, app, company_id, order_photos_schema):
    with app.app_context():
        order_id = _create_order(company_id)

    response = auth_client.get(f"/order-photos/orders/{order_id}/gallery")
    assert response.status_code == 200
    assert "Brak zdjęć dla wybranych filtrów." in response.get_data(as_text=True)


def test_gallery_defaults_to_all_photo_stages_and_keeps_stage_filter(auth_client, app, company_id, order_photos_schema, monkeypatch, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    with app.app_context():
        order_id = _create_order(company_id)
        another_order_id = _create_order(company_id)
        photo_service = ServiceOrderPhotoService()
        monkeypatch.setattr(photo_service, "_ensure_add_permission", lambda: None)
        for photo_type, title in (("RECEPTION", "Default reception photo"), ("REPAIR", "Default repair photo")):
            photo_service.upload_photos(
                order_id=order_id, company_id=company_id, branch_id=None, user_id=app.config["TEST_USER_ID"],
                photo_type=photo_type, title=title, description=None, taken_at=None, sort_order=100,
                is_visible_for_customer=False,
                files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename=f"{photo_type}.jpg")],
                main_photo_index=None, upload_root=tmp_path,
            )
        photo_service.upload_photos(
            order_id=another_order_id, company_id=company_id, branch_id=None, user_id=app.config["TEST_USER_ID"],
            photo_type="REPAIR", title="Another order only", description=None, taken_at=None, sort_order=100,
            is_visible_for_customer=False,
            files=[photo_service_module.FileStorage(stream=io.BytesIO(_image_bytes()), filename="OTHER.jpg")],
            main_photo_index=None, upload_root=tmp_path,
        )

    from app.order_photos import routes as photo_routes
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"operator"})
    monkeypatch.setattr(photo_routes.service, "is_customer_portal_user", lambda: False)
    default = auth_client.get(f"/order-photos/orders/{order_id}/gallery")
    assert default.status_code == 200
    assert "Default reception photo" in default.get_data(as_text=True)
    assert "Default repair photo" in default.get_data(as_text=True)
    assert "Another order only" not in default.get_data(as_text=True)

    filtered = auth_client.get(f"/order-photos/orders/{order_id}/gallery?photo_type=REPAIR")
    assert filtered.status_code == 200
    assert "Default repair photo" in filtered.get_data(as_text=True)
    assert "Default reception photo" not in filtered.get_data(as_text=True)


def test_upload_request_size_limit_rejects_before_multipart_validation(auth_client, app, company_id, order_photos_schema, monkeypatch):
    with app.app_context():
        order_id = _create_order(company_id)
    from app.order_photos import routes as photo_routes

    monkeypatch.setattr(photo_routes, "MAX_UPLOAD_REQUEST_BYTES", 32)
    response = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "REPAIR", "files": [_upload_file_payload()]},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    with app.app_context():
        assert db.session.query(ServiceOrderPhoto).filter_by(service_order_id=order_id).count() == 0


def test_create_order_form_stages_photos_and_uploads_only_after_real_order_exists(auth_client, app, company_id, order_photos_schema, monkeypatch):
    from app.order_photos import routes as photo_routes
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"technik"})
    monkeypatch.setattr(orders_routes.photo_service, "can_manage_photos", lambda: True)
    form_page = auth_client.get("/orders/new")
    assert form_page.status_code == 200
    body = form_page.get_data(as_text=True)
    assert 'id="order-create-photo-files"' in body
    assert 'id="order-create-add-photo"' in body
    assert 'id="order-photo-draft-token"' in body

    with app.app_context():
        customer = Customer(full_name="Create With Photo", company_id=company_id)
        db.session.add(customer)
        db.session.flush()
        device = Device(device_type="Printer", manufacturer="PhotoMaker", model="P1", company_id=company_id)
        db.session.add(device)
        db.session.commit()
        customer_id, device_id = customer.id, device.id

    draft_token = "8f428d31-cc82-45de-90cc-26dcd25a4424"
    response = auth_client.post("/orders/new", data={
        "customer_id": str(customer_id),
        "device_id": str(device_id),
        "order_type": "STANDARD",
        "intake_date": date.today().isoformat(),
        "status": "RECEIVED",
        "priority": "NORMAL",
        "issue_description": "Order with staged photo",
        "photo_draft_token": draft_token,
    }, follow_redirects=False)
    assert response.status_code == 302
    from urllib.parse import parse_qs, urlparse

    from app.orders import routes as order_routes
    redirect_parts = urlparse(response.headers["Location"])
    order_id = int(redirect_parts.path.rsplit("/", 1)[1])
    signed_draft_token = parse_qs(redirect_parts.query)["pending_photo_token"][0]
    assert signed_draft_token != draft_token
    with app.app_context():
        assert order_routes._validated_photo_draft_token(
            signed_draft_token, order_id=order_id, company_id=company_id, user_id=app.config["TEST_USER_ID"]
        ) == draft_token
        assert order_routes._validated_photo_draft_token(
            signed_draft_token, order_id=order_id + 1, company_id=company_id, user_id=app.config["TEST_USER_ID"]
        ) is None
        assert order_routes._validated_photo_draft_token(
            signed_draft_token, order_id=order_id, company_id=company_id + 1, user_id=app.config["TEST_USER_ID"]
        ) is None

    uploaded = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "RECEPTION", "description": "Queued at order create", "files": [_upload_file_payload("queued.jpg")]},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert uploaded.status_code == 200
    assert uploaded.get_json()["ok"] is True
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 1
        photo = db.session.query(ServiceOrderPhoto).one()
        assert photo.service_order_id == order_id
        assert photo.description == "Queued at order create"


def test_failed_create_does_not_create_photo_orphan(auth_client, app, company_id, order_photos_schema, monkeypatch):
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    response = auth_client.post("/orders/new", data={
        "customer_id": "999999",
        "device_id": "999999",
        "intake_date": date.today().isoformat(),
        "photo_draft_token": "c87835b1-d95b-40bf-9791-6a2fd52bd004",
    })
    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 0
        assert db.session.query(ServiceOrderPhoto).count() == 0


def test_photo_upload_failure_and_retry_do_not_repeat_order_create(auth_client, app, company_id, order_photos_schema, monkeypatch, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    from app.order_photos import routes as photo_routes
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"technik"})
    monkeypatch.setattr(orders_routes.photo_service, "can_manage_photos", lambda: True)
    with app.app_context():
        customer = Customer(full_name="Retry Photo Customer", company_id=company_id)
        db.session.add(customer)
        db.session.flush()
        device = Device(device_type="Printer", manufacturer="RetryMaker", model="R1", company_id=company_id)
        db.session.add(device)
        db.session.commit()
        customer_id, device_id = customer.id, device.id

    created = auth_client.post("/orders/new", data={
        "customer_id": str(customer_id), "device_id": str(device_id), "order_type": "STANDARD",
        "intake_date": date.today().isoformat(), "status": "RECEIVED", "priority": "NORMAL",
        "issue_description": "Order remains after separate photo failure",
    }, follow_redirects=False)
    order_id = int(created.headers["Location"].rstrip("/").split("/")[-1])

    monkeypatch.setattr(photo_routes.service, "_ensure_add_permission", lambda: (_ for _ in ()).throw(ServiceOrderPhotoPermissionError("test denied")))
    failed_upload = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "REPAIR", "files": [_upload_file_payload("retry.jpg")]},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert failed_upload.status_code == 403
    assert "test denied" in failed_upload.get_json()["message"]
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 1
        assert db.session.query(ServiceOrderPhoto).count() == 0

    monkeypatch.setattr(photo_routes.service, "_ensure_add_permission", lambda: None)
    retry_upload = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "REPAIR", "files": [_upload_file_payload("retry.jpg")]},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert retry_upload.status_code == 200
    assert retry_upload.get_json()["ok"] is True
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 1
        photo = db.session.query(ServiceOrderPhoto).one()
        assert photo.service_order_id == order_id


def test_ajax_photo_upload_requires_valid_csrf_token(auth_client, app, company_id, order_photos_schema):
    with app.app_context():
        order_id = _create_order(company_id)
    response = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "REPAIR", "files": [_upload_file_payload("csrf.jpg")]},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 403


def test_order_edit_form_uploads_photo_without_resubmitting_order(auth_client, app, company_id, order_photos_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    from app.order_photos import routes as photo_routes
    from app.orders import routes as orders_routes
    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    monkeypatch.setattr(photo_routes.service, "_role_names", lambda: {"technik"})
    monkeypatch.setattr(orders_routes.photo_service, "can_manage_photos", lambda: True)

    with app.app_context():
        order_id = _create_order(company_id)
        original_number = db.session.get(ServiceOrder, order_id).order_number

    edit_page = auth_client.get(f"/orders/{order_id}/edit")
    assert edit_page.status_code == 200
    body = edit_page.get_data(as_text=True)
    assert 'id="order-edit-photo-upload-form"' in body
    assert 'id="order-edit-add-photo"' in body
    assert 'id="order-edit-photo-files"' in body
    assert 'action="/order-photos/orders/' in body

    uploaded = auth_client.post(
        f"/order-photos/orders/{order_id}/upload",
        data={"photo_type": "REPAIR", "description": "Added from edit form", "files": [_upload_file_payload("edit.jpg")]},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert uploaded.status_code == 200
    assert uploaded.get_json()["ok"] is True
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 1
        order = db.session.get(ServiceOrder, order_id)
        photo = db.session.query(ServiceOrderPhoto).one()
        assert order is not None and order.order_number == original_number
        assert photo.service_order_id == order_id
        assert photo.description == "Added from edit form"


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
