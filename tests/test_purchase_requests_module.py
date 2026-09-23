from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.branch import Branch
from app.models.catalog_part import CatalogPart
from app.models.catalog_category import ProductCategory
from app.models.vat_rate import VatRate
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.purchase_request import (
    PurchaseRequest,
    PurchaseRequestPriorityEnum,
    PurchaseRequestStatusEnum,
)
from app.models.service_order import ServiceOrder
from app.models.user import User


def test_purchase_request_model_fields_and_statuses(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Company.__table__,
                Branch.__table__,
                User.__table__,
                Customer.__table__,
                Device.__table__,
                ServiceOrder.__table__,
                CatalogPart.__table__,
                ProductCategory.__table__,
                VatRate.__table__,
                PurchaseRequest.__table__,
            ],
        )

        company = db.session.get(Company, int(app.config["TEST_COMPANY_ID"]))
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        branch = Branch(company_id=company.id, name="Oddział testowy", code="PR-1")
        db.session.add(branch)
        db.session.flush()

        customer = Customer(
            customer_type="PERSON",
            full_name="Jan Test",
            company_id=company.id,
            branch_id=branch.id,
        )
        db.session.add(customer)
        db.session.flush()

        device = Device(
            customer_id=customer.id,
            manufacturer="HP",
            model="LaserJet",
            serial_number="PR-0001",
            company_id=company.id,
            branch_id=branch.id,
        )
        db.session.add(device)
        db.session.flush()

        order = ServiceOrder(
            customer_id=customer.id,
            device_id=device.id,
            order_number="PR-100",
            status="RECEIVED",
            priority="HIGH",
            intake_date=date.today(),
            issue_description="Test",
            company_id=company.id,
            branch_id=branch.id,
        )
        db.session.add(order)

        category = ProductCategory(code="PR-CAT", name="Części", company_id=company.id, branch_id=branch.id)
        vat = VatRate(code="PR-23", rate=Decimal("23"), company_id=company.id, is_active=True)
        db.session.add_all([category, vat])
        db.session.flush()
        part = CatalogPart(
            code="PR-100",
            name="Część testowa",
            category_id=category.id,
            vat_id=vat.id,
            current_stock=0,
            purchase_price_net=Decimal("12.50"),
            sale_price_net=Decimal("20.00"),
            company_id=company.id,
            branch_id=branch.id,
        )
        db.session.add(part)
        db.session.flush()

        request_row = PurchaseRequest(
            service_order_id=order.id,
            part_id=part.id,
            quantity=Decimal("2"),
            status=PurchaseRequestStatusEnum.NEW.value,
            priority=PurchaseRequestPriorityEnum.URGENT.value,
            notes="Brak części",
            requested_by=user.id,
            company_id=company.id,
            branch_id=branch.id,
        )
        db.session.add(request_row)
        db.session.commit()

        assert request_row.id is not None
        assert request_row.status == PurchaseRequestStatusEnum.NEW.value
        assert request_row.priority == PurchaseRequestPriorityEnum.URGENT.value
        assert request_row.quantity == Decimal("2")
        assert request_row.requested_by == user.id
        assert request_row.created_at is not None
