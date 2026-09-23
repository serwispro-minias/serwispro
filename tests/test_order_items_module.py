from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_category import ProductCategory
from app.models.catalog_service_item import CatalogServiceItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.models.purchase_request import PurchaseRequest
from app.orders.item_service import ServiceOrderItemService
from app.models.vat_rate import VatRate


@pytest.fixture()
def order_items_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                CatalogPart.__table__,
                ProductCategory.__table__,
                VatRate.__table__,
                CatalogMaterial.__table__,
                CatalogServiceItem.__table__,
                CatalogStockMovement.__table__,
                ServiceEstimate.__table__,
                ServiceEstimateItem.__table__,
                ServiceOrderItem.__table__,
                PurchaseRequest.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceOrderItem.__table__,
                CatalogStockMovement.__table__,
                CatalogServiceItem.__table__,
                CatalogMaterial.__table__,
                CatalogPart.__table__,
                VatRate.__table__,
                ProductCategory.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                ServiceEstimateItem.__table__,
                ServiceEstimate.__table__,
                PurchaseRequest.__table__,
            ],
        )


def _create_order(company_id: int) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Order Items Customer",
        email="order-items@example.com",
        phone="500500500",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Canon",
        model="MF643Cdw",
        serial_number="SN-ITEM-1",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-ITEM-001",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date(2026, 8, 6),
        issue_description="Problem testowy",
        company_id=company_id,
    )
    db.session.add(order)
    db.session.commit()
    return int(order.id)


def _create_catalog_records(company_id: int):
    category = ProductCategory(code="ITEM-CAT", name="Części", company_id=company_id)
    vat = VatRate(code="ITEM-23", rate=23, company_id=company_id, is_active=True)
    db.session.add_all([category, vat])
    db.session.flush()
    part = CatalogPart(
        code="PART-001",
        name="Rolka poboru",
        category_id=category.id,
        vat_id=vat.id,
        current_stock=10,
        purchase_price_net=Decimal("10.00"),
        sale_price_net=Decimal("20.00"),
        company_id=company_id,
    )
    material = CatalogMaterial(
        code="MAT-001",
        name="Alkohol izopropylowy",
        unit="l",
        current_stock=Decimal("5"),
        minimum_stock=Decimal("1"),
        purchase_price_net=Decimal("8.00"),
        default_usage_qty=Decimal("1"),
        vat_rate=Decimal("23"),
        company_id=company_id,
    )
    service_item = CatalogServiceItem(
        code="SERV-001",
        name="Kalibracja",
        default_price_net=Decimal("50.00"),
        vat_rate=Decimal("23"),
        standard_duration_minutes=30,
        is_sellable=True,
        company_id=company_id,
    )
    db.session.add_all([part, material, service_item])
    db.session.commit()
    return int(part.id), int(material.id), int(service_item.id)


def _patch_order_view_dependencies(monkeypatch):
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes.service, "get_status_history", lambda order_id, company_id: [])
    monkeypatch.setattr(orders_routes.notification_service, "list_messages_for_order", lambda order_id, company_id, branch_id: [])
    monkeypatch.setattr(orders_routes.action_service, "list_actions", lambda order_id, company_id, branch_id: [])


def test_order_items_tab_and_lifecycle(auth_client, app, company_id, order_items_schema, monkeypatch):
    _patch_order_view_dependencies(monkeypatch)

    with app.app_context():
        order_id = _create_order(company_id)
        part_id, material_id, service_id = _create_catalog_records(company_id)

    response = auth_client.get(f"/orders/{order_id}?tab=items")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Części i usługi" in body
    assert "Kosztorys zlecenia" in body

    add_part = auth_client.post(
        f"/orders/{order_id}/items",
        data={
            "item_type": "PART",
            "item_id": str(part_id),
            "search_query": "Rolka",
            "quantity": "3",
            "unit_price_net": "20.00",
            "discount_percent": "0",
            "notes": "",
        },
    )
    assert add_part.status_code == 200
    assert add_part.get_json()["ok"] is True

    add_material = auth_client.post(
        f"/orders/{order_id}/items",
        data={
            "item_type": "MATERIAL",
            "item_id": str(material_id),
            "search_query": "Alkohol",
            "quantity": "2",
            "unit_price_net": "8.00",
            "discount_percent": "0",
            "notes": "",
        },
    )
    assert add_material.status_code == 200
    assert add_material.get_json()["ok"] is True

    add_service = auth_client.post(
        f"/orders/{order_id}/items",
        data={
            "item_type": "SERVICE",
            "item_id": str(service_id),
            "search_query": "Kalibracja",
            "quantity": "1",
            "unit_price_net": "50.00",
            "discount_percent": "0",
            "notes": "",
        },
    )
    assert add_service.status_code == 200
    assert add_service.get_json()["ok"] is True

    with app.app_context():
        items = db.session.query(ServiceOrderItem).filter_by(service_order_id=order_id).order_by(ServiceOrderItem.id.asc()).all()
        assert len(items) == 3
        totals = ServiceOrderItemService().compute_totals(
            [
                {
                    "item_type": item.item_type,
                    "total_net": str(item.total_net),
                    "vat_rate": str(item.vat_rate),
                }
                for item in items
            ]
        )
        assert totals.parts_net == Decimal("60.00")
        assert totals.materials_net == Decimal("16.00")
        assert totals.services_net == Decimal("50.00")
        assert totals.gross == Decimal("154.98")

        part_item_id = int(items[0].id)

    use_part = auth_client.post(
        f"/orders/{order_id}/items/{part_item_id}/use",
        data={"quantity": "2", "submit_use": "1"},
    )
    assert use_part.status_code == 200
    assert use_part.get_json()["ok"] is True

    return_part = auth_client.post(
        f"/orders/{order_id}/items/{part_item_id}/return",
        data={"quantity": "1", "submit_return": "1"},
    )
    assert return_part.status_code == 200
    assert return_part.get_json()["ok"] is True

    with app.app_context():
        refreshed_part = db.session.get(ServiceOrderItem, items[0].id)
        refreshed_material = db.session.get(ServiceOrderItem, items[1].id)
        refreshed_service = db.session.get(ServiceOrderItem, items[2].id)
        assert refreshed_part is not None
        assert Decimal(refreshed_part.reserved_quantity) == Decimal("0.000")
        assert Decimal(refreshed_part.used_quantity) == Decimal("2.000")
        assert Decimal(refreshed_part.returned_quantity) == Decimal("1.000")
        assert refreshed_material is not None
        assert Decimal(refreshed_material.reserved_quantity) == Decimal("2.000")
        assert refreshed_service is not None
        assert Decimal(refreshed_service.reserved_quantity) == Decimal("0.000")

        part = db.session.get(CatalogPart, part_id)
        material = db.session.get(CatalogMaterial, material_id)
        assert part is not None and Decimal(part.current_stock) == Decimal("9.000")
        assert material is not None and Decimal(material.current_stock) == Decimal("5.000")
