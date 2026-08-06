from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from app.extensions import db
from app.models.branch import Branch
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.setting import Setting
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.service_order_photo_annotation import PhotoAnnotation
from app.models.service_order_timeline import ServiceOrderTimelineEntry
from app.order_photos.exceptions import ServiceOrderPhotoNotFoundError, ServiceOrderPhotoPermissionError
from app.order_photos.service import ServiceOrderPhotoService


@pytest.fixture()
def photo_annotations_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceOrderPhoto.__table__,
                PhotoAnnotation.__table__,
                ServiceOrderTimelineEntry.__table__,
                Setting.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                PhotoAnnotation.__table__,
                ServiceOrderPhoto.__table__,
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                ServiceOrderTimelineEntry.__table__,
                Setting.__table__,
            ],
        )


def _image_bytes(size: tuple[int, int] = (640, 480), color: tuple[int, int, int] = (80, 120, 160)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size=size, color=color).save(out, format="JPEG")
    return out.getvalue()


def _create_order(company_id: int, *, branch_id: int | None = None) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Adnotacje Klient",
        email="annot@example.com",
        phone="500111222",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Canon",
        model="iR",
        serial_number=f"ANN-SN-{customer.id}",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number=f"SO-ANN-{customer.id}",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Test adnotacji",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)
    db.session.commit()
    return int(order.id)


def _create_photo(company_id: int, order_id: int, upload_root: Path, *, branch_id: int | None = None) -> int:
    service_dir = upload_root / "service_orders" / str(order_id) / "photos"
    thumb_dir = service_dir / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    file_name = "photo_test.jpg"
    (service_dir / file_name).write_bytes(_image_bytes())
    (thumb_dir / "photo_test_thumb.webp").write_bytes(_image_bytes(size=(120, 90)))

    row = ServiceOrderPhoto(
        service_order_id=order_id,
        photo_type="REPAIR",
        title="Test photo",
        description="Photo for annotations",
        file_name=file_name,
        original_file_name="photo_test.jpg",
        mime_type="image/jpeg",
        file_size=(service_dir / file_name).stat().st_size,
        width=640,
        height=480,
        taken_at=datetime.utcnow(),
        sort_order=100,
        is_visible_for_customer=True,
        company_id=company_id,
        branch_id=branch_id,
        created_by=1,
        updated_by=1,
    )
    db.session.add(row)
    db.session.commit()
    return int(row.id)


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def test_create_update_delete_annotation_and_coordinates(app, company_id, photo_annotations_schema, tmp_path, monkeypatch):
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})

    with app.app_context():
        order_id = _create_order(company_id)
        photo_id = _create_photo(company_id, order_id, tmp_path)

        created = service.create_annotation(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            payload={
                "annotation_type": "RECTANGLE",
                "x": "0.10",
                "y": "0.20",
                "width": "0.35",
                "height": "0.25",
                "rotation": "15",
                "color": "#ff0000",
                "title": "Pekniecie",
                "description": "Rysa obudowy",
                "priority": "HIGH",
                "is_visible_for_customer": "y",
                "points_json": "",
            },
        )
        assert created.id is not None
        assert float(created.x) == pytest.approx(0.10, abs=1e-4)
        assert float(created.y) == pytest.approx(0.20, abs=1e-4)
        assert float(created.width) == pytest.approx(0.35, abs=1e-4)
        assert float(created.height) == pytest.approx(0.25, abs=1e-4)

        updated = service.update_annotation(
            annotation_id=created.id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            payload={
                "annotation_type": "CIRCLE",
                "x": "0.22",
                "y": "0.33",
                "width": "0.18",
                "height": "0.18",
                "rotation": "0",
                "color": "#00ff00",
                "title": "Wgniecenie",
                "description": "Do akceptacji",
                "priority": "CRITICAL",
                "is_visible_for_customer": "",
                "points_json": "",
            },
        )
        assert updated.annotation_type == "CIRCLE"
        assert updated.color == "#00ff00"
        assert updated.priority == "CRITICAL"
        assert updated.is_visible_for_customer is False

        monkeypatch.setattr(service, "_role_names", lambda: {"operator"})
        deleted = service.delete_annotation(
            annotation_id=created.id,
            company_id=company_id,
            branch_id=None,
            user_id=7,
        )
        assert deleted.is_active is False
        assert deleted.deleted_by == 7


def test_annotation_rendering_returns_modified_image_bytes(app, company_id, photo_annotations_schema, tmp_path, monkeypatch):
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})

    with app.app_context():
        order_id = _create_order(company_id)
        photo_id = _create_photo(company_id, order_id, tmp_path)

        service.create_annotation(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            payload={
                "annotation_type": "PIN",
                "x": "0.40",
                "y": "0.40",
                "width": "0",
                "height": "0",
                "rotation": "0",
                "color": "#ff3b30",
                "title": "Pin",
                "description": "",
                "priority": "NORMAL",
                "is_visible_for_customer": "y",
                "points_json": "",
            },
        )

        photo = service.get_photo(photo_id=photo_id, company_id=company_id, branch_id=None)
        rendered = service.render_annotated_photo_bytes(
            photo=photo,
            upload_root=tmp_path,
            company_id=company_id,
            branch_id=None,
            customer_only=False,
        )

    assert rendered is not None
    assert rendered[:2] == b"\xff\xd8"


def test_annotation_permissions_and_scope(app, company_id, photo_annotations_schema, tmp_path, monkeypatch):
    service = ServiceOrderPhotoService()

    with app.app_context():
        branch_a = Branch(name="A", code="A-AN", company_id=company_id)
        branch_b = Branch(name="B", code="B-AN", company_id=company_id)
        db.session.add_all([branch_a, branch_b])
        db.session.flush()

        order_id = _create_order(company_id, branch_id=branch_b.id)
        photo_id = _create_photo(company_id, order_id, tmp_path, branch_id=branch_b.id)

        monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
        annotation = service.create_annotation(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=branch_b.id,
            user_id=1,
            payload={
                "annotation_type": "LINE",
                "x": "0.1",
                "y": "0.1",
                "width": "0.2",
                "height": "0.2",
                "rotation": "0",
                "color": "#112233",
                "title": "Linia",
                "description": "",
                "priority": "LOW",
                "is_visible_for_customer": "",
                "points_json": '[{"x":0.1,"y":0.1},{"x":0.3,"y":0.3}]',
            },
        )

        other_company = Company(name="Other annot", prefix="OAN")
        db.session.add(other_company)
        db.session.commit()
        other_company_id = int(other_company.id)
        annotation_id = int(annotation.id)
        branch_a_id = int(branch_a.id)
        branch_b_id = int(branch_b.id)

    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
    with app.app_context(), pytest.raises(ServiceOrderPhotoNotFoundError):
        service.update_annotation(
            annotation_id=annotation_id,
            company_id=other_company_id,
            branch_id=None,
            user_id=1,
            payload={
                "annotation_type": "PIN",
                "x": "0.1",
                "y": "0.1",
                "width": "0",
                "height": "0",
                "rotation": "0",
                "color": "#000000",
                "title": "x",
                "description": "",
                "priority": "NORMAL",
                "is_visible_for_customer": "",
                "points_json": "",
            },
        )

    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
    with app.app_context(), pytest.raises(ServiceOrderPhotoNotFoundError):
        service.list_annotations(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=branch_a_id,
            for_customer=False,
        )

    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})
    with app.app_context(), pytest.raises(ServiceOrderPhotoPermissionError):
        service.delete_annotation(
            annotation_id=annotation_id,
            company_id=company_id,
            branch_id=branch_b_id,
            user_id=1,
        )


def test_protocol_pdf_accepts_annotated_mode(auth_client, app, company_id, photo_annotations_schema, tmp_path, monkeypatch):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    service = ServiceOrderPhotoService()
    monkeypatch.setattr(service, "_role_names", lambda: {"technik"})

    with app.app_context():
        order_id = _create_order(company_id)
        photo_id = _create_photo(company_id, order_id, tmp_path)
        service.create_annotation(
            photo_id=photo_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            payload={
                "annotation_type": "TEXT",
                "x": "0.2",
                "y": "0.2",
                "width": "0",
                "height": "0",
                "rotation": "0",
                "color": "#ff0000",
                "title": "Uszkodzenie",
                "description": "Widoczne pekniecie",
                "priority": "HIGH",
                "is_visible_for_customer": "y",
                "points_json": "",
            },
        )
        db.session.add(
            Setting(
                key="company_name",
                value="Serwis Pro",
                company_id=company_id,
                branch_id=None,
            )
        )
        db.session.commit()

    response = auth_client.get(
        f"/orders/{order_id}/print/intake?mode=download&photo_ids={photo_id}&photo_render_mode=annotated"
    )
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    text = _extract_text(response.data)
    assert "Dokumentacja fotograficzna" in text
    assert "z oznaczeniami" in text
