from __future__ import annotations

import io
from datetime import date

import pytest

from app.extensions import db
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.device import Device
from app.models.inventory_part import InventoryPart
from app.models.inventory_stock_operation import InventoryStockOperation
from app.models.service_order import ServiceOrder
from app.models.service_order_part_usage import ServiceOrderPartUsage
from app.models.service_order_timeline import ServiceOrderTimelineAttachment, ServiceOrderTimelineEntry


@pytest.fixture()
def order_timeline_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                InventoryPart.__table__,
                InventoryStockOperation.__table__,
                ServiceOrderPartUsage.__table__,
                ServiceOrderTimelineEntry.__table__,
                ServiceOrderTimelineAttachment.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceOrderTimelineAttachment.__table__,
                ServiceOrderTimelineEntry.__table__,
                ServiceOrderPartUsage.__table__,
                InventoryStockOperation.__table__,
                InventoryPart.__table__,
                ServiceOrder.__table__,
                Device.__table__,
            ],
        )


def _create_service_order(company_id: int, branch_id: int | None = None) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Timeline Test Customer",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Test",
        model="Device",
        serial_number="SN-TIMELINE-1",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()

    service_order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-TIMELINE-1",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Initial issue",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(service_order)
    db.session.commit()
    return int(service_order.id)


def test_order_edit_contains_timeline_tab(auth_client, app, company_id, order_timeline_schema):
    with app.app_context():
        service_order_id = _create_service_order(company_id)

    response = auth_client.get(f"/orders/{service_order_id}/edit")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Historia naprawy / Czynności serwisowe" in body


def test_add_timeline_entry_with_attachment_ajax(auth_client, app, company_id, order_timeline_schema, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    with app.app_context():
        service_order_id = _create_service_order(company_id)

    response = auth_client.post(
        f"/orders/{service_order_id}/timeline",
        data={
            "entry_type": "DIAGNOSIS",
            "description": "Sprawdzono płytę główną i wykonano pomiary.",
            "parts_cost": "123.45",
            "labor_minutes": "35",
            "attachments": (io.BytesIO(b"%PDF-1.4 test file"), "report.pdf"),
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["ok"] is True
    assert "Sprawdzono płytę główną" in payload["entry_html"]
    assert "report.pdf" in payload["entry_html"]

    with app.app_context():
        entry = db.session.query(ServiceOrderTimelineEntry).filter_by(service_order_id=service_order_id).one()
        attachment = db.session.query(ServiceOrderTimelineAttachment).filter_by(entry_id=entry.id).one()

        assert entry.company_id == company_id
        assert entry.entry_type == "DIAGNOSIS"
        assert entry.labor_minutes == 35
        assert attachment.company_id == company_id
        assert attachment.original_filename == "report.pdf"


def test_timeline_entry_respects_branch_scope(auth_client, app, company_id, order_timeline_schema):
    with app.app_context():
        branch = Branch(name="Other Branch", code="SER-OTHER", company_id=company_id)
        db.session.add(branch)
        db.session.flush()

        service_order_id = _create_service_order(company_id, branch_id=branch.id)

    response = auth_client.post(
        f"/orders/{service_order_id}/timeline",
        data={
            "entry_type": "REPAIR",
            "description": "Wymieniono uszkodzony element.",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload is not None
    assert payload["ok"] is False

    with app.app_context():
        assert db.session.query(ServiceOrderTimelineEntry).count() == 0
