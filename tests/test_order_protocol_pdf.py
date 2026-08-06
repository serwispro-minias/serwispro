from __future__ import annotations

import base64
import io
from datetime import date

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_timeline import ServiceOrderTimelineAttachment, ServiceOrderTimelineEntry
from app.models.setting import Setting


@pytest.fixture()
def order_protocol_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Setting.__table__,
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
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
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                Setting.__table__,
            ],
        )


def _create_protocol_order(company_id: int, *, long_text: bool = False) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Zażółć Gęślą Jaźń",
        email="zazolc@example.com",
        phone="500600700",
        city="Poznań",
        street="Kwiatowa",
        building_no="12",
        apartment_no="7",
        postal_code="60-001",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Brother",
        model="T720",
        serial_number="SN-PL-001",
        inventory_number="INV-100",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    issue_description = "Uszkodzenie mechanizmu podawania papieru. Zażółć gęślą jaźń."
    if long_text:
        issue_description = " ".join([issue_description] * 240)

    service_order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-PDF-1",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date(2026, 8, 3),
        planned_finish_date=date(2026, 8, 10),
        issue_description=issue_description,
        repair_description="Widoczne zarysowania obudowy.",
        customer_notes="Kabel zasilający, tusz, instrukcja.",
        technician_notes="Pilna weryfikacja rolek.",
        estimated_cost=149.50,
        final_cost=199.00,
        company_id=company_id,
    )
    db.session.add(service_order)
    db.session.flush()

    entries = [
        ServiceOrderTimelineEntry(
            service_order_id=service_order.id,
            author_user_id=1,
            entry_type="DIAGNOSIS",
            description="Sprawdzono mechanizm rolek i poboru papieru.",
            parts_cost=None,
            labor_minutes=20,
            company_id=company_id,
        ),
        ServiceOrderTimelineEntry(
            service_order_id=service_order.id,
            author_user_id=1,
            entry_type="REPAIR",
            description="Wymieniono zużyte rolki poboru.",
            parts_cost=59.90,
            labor_minutes=45,
            company_id=company_id,
        ),
        ServiceOrderTimelineEntry(
            service_order_id=service_order.id,
            author_user_id=1,
            entry_type="PARTS_ORDER",
            description="Rolki poboru papieru + separator.",
            parts_cost=39.90,
            labor_minutes=None,
            company_id=company_id,
        ),
    ]
    db.session.add_all(entries)
    db.session.add(
        ServiceOrderAction(
            service_order_id=service_order.id,
            company_id=company_id,
            action_date=date(2026, 8, 5),
            action_type="REPAIR",
            description="Wymieniono zespół rolek i wykonano kalibrację.",
            work_time_minutes=45,
            cost=129.90,
            is_visible_for_customer=True,
        )
    )
    db.session.commit()
    return int(service_order.id)


def _add_company_settings(company_id: int, logo_path: str | None = None) -> None:
    settings = [
        Setting(key="company_name", value="SerwisPRO Test", company_id=company_id),
        Setting(key="company_address", value="ul. Testowa 1, 00-001 Warszawa", company_id=company_id),
        Setting(key="company_nip", value="1234567890", company_id=company_id),
        Setting(key="company_phone", value="+48 22 000 00 00", company_id=company_id),
        Setting(key="company_email", value="serwis@test.local", company_id=company_id),
        Setting(key="company_website", value="www.test.local", company_id=company_id),
        Setting(key="repair_warranty_info", value="Gwarancja 90 dni na wykonaną naprawę.", company_id=company_id),
    ]
    if logo_path:
        settings.append(Setting(key="company_logo", value=logo_path, company_id=company_id))

    db.session.add_all(settings)
    db.session.commit()


def _extract_text(pdf_bytes: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return len(reader.pages), text


def test_generate_intake_protocol_pdf_with_polish_text(auth_client, app, company_id, order_protocol_schema):
    with app.app_context():
        order_id = _create_protocol_order(company_id)
        _add_company_settings(company_id)

    response = auth_client.get(f"/orders/{order_id}/print/intake")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"

    page_count, text = _extract_text(response.data)
    assert page_count >= 1
    assert "Protokół przyjęcia sprzętu do serwisu" in text
    assert "Zażółć Gęślą Jaźń" in text
    assert "Opis zgłoszonej usterki" in text


def test_generate_release_protocol_pdf_contains_costs(auth_client, app, company_id, order_protocol_schema):
    with app.app_context():
        order_id = _create_protocol_order(company_id)
        _add_company_settings(company_id)

    response = auth_client.get(f"/orders/{order_id}/print/release")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"

    page_count, text = _extract_text(response.data)
    assert page_count >= 1
    assert "Protokół wydania sprzętu z serwisu" in text
    assert "Koszt usługi" in text
    assert "Koszt części" in text
    assert "Kwota do zapłaty" in text
    assert "Historia napraw" in text
    assert "Wymieniono zespół rolek i wykonano kalibrację." in text


def test_short_description_fits_single_page(auth_client, app, company_id, order_protocol_schema):
    with app.app_context():
        order_id = _create_protocol_order(company_id, long_text=False)
        _add_company_settings(company_id)

    response = auth_client.get(f"/orders/{order_id}/print/intake")
    assert response.status_code == 200

    page_count, _ = _extract_text(response.data)
    assert page_count == 1


def test_long_description_breaks_to_multiple_pages(auth_client, app, company_id, order_protocol_schema):
    with app.app_context():
        order_id = _create_protocol_order(company_id, long_text=True)
        _add_company_settings(company_id)

    response = auth_client.get(f"/orders/{order_id}/print/intake")
    assert response.status_code == 200

    page_count, _ = _extract_text(response.data)
    assert page_count >= 2


def test_logo_path_is_renderable(auth_client, app, company_id, order_protocol_schema, tmp_path):
    logo_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO6Y8y8AAAAASUVORK5CYII="
    )
    logo_file = tmp_path / "logo.png"
    logo_file.write_bytes(logo_data)

    with app.app_context():
        order_id = _create_protocol_order(company_id)
        _add_company_settings(company_id, logo_path=str(logo_file))

    response = auth_client.get(f"/orders/{order_id}/print/intake")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_pdf_preview_redirect(auth_client, app, company_id, order_protocol_schema):
    with app.app_context():
        order_id = _create_protocol_order(company_id)
        _add_company_settings(company_id)

    response = auth_client.get(f"/orders/{order_id}/print/preview?protocol=release", follow_redirects=False)
    assert response.status_code == 302
    assert f"/orders/{order_id}/print/release" in response.headers["Location"]
