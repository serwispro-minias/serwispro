from __future__ import annotations

from datetime import date
from decimal import Decimal
import io

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models.branch import Branch
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_service_item import CatalogServiceItem
from app.models.customer import Customer
from app.models.device import Device
from app.models.setting import Setting
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_material_usage import ServiceOrderMaterialUsage
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.service_order_service_line import ServiceOrderServiceLine
from app.models.user import User


def _schema_tables() -> list:
    return [
        Device.__table__,
        ServiceOrder.__table__,
        CatalogPart.__table__,
        CatalogMaterial.__table__,
        CatalogServiceItem.__table__,
        Setting.__table__,
        ServiceOrderPartReservation.__table__,
        ServiceOrderMaterialUsage.__table__,
        ServiceOrderServiceLine.__table__,
        ServiceEstimate.__table__,
        ServiceEstimateItem.__table__,
    ]


@pytest.fixture()
def estimates_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=_schema_tables())

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(_schema_tables())))


def _create_order(company_id: int, *, branch_id: int | None = None) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Klient Kosztorysu",
        email="estimate@example.com",
        phone="500500500",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Brother",
        model="HL-L2352DW",
        serial_number="SN-EST-1",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-EST-001",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date(2026, 8, 6),
        issue_description="Brak podawania papieru",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)
    db.session.flush()

    part = CatalogPart(
        code="PART-EST-1",
        name="Rolki poboru",
        unit="szt.",
        current_stock=10,
        minimum_stock=1,
        purchase_price_net=12.00,
        sale_price_net=24.00,
        vat_rate=23,
        company_id=company_id,
        branch_id=branch_id,
    )
    material = CatalogMaterial(
        code="MAT-EST-1",
        name="Środek czyszczący",
        unit="l",
        current_stock=5,
        minimum_stock=1,
        purchase_price_net=8.00,
        default_usage_qty=1,
        vat_rate=23,
        company_id=company_id,
        branch_id=branch_id,
    )
    service_item = CatalogServiceItem(
        code="SRV-EST-1",
        name="Kalibracja",
        default_price_net=80.00,
        vat_rate=23,
        standard_duration_minutes=30,
        is_sellable=True,
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add_all([part, material, service_item])
    db.session.flush()

    db.session.add_all(
        [
            ServiceOrderPartReservation(
                service_order_id=order.id,
                part_id=part.id,
                quantity=2,
                status="RESERVED",
                company_id=company_id,
                branch_id=branch_id,
            ),
            ServiceOrderMaterialUsage(
                service_order_id=order.id,
                material_id=material.id,
                quantity=3,
                unit_net_price=8.00,
                vat_rate=23,
                net_value=24.00,
                vat_value=5.52,
                gross_value=29.52,
                company_id=company_id,
                branch_id=branch_id,
            ),
            ServiceOrderServiceLine(
                service_order_id=order.id,
                service_item_id=service_item.id,
                quantity=1,
                unit_net_price=80.00,
                vat_rate=23,
                net_value=80.00,
                vat_value=18.40,
                gross_value=98.40,
                duration_minutes=30,
                company_id=company_id,
                branch_id=branch_id,
            ),
        ]
    )
    db.session.commit()
    return int(order.id)


def _patch_order_detail_dependencies(monkeypatch):
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes.service, "get_status_history", lambda order_id, company_id: [])
    monkeypatch.setattr(orders_routes.notification_service, "list_messages_for_order", lambda order_id, company_id, branch_id: [])
    monkeypatch.setattr(orders_routes.action_service, "list_actions", lambda order_id, company_id, branch_id: [])


def test_order_tab_can_create_estimate_and_render_pdf(auth_client, app, company_id, estimates_schema, monkeypatch):
    _patch_order_detail_dependencies(monkeypatch)

    with app.app_context():
        order_id = _create_order(company_id)

    response = auth_client.get(f"/orders/{order_id}?tab=estimates")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Kosztorys" in body
    assert "Brak zapisanych wersji kosztorysu" in body

    created = auth_client.post(
        f"/services/orders/{order_id}/estimates",
        data={"valid_until": "2026-08-20", "notes": "Wersja testowa"},
        follow_redirects=False,
    )
    assert created.status_code == 302
    assert "/services/" in created.headers["Location"]

    estimate_id = int(created.headers["Location"].rstrip("/").split("/")[-1])

    with app.app_context():
        estimate = db.session.get(ServiceEstimate, estimate_id)
        assert estimate is not None
        assert estimate.version_number == 1
        assert estimate.status == "DRAFT"
        assert len(estimate.items) == 3
        assert estimate.gross_total == Decimal("186.96")

    pdf = auth_client.get(f"/services/{estimate_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    reader = PdfReader(io.BytesIO(pdf.data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Kosztorys naprawy" in text
    assert "SO-EST-001" in text
    assert "Klient Kosztorysu" in text


def test_sent_estimate_creates_new_revision_when_edited(auth_client, app, company_id, estimates_schema):
    with app.app_context():
        order_id = _create_order(company_id)

    created = auth_client.post(
        f"/services/orders/{order_id}/estimates",
        data={"valid_until": "2026-08-20", "notes": "Wersja testowa"},
        follow_redirects=False,
    )
    estimate_id = int(created.headers["Location"].rstrip("/").split("/")[-1])

    sent = auth_client.post(f"/services/{estimate_id}/send", follow_redirects=False)
    assert sent.status_code == 302

    edited = auth_client.post(
        f"/services/{estimate_id}/items",
        data={
            "name": "Dodatkowa usługa",
            "quantity": "1",
            "unit": "szt.",
            "unit_net_price": "50.00",
            "discount_percent": "0",
            "vat_rate": "23",
            "description": "Pozycja manualna",
        },
        follow_redirects=False,
    )
    assert edited.status_code == 302
    new_estimate_id = int(edited.headers["Location"].rstrip("/").split("/")[-1])
    assert new_estimate_id != estimate_id

    with app.app_context():
        estimates = db.session.query(ServiceEstimate).filter_by(service_order_id=order_id).order_by(ServiceEstimate.version_number.asc()).all()
        assert len(estimates) == 2
        assert estimates[0].status == "SENT"
        assert estimates[1].status == "DRAFT"
        assert len(estimates[1].items) == 4
        assert estimates[1].gross_total > estimates[0].gross_total


def test_estimate_routes_respect_branch_scope(auth_client, app, company_id, estimates_schema):
    with app.app_context():
        branch_a = Branch(name="Oddział A", code="A", company_id=company_id)
        branch_b = Branch(name="Oddział B", code="B", company_id=company_id)
        db.session.add_all([branch_a, branch_b])
        db.session.flush()

        user = db.session.get(User, app.config["TEST_USER_ID"])
        assert user is not None
        user.branch_id = branch_b.id
        order_id = _create_order(company_id, branch_id=branch_b.id)
        from app.services.service import estimate_service

        estimate = estimate_service.create_from_order(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_b.id,
            user_id=user.id,
            valid_until=date(2026, 8, 20),
            notes="Branch scope",
        )
        estimate_id = estimate.id

        user.branch_id = branch_a.id
        db.session.commit()

    response = auth_client.get(f"/services/{estimate_id}")
    assert response.status_code == 404
