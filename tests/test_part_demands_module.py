from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.catalog.service import CatalogService
from app.extensions import db
from app.models.branch import Branch
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.customer import Customer
from app.models.device import Device
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.role import Role
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_item import ServiceOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.user import User
from app.models.user_role import UserRole
from app.part_demands.exceptions import PartDemandPermissionError
from app.part_demands.service import PartDemandService


@pytest.fixture()
def part_demand_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Branch.__table__,
                Role.__table__,
                UserRole.__table__,
                Customer.__table__,
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceOrderItem.__table__,
                CatalogPart.__table__,
                CatalogStockMovement.__table__,
                ServiceOrderPartReservation.__table__,
                PartDemand.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                PartDemand.__table__,
                ServiceOrderPartReservation.__table__,
                CatalogStockMovement.__table__,
                CatalogPart.__table__,
                ServiceOrderItem.__table__,
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                Customer.__table__,
                UserRole.__table__,
                Role.__table__,
                Branch.__table__,
            ],
        )


def _create_branch(company_id: int, code: str) -> Branch:
    branch = Branch(company_id=company_id, name=f"Oddział {code}", code=code)
    db.session.add(branch)
    db.session.commit()
    return branch


def _assign_role(*, company_id: int, branch_id: int | None, user_id: int, role_name: str) -> None:
    role = Role(company_id=company_id, branch_id=branch_id, name=role_name)
    db.session.add(role)
    db.session.flush()
    db.session.add(UserRole(company_id=company_id, branch_id=branch_id, user_id=user_id, role_id=role.id))
    db.session.commit()


def _create_user(*, company_id: int, branch_id: int | None, login: str) -> User:
    user = User(login=login, password_hash="x", company_id=company_id, branch_id=branch_id)
    db.session.add(user)
    db.session.commit()
    return user


def _create_order_and_part(*, company_id: int, branch_id: int, order_number: str, stock: str = "0") -> tuple[ServiceOrder, CatalogPart]:
    customer = Customer(customer_type="PERSON", full_name=f"Klient {order_number}", company_id=company_id, branch_id=branch_id)
    db.session.add(customer)
    db.session.flush()

    device = Device(customer_id=customer.id, manufacturer="HP", model="LaserJet", serial_number=f"SN-{order_number}", company_id=company_id, branch_id=branch_id)
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number=order_number,
        status="RECEIVED",
        priority="HIGH",
        intake_date=date.today(),
        issue_description="Test",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)

    part = CatalogPart(
        code=f"PART-{order_number}",
        name="Toner HP 26A",
        unit="szt.",
        current_stock=Decimal(stock),
        minimum_stock=Decimal("0"),
        purchase_price_net=Decimal("100"),
        sale_price_net=Decimal("150"),
        vat_rate=Decimal("23"),
        is_reservable=True,
        is_sellable=True,
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(part)
    db.session.commit()
    return order, part


def test_shortage_creates_part_demand_on_reservation(app, part_demand_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None

        branch = _create_branch(company_id, "PD-A")
        user.branch_id = branch.id
        db.session.commit()

        order, part = _create_order_and_part(company_id=company_id, branch_id=branch.id, order_number="SO-PD-001", stock="2")

        result = CatalogService().reserve_part_for_order(
            order_id=order.id,
            part_id=part.id,
            quantity=Decimal("5"),
            user_id=user.id,
            company_id=company_id,
            branch_id=branch.id,
        )

        assert result.demand_created is True
        demand = db.session.get(PartDemand, result.demand_id)
        assert demand is not None
        assert Decimal(demand.requested_quantity) == Decimal("5.000")
        assert Decimal(demand.missing_quantity) == Decimal("3.000")
        assert demand.status == PartDemandStatusEnum.TO_ORDER.value


def test_reservation_with_stock_does_not_create_demand(app, part_demand_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None

        branch = _create_branch(company_id, "PD-B")
        user.branch_id = branch.id
        db.session.commit()

        order, part = _create_order_and_part(company_id=company_id, branch_id=branch.id, order_number="SO-PD-002", stock="10")

        result = CatalogService().reserve_part_for_order(
            order_id=order.id,
            part_id=part.id,
            quantity=Decimal("2"),
            user_id=user.id,
            company_id=company_id,
            branch_id=branch.id,
        )

        assert result.demand_created is False
        reservations = db.session.query(ServiceOrderPartReservation).filter_by(service_order_id=order.id).all()
        assert len(reservations) == 1
        assert Decimal(reservations[0].quantity) == Decimal("2.000")


def test_part_demand_crud_grouping_filtering_and_scope(app, part_demand_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        admin = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert admin is not None

        branch_a = _create_branch(company_id, "PD-C1")
        branch_b = _create_branch(company_id, "PD-C2")
        admin.branch_id = branch_a.id
        db.session.commit()
        _assign_role(company_id=company_id, branch_id=branch_a.id, user_id=admin.id, role_name="Administrator")

        order_a, part_a = _create_order_and_part(company_id=company_id, branch_id=branch_a.id, order_number="SO-PD-101")
        part_a.branch_id = None
        db.session.add(part_a)
        db.session.commit()
        order_b, _ = _create_order_and_part(company_id=company_id, branch_id=branch_b.id, order_number="SO-PD-102")

        service = PartDemandService()
        created = service.create_demand(
            data={
                "service_order_id": order_a.id,
                "service_order_item_id": None,
                "inventory_item_id": part_a.id,
                "requested_quantity": "12",
                "reserved_quantity": "0",
                "missing_quantity": "12",
                "status": "NEW",
                "priority": "HIGH",
                "expected_date": date.today(),
                "notes": "Brak tonera",
            },
            company_id=company_id,
            branch_scope_id=branch_a.id,
            actor=admin,
        )

        service.create_demand(
            data={
                "service_order_id": order_b.id,
                "service_order_item_id": None,
                "inventory_item_id": part_a.id,
                "requested_quantity": "3",
                "reserved_quantity": "0",
                "missing_quantity": "3",
                "status": "TO_ORDER",
                "priority": "NORMAL",
                "expected_date": date.today(),
                "notes": "Drugi oddział",
            },
            company_id=company_id,
            branch_scope_id=branch_b.id,
            actor=admin,
        )

        rows = service.list_demands(
            company_id=company_id,
            actor=admin,
            branch_scope_id=branch_a.id,
            status="NEW",
            priority="HIGH",
            branch_filter_id=branch_a.id,
            order_id=order_a.id,
            inventory_item_id=part_a.id,
            expected_date_from=date.today(),
            expected_date_to=date.today(),
            query_text="SO-PD-101",
        )
        assert len(rows) == 1
        assert rows[0].id == created.id

        grouped = service.list_grouped(
            company_id=company_id,
            actor=admin,
            branch_scope_id=None,
            status=None,
            priority=None,
            branch_filter_id=None,
            expected_date_from=None,
            expected_date_to=None,
        )
        assert len(grouped) == 1
        assert grouped[0].part_name == "Toner HP 26A"
        assert grouped[0].total_missing == Decimal("15.000")
        assert "SO-PD-101" in grouped[0].order_numbers
        assert "SO-PD-102" in grouped[0].order_numbers

        updated = service.update_demand(
            demand_id=created.id,
            data={
                "service_order_id": order_a.id,
                "service_order_item_id": None,
                "inventory_item_id": part_a.id,
                "requested_quantity": "12",
                "reserved_quantity": "2",
                "missing_quantity": "10",
                "status": "IN_PURCHASE",
                "priority": "URGENT",
                "expected_date": date.today(),
                "notes": "W realizacji",
            },
            company_id=company_id,
            branch_scope_id=branch_a.id,
            actor=admin,
        )
        assert updated.status == "IN_PURCHASE"

        service.delete_demand(demand_id=created.id, company_id=company_id, branch_scope_id=branch_a.id, actor=admin)
        deleted = db.session.get(PartDemand, created.id)
        assert deleted is not None
        assert deleted.is_active is False


def test_fulfill_demand_and_permissions(app, part_demand_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        admin = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert admin is not None

        branch = _create_branch(company_id, "PD-D")
        admin.branch_id = branch.id
        db.session.commit()
        _assign_role(company_id=company_id, branch_id=branch.id, user_id=admin.id, role_name="Administrator")

        technician = _create_user(company_id=company_id, branch_id=branch.id, login="tech-pd")
        _assign_role(company_id=company_id, branch_id=branch.id, user_id=technician.id, role_name="Technik")

        order, part = _create_order_and_part(company_id=company_id, branch_id=branch.id, order_number="SO-PD-301", stock="5")

        demand_service = PartDemandService()
        demand = demand_service.create_demand(
            data={
                "service_order_id": order.id,
                "service_order_item_id": None,
                "inventory_item_id": part.id,
                "requested_quantity": "2",
                "reserved_quantity": "0",
                "missing_quantity": "2",
                "status": "ORDERED",
                "priority": "HIGH",
                "expected_date": date.today(),
                "notes": "Po dostawie",
            },
            company_id=company_id,
            branch_scope_id=branch.id,
            actor=admin,
        )

        fulfilled = demand_service.fulfill_demand(
            demand_id=demand.id,
            reserve_quantity=Decimal("2"),
            company_id=company_id,
            branch_scope_id=branch.id,
            actor=admin,
        )
        assert fulfilled.status == PartDemandStatusEnum.DELIVERED.value
        assert Decimal(fulfilled.missing_quantity) == Decimal("0")

        reservations = db.session.query(ServiceOrderPartReservation).filter_by(service_order_id=order.id).all()
        assert len(reservations) == 1
        assert Decimal(reservations[0].quantity) == Decimal("2.000")

        with pytest.raises(PartDemandPermissionError):
            demand_service.list_demands(
                company_id=company_id,
                actor=technician,
                branch_scope_id=branch.id,
                status=None,
                priority=None,
                branch_filter_id=None,
                order_id=None,
                inventory_item_id=None,
                expected_date_from=None,
                expected_date_to=None,
                query_text=None,
            )
