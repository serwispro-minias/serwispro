from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_part import CatalogPart
from app.models.catalog_supplier import CatalogSupplier
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_history import PurchaseOrderHistory
from app.models.purchase_order_item import PurchaseOrderItem

from .exceptions import PurchaseOrderNotFoundError, PurchaseOrderPermissionError, PurchaseOrderValidationError


class PurchaseOrderService:
    _STATUS_TRANSITIONS = {
        PurchaseOrderStatusEnum.DRAFT.value: {PurchaseOrderStatusEnum.SENT.value, PurchaseOrderStatusEnum.CANCELLED.value},
        PurchaseOrderStatusEnum.SENT.value: {PurchaseOrderStatusEnum.CONFIRMED.value, PurchaseOrderStatusEnum.CANCELLED.value},
        PurchaseOrderStatusEnum.CONFIRMED.value: {PurchaseOrderStatusEnum.PARTIAL.value, PurchaseOrderStatusEnum.COMPLETED.value, PurchaseOrderStatusEnum.CANCELLED.value},
        PurchaseOrderStatusEnum.PARTIAL.value: {PurchaseOrderStatusEnum.PARTIAL.value, PurchaseOrderStatusEnum.COMPLETED.value, PurchaseOrderStatusEnum.CANCELLED.value},
        PurchaseOrderStatusEnum.COMPLETED.value: set(),
        PurchaseOrderStatusEnum.CANCELLED.value: set(),
    }

    def list_orders(self, *, company_id: int, branch_id: int | None, actor, status=None, supplier_id=None, date_from=None, date_to=None, po_number=None, part_id=None, created_by=None):
        self._assert_view(actor)
        query = select(PurchaseOrder).options(selectinload(PurchaseOrder.supplier), selectinload(PurchaseOrder.items)).where(PurchaseOrder.company_id == company_id).where(PurchaseOrder.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(PurchaseOrder.branch_id == branch_id, PurchaseOrder.branch_id.is_(None)))
        if status:
            query = query.where(PurchaseOrder.status == status)
        if supplier_id:
            query = query.where(PurchaseOrder.supplier_id == supplier_id)
        if date_from:
            query = query.where(PurchaseOrder.order_date >= date_from)
        if date_to:
            query = query.where(PurchaseOrder.order_date <= date_to)
        if po_number:
            query = query.where(PurchaseOrder.po_number.ilike(f"%{po_number.strip()}%"))
        if created_by:
            query = query.where(PurchaseOrder.created_by == created_by)
        if part_id:
            query = query.join(PurchaseOrderItem).where(PurchaseOrderItem.part_id == part_id)
        return list(db.session.scalars(query.order_by(PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc())).unique().all())

    def get_order(self, *, order_id: int, company_id: int, branch_id: int | None, actor) -> PurchaseOrder:
        self._assert_view(actor)
        query = select(PurchaseOrder).options(selectinload(PurchaseOrder.supplier), selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.part), selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.demand_links).selectinload(PurchaseOrderDemandLink.demand), selectinload(PurchaseOrder.history)).where(PurchaseOrder.id == order_id, PurchaseOrder.company_id == company_id, PurchaseOrder.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(PurchaseOrder.branch_id == branch_id, PurchaseOrder.branch_id.is_(None)))
        row = db.session.scalar(query)
        if row is None:
            raise PurchaseOrderNotFoundError("Nie znaleziono zamówienia.")
        return row

    def create_from_demands(self, *, demand_ids: list[int], supplier_id: int, company_id: int, branch_id: int | None, actor, order_date: date | None = None, expected_delivery_date: date | None = None, notes: str | None = None) -> PurchaseOrder:
        self._assert_manage(actor)
        if not demand_ids:
            raise PurchaseOrderValidationError("Wybierz co najmniej jedno zapotrzebowanie.")
        supplier = db.session.scalar(select(CatalogSupplier).where(CatalogSupplier.id == supplier_id, CatalogSupplier.company_id == company_id, CatalogSupplier.is_active.is_(True), CatalogSupplier.is_supplier_active.is_(True)))
        if supplier is None:
            raise PurchaseOrderValidationError("Nie znaleziono aktywnego dostawcy.")
        query = select(PartDemand).options(selectinload(PartDemand.inventory_item)).where(PartDemand.id.in_(demand_ids), PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status.in_([PartDemandStatusEnum.NEW.value, PartDemandStatusEnum.TO_ORDER.value, PartDemandStatusEnum.IN_PURCHASE.value]))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(PartDemand.branch_id == branch_id)
        demands = list(db.session.scalars(query).all())
        if len(demands) != len(set(demand_ids)):
            raise PurchaseOrderValidationError("Niektóre zapotrzebowania są niedostępne lub już zamknięte.")
        if any(d.inventory_item is None or d.inventory_item.supplier_id != supplier.id for d in demands):
            raise PurchaseOrderValidationError("Wszystkie wybrane części muszą należeć do wybranego dostawcy.")

        po = PurchaseOrder(po_number=self._next_number(company_id), supplier_id=supplier.id, status=PurchaseOrderStatusEnum.DRAFT.value, order_date=order_date or date.today(), expected_delivery_date=expected_delivery_date, notes=(notes or "").strip() or None, company_id=company_id, branch_id=branch_id, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None))
        db.session.add(po)
        db.session.flush()
        groups: dict[int, list[PartDemand]] = {}
        for demand in demands:
            groups.setdefault(demand.inventory_item_id, []).append(demand)
        for part_id, grouped in groups.items():
            part = grouped[0].inventory_item
            quantity = sum((Decimal(d.missing_quantity) for d in grouped), Decimal("0"))
            if quantity <= 0:
                continue
            price = Decimal(part.purchase_price_net or 0)
            vat = Decimal(part.vat_rate or 0)
            total_net = (quantity * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_vat = (total_net * vat / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            item = PurchaseOrderItem(purchase_order_id=po.id, part_id=part.id, code_snapshot=part.code, manufacturer_snapshot=part.manufacturer.name if getattr(part, "manufacturer", None) else None, quantity_ordered=quantity, unit=part.unit, unit_price_net=price, vat_rate=vat, total_net=total_net, total_vat=total_vat, total_gross=total_net + total_vat, expected_delivery_date=expected_delivery_date, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None))
            db.session.add(item)
            db.session.flush()
            for demand in grouped:
                db.session.add(PurchaseOrderDemandLink(purchase_order_item_id=item.id, part_demand_id=demand.id, allocated_quantity=Decimal(demand.missing_quantity), created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
                demand.status = PartDemandStatusEnum.IN_PURCHASE.value
            po.total_net += total_net
            po.total_vat += total_vat
            po.total_gross += total_net + total_vat
        self._history(po, "CREATED", None, po.status, "Utworzono zamówienie z zapotrzebowań", actor)
        db.session.commit()
        return po

    def preferred_supplier_suggestions(self, *, demand_ids: list[int], company_id: int, branch_id: int | None) -> dict[str, object]:
        query = select(PartDemand.inventory_item_id, CatalogPart.preferred_supplier_id, CatalogPart.code, CatalogPart.name).join(CatalogPart, CatalogPart.id == PartDemand.inventory_item_id).where(PartDemand.id.in_(demand_ids), PartDemand.company_id == company_id, PartDemand.is_active.is_(True))
        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        rows = db.session.execute(query).all()
        groups: dict[int, list[dict[str, object]]] = {}
        for _, supplier_id, code, name in rows:
            if supplier_id is not None:
                groups.setdefault(int(supplier_id), []).append({"code": code, "name": name})
        return {"supplier_ids": sorted(groups), "groups": groups, "single_supplier_id": next(iter(groups)) if len(groups) == 1 else None}

    def update_order(self, *, order_id: int, supplier_id: int, order_date: date, expected_delivery_date: date | None, notes: str | None, company_id: int, branch_id: int | None, actor) -> PurchaseOrder:
        self._assert_manage(actor)
        po = self.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if po.status not in {PurchaseOrderStatusEnum.DRAFT.value, PurchaseOrderStatusEnum.SENT.value}:
            raise PurchaseOrderValidationError("Tego zamówienia nie można już edytować.")
        supplier = db.session.scalar(select(CatalogSupplier).where(CatalogSupplier.id == supplier_id, CatalogSupplier.company_id == company_id, CatalogSupplier.is_active.is_(True), CatalogSupplier.is_supplier_active.is_(True)))
        if supplier is None:
            raise PurchaseOrderValidationError("Nie znaleziono aktywnego dostawcy.")
        po.supplier_id = supplier.id
        po.order_date = order_date
        po.expected_delivery_date = expected_delivery_date
        po.notes = (notes or "").strip() or None
        po.updated_by = getattr(actor, "id", None)
        self._history(po, "EDITED", po.status, po.status, "Edytowano zamówienie", actor)
        db.session.commit()
        return po

    def update_status(self, *, order_id: int, status: str, company_id: int, branch_id: int | None, actor) -> PurchaseOrder:
        normalized = str(status or "").upper()
        if normalized not in {value for value, _ in [(item.value, item.name) for item in PurchaseOrderStatusEnum]}:
            raise PurchaseOrderValidationError("Nieprawidłowy status zamówienia.")
        po = self.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if normalized != po.status and normalized not in self._STATUS_TRANSITIONS.get(po.status, set()):
            raise PurchaseOrderValidationError(f"Niedozwolona zmiana statusu: {po.status} -> {normalized}.")
        if normalized in {PurchaseOrderStatusEnum.CONFIRMED.value, PurchaseOrderStatusEnum.CANCELLED.value}:
            self._assert_approve(actor)
        else:
            self._assert_manage(actor)
        old = po.status
        po.status = normalized
        po.updated_by = getattr(actor, "id", None)
        self._history(po, "STATUS_CHANGED", old, normalized, f"Zmieniono status: {old} -> {normalized}", actor)
        db.session.commit()
        return po

    def _next_number(self, company_id: int) -> str:
        year = date.today().year
        prefix = f"PO/{year}/"
        count = db.session.scalar(select(func.count(PurchaseOrder.id)).where(PurchaseOrder.company_id == company_id, PurchaseOrder.po_number.like(f"{prefix}%"))) or 0
        return f"{prefix}{int(count) + 1:06d}"

    def _history(self, po, event_type, old_status, new_status, description, actor):
        po.history.append(PurchaseOrderHistory(event_type=event_type, old_status=old_status, new_status=new_status, description=description, changed_by=getattr(actor, "id", None), created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))

    def _assert_view(self, actor):
        if not (self._is_admin(actor) or self._is_purchase(actor) or self._is_mechanic(actor) or self._is_manager(actor)):
            raise PurchaseOrderPermissionError("Brak uprawnień do podglądu zamówień.")

    def _assert_manage(self, actor):
        if not (self._is_admin(actor) or self._is_purchase(actor)):
            raise PurchaseOrderPermissionError("Tylko magazynier lub zakupy mogą zarządzać zamówieniami.")

    def _assert_approve(self, actor):
        if not (self._is_admin(actor) or self._is_manager(actor)):
            raise PurchaseOrderPermissionError("Tylko kierownik lub administrator może zatwierdzać i anulować zamówienia.")

    def _names(self, actor):
        return {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}

    def _is_admin(self, actor): return "administrator" in self._names(actor)
    def _is_manager(self, actor): return "kierownik" in self._names(actor)
    def _is_purchase(self, actor): return bool(self._names(actor) & {"zakupy", "magazyn", "magazynier", "zakupowiec", "warehouse", "purchase"})
    def _is_mechanic(self, actor): return bool(self._names(actor) & {"mechanik", "technik", "technician", "repairman"})


purchase_order_service = PurchaseOrderService()