"""Fail-closed allocation using existing relations; never reconcile legacy data."""
from decimal import Decimal

from sqlalchemy import inspect, select

from app.extensions import db
from app.models.catalog_part import InventoryItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.part_demand import PartDemand
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue
from app.models.stock_issue_item import StockIssueItem

from .exceptions import PartDemandValidationError


def _rows(model, *conditions):
    if not inspect(db.session.connection()).has_table(model.__tablename__):
        return []
    return list(db.session.scalars(select(model).where(*conditions)).all())


def context(demand):
    order = db.session.get(ServiceOrder, demand.service_order_id)
    product = db.session.get(InventoryItem, demand.inventory_item_id)
    if (order is None or not order.is_active or order.company_id != demand.company_id
            or order.branch_id != demand.branch_id or product is None or not product.is_active
            or product.company_id != demand.company_id
            or (order.branch_id is not None and product.branch_id not in {None, order.branch_id})):
        raise PartDemandValidationError("Niezgodna firma, oddział, zlecenie lub produkt zapotrzebowania. Wymagane uzgodnienie danych.")
    item = None
    if demand.service_order_item_id is not None:
        item = db.session.get(ServiceOrderItem, demand.service_order_item_id)
        if (item is None or not item.is_active or item.company_id != demand.company_id
                or item.branch_id != demand.branch_id or item.service_order_id != order.id
                or item.item_type != "PART" or item.item_id != product.id):
            raise PartDemandValidationError("Pozycja zapotrzebowania nie jest zgodna ze zleceniem, produktem, firmą, oddziałem lub typem. Wymagane uzgodnienie danych.")
    return order, product, item


def allocation(demand):
    """One demand, at most one matching item and one canonical hold.

    No MAX, product-only matching or inference that two tables are mirrors.
    Multiple holds/demands require an explicit allocation relation in the future.
    """
    order, product, item = context(demand)
    rivals = _rows(PartDemand, PartDemand.service_order_id == order.id,
        PartDemand.inventory_item_id == product.id, PartDemand.company_id == demand.company_id,
        PartDemand.is_active.is_(True), PartDemand.status != "CANCELLED")
    if any(row.id != demand.id for row in rivals):
        raise PartDemandValidationError("Niejednoznaczna alokacja: kilka zapotrzebowań dla zlecenia i produktu. Wymagane ręczne uzgodnienie.")
    items = _rows(ServiceOrderItem, ServiceOrderItem.service_order_id == order.id,
        ServiceOrderItem.item_id == product.id, ServiceOrderItem.item_type == "PART",
        ServiceOrderItem.company_id == demand.company_id, ServiceOrderItem.is_active.is_(True))
    if len(items) > 1 or (items and (item is None or items[0].id != item.id)):
        raise PartDemandValidationError("Niejednoznaczna alokacja pozycji zlecenia. Wskaż jednoznaczne powiązanie; dane nie zostały uzgodnione automatycznie.")
    holds = _rows(ServiceOrderPartReservation,
        ServiceOrderPartReservation.service_order_id == order.id,
        ServiceOrderPartReservation.part_id == product.id,
        ServiceOrderPartReservation.company_id == demand.company_id,
        ServiceOrderPartReservation.is_active.is_(True), ServiceOrderPartReservation.status == "RESERVED")
    legacy = _rows(InventoryReservation, InventoryReservation.service_order_id == order.id,
        InventoryReservation.inventory_item_id == product.id,
        InventoryReservation.company_id == demand.company_id,
        InventoryReservation.is_active.is_(True), InventoryReservation.status == "RESERVED")
    if legacy or len(holds) > 1 or any(h.branch_id != demand.branch_id for h in holds):
        raise PartDemandValidationError("Niejednoznaczna alokacja rezerwacji: starsze lub wielokrotne zapisy wymagają ręcznego uzgodnienia.")
    reserved = Decimal(holds[0].quantity) if holds else Decimal("0")
    if holds:
        old_movements = _rows(CatalogStockMovement,
            CatalogStockMovement.company_id == demand.company_id,
            CatalogStockMovement.part_id == product.id,
            CatalogStockMovement.reference_type == "SERVICE_ORDER",
            CatalogStockMovement.reference_id == str(order.id),
            CatalogStockMovement.movement_type == "RESERVATION",
            CatalogStockMovement.stock_before != CatalogStockMovement.stock_after)
        if old_movements:
            raise PartDemandValidationError("Historyczna rezerwacja zmieniała stan fizyczny. Wymagane ręczne uzgodnienie przed realizacją.")
    if item is not None and Decimal(item.reserved_quantity) != reserved:
        raise PartDemandValidationError("Ilość pozycji nie ma zgodnego potwierdzenia w rezerwacji magazynowej. Wymagane uzgodnienie.")
    used = Decimal("0")
    if inspect(db.session.connection()).has_table(StockIssueItem.__tablename__):
        lines = db.session.execute(select(StockIssueItem, StockIssue).join(StockIssue).where(
            StockIssue.service_order_id == order.id, StockIssue.company_id == demand.company_id,
            StockIssue.status == "POSTED", StockIssue.is_active.is_(True),
            StockIssueItem.inventory_item_id == product.id, StockIssueItem.is_active.is_(True))).all()
        for line, issue in lines:
            if (issue.branch_id != demand.branch_id or
                    (item is not None and line.service_order_item_id != item.id) or
                    (item is None and (line.service_order_item_id is not None or line.part_demand_id != demand.id)) or
                    (line.part_demand_id is not None and line.part_demand_id != demand.id)):
                raise PartDemandValidationError("Niejednoznaczna alokacja zużycia RW. Wymagane uzgodnienie.")
            used += Decimal(line.quantity_issued)
    if item is not None and Decimal(item.used_quantity) != used:
        raise PartDemandValidationError("Zużycie pozycji nie ma zgodnego potwierdzenia w zaksięgowanym RW.")
    return item, reserved, used


def missing(requested, reserved, used):
    return max(Decimal("0"), Decimal(requested) - reserved - used)


def validate_status(status, missing_quantity):
    if status == "DELIVERED" and missing_quantity > 0:
        raise PartDemandValidationError("Status Zaspokojone wymaga braku 0 potwierdzonego rezerwacją lub zużyciem RW; samo PZ nie wystarcza.")


def for_item(item):
    # Include foreign-company/wrong-order backlinks so they cannot be silently skipped.
    rows = _rows(PartDemand, PartDemand.service_order_item_id == item.id,
        PartDemand.is_active.is_(True), PartDemand.status != "CANCELLED")
    related = _rows(PartDemand, PartDemand.service_order_id == item.service_order_id,
        PartDemand.inventory_item_id == item.item_id, PartDemand.company_id == item.company_id,
        PartDemand.is_active.is_(True), PartDemand.status != "CANCELLED") if item.item_type == "PART" else []
    result = {row.id: row for row in rows + related}
    for row in result.values():
        allocation(row)
    return list(result.values())


def synchronize(demand, actor_id):
    _, reserved, used = allocation(demand)
    demand.reserved_quantity = reserved
    demand.missing_quantity = missing(demand.requested_quantity, reserved, used)
    # A formerly satisfied need becomes open again on release. Do not mark PZ
    # or ordinary sync as delivered automatically.
    if demand.status == "DELIVERED" and demand.missing_quantity > 0:
        demand.status = "TO_ORDER"
    validate_status(demand.status, demand.missing_quantity)
    demand.updated_by = actor_id