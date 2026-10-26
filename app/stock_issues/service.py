from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, inspect, or_, select, update
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import InventoryItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue, StockIssueStatusEnum
from app.models.stock_issue_item import StockIssueItem
from app.utils.contextual_search import contextual_search

from .exceptions import (
    StockIssueNotFoundError,
    StockIssuePermissionError,
    StockIssueValidationError,
)


class StockIssueService:
    def list_issues(self, *, company_id: int, branch_id: int | None, actor, issue_number=None, order_id=None, issued_by=None, date_from=None, date_to=None, status=None):
        self._assert_view(actor)
        query = select(StockIssue).options(selectinload(StockIssue.service_order), selectinload(StockIssue.issuer), selectinload(StockIssue.branch), selectinload(StockIssue.items).selectinload(StockIssueItem.inventory_item)).where(StockIssue.company_id == company_id, StockIssue.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(StockIssue.branch_id == branch_id, StockIssue.branch_id.is_(None)))
        if issue_number:
            query = query.where(contextual_search(StockIssue.issue_number, StockIssue.notes, query=issue_number))
        if order_id:
            query = query.where(StockIssue.service_order_id == order_id)
        if issued_by:
            query = query.where(StockIssue.issued_by == issued_by)
        if date_from:
            query = query.where(StockIssue.issue_date >= date_from)
        if date_to:
            query = query.where(StockIssue.issue_date <= date_to)
        if status:
            query = query.where(StockIssue.status == status)
        return list(db.session.scalars(query.order_by(StockIssue.issue_date.desc(), StockIssue.id.desc())).unique().all())

    def get_issue(self, *, issue_id: int, company_id: int, branch_id: int | None, actor) -> StockIssue:
        self._assert_view(actor)
        query = select(StockIssue).options(selectinload(StockIssue.service_order), selectinload(StockIssue.issuer), selectinload(StockIssue.branch), selectinload(StockIssue.items).selectinload(StockIssueItem.inventory_item), selectinload(StockIssue.items).selectinload(StockIssueItem.demand), selectinload(StockIssue.items).selectinload(StockIssueItem.reservation)).where(StockIssue.id == issue_id, StockIssue.company_id == company_id, StockIssue.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(StockIssue.branch_id == branch_id, StockIssue.branch_id.is_(None)))
        issue = db.session.scalar(query)
        if issue is None:
            raise StockIssueNotFoundError("Nie znaleziono dokumentu RW.")
        return issue

    def create_issue(self, *, items: list[dict[str, object]], company_id: int, branch_id: int | None, actor, service_order_id: int | None = None, notes: str | None = None, issue_date: date | None = None) -> StockIssue:
        try:
            return self._create_issue(items=items, company_id=company_id, branch_id=branch_id,
                actor=actor, service_order_id=service_order_id, notes=notes, issue_date=issue_date)
        except Exception:
            db.session.rollback()
            raise

    def _create_issue(self, *, items, company_id, branch_id, actor, service_order_id=None, notes=None, issue_date=None):
        self._assert_manage(actor)
        if not items:
            raise StockIssueValidationError("RW musi zawierać co najmniej jedną pozycję.")
        self._validate_order(service_order_id, company_id, branch_id, actor)
        issue = StockIssue(issue_number=self._next_number(company_id), issue_date=issue_date or date.today(), service_order_id=service_order_id, branch_id=branch_id, issued_by=getattr(actor, "id", None), status=StockIssueStatusEnum.DRAFT.value, notes=(notes or "").strip() or None, company_id=company_id, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None))
        db.session.add(issue)
        db.session.flush()
        for payload in items:
            self._add_item(issue=issue, payload=payload, company_id=company_id, branch_id=branch_id)
        db.session.commit()
        return issue

    def update_issue(self, *, issue_id: int, company_id: int, branch_id: int | None, actor, items: list[dict[str, object]] | None = None, service_order_id: int | None = None, notes: str | None = None, issue_date: date | None = None) -> StockIssue:
        self._assert_manage(actor)
        issue = self.get_issue(issue_id=issue_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if issue.status != StockIssueStatusEnum.DRAFT.value:
            raise StockIssueValidationError("Zaksięgowanego RW nie można edytować.")
        self._validate_order(service_order_id, company_id, branch_id, actor)
        if any(item.service_order_item_id for item in issue.items):
            raise StockIssueValidationError("RW rozliczenia pozycji zlecenia nie można edytować poza zleceniem.")
        issue.service_order_id = service_order_id
        issue.notes = (notes or "").strip() or None
        if issue_date is not None:
            issue.issue_date = issue_date
        if items is not None:
            issue.items.clear()
            db.session.flush()
            for payload in items:
                self._add_item(issue=issue, payload=payload, company_id=company_id, branch_id=branch_id)
        issue.updated_by = getattr(actor, "id", None)
        db.session.commit()
        return issue

    def post_issue(self, *, issue_id: int, company_id: int, branch_id: int | None, actor) -> StockIssue:
        self._assert_manage(actor)
        try:
            issue = self.get_issue(issue_id=issue_id, company_id=company_id, branch_id=branch_id, actor=actor)
            if issue.status == StockIssueStatusEnum.POSTED.value:
                return issue
            if issue.status == StockIssueStatusEnum.CANCELLED.value:
                raise StockIssueValidationError("Anulowanego RW nie można zaksięgować.")
            if not issue.items:
                raise StockIssueValidationError("RW nie ma pozycji.")
            from app.part_demands import consistency
            from app.part_demands.exceptions import PartDemandValidationError
            try:
                for line in issue.items:
                    if line.inventory_item_id and issue.service_order_id:
                        candidates = db.session.scalars(select(PartDemand).where(
                            PartDemand.service_order_id == issue.service_order_id,
                            PartDemand.inventory_item_id == line.inventory_item_id,
                            PartDemand.company_id == company_id,
                            PartDemand.is_active.is_(True), PartDemand.status != "CANCELLED")).all()
                        for demand in candidates:
                            consistency.allocation(demand)
                    if line.service_order_item_id:
                        linked_item = db.session.get(ServiceOrderItem, line.service_order_item_id)
                        if linked_item is not None:
                            consistency.for_item(linked_item)
                    if line.part_demand_id:
                        consistency.allocation(db.session.get(PartDemand, line.part_demand_id))
            except PartDemandValidationError as exc:
                raise StockIssueValidationError(str(exc)) from exc
            claimed = db.session.execute(update(StockIssue).where(StockIssue.id == issue.id,
                StockIssue.status == "DRAFT").values(status="POSTED")
                .execution_options(synchronize_session=False)).rowcount
            if claimed != 1:
                db.session.refresh(issue)
                if issue.status == "POSTED":
                    return issue
                raise StockIssueValidationError("RW nie jest roboczy.")
            self._validate_order(issue.service_order_id, company_id, branch_id, actor)
            from app.inventory.reservation_service import reserved_stock
            from app.orders.item_service import ServiceOrderItemService
            for item in sorted(issue.items, key=lambda row: (row.material_id is not None, row.inventory_item_id or row.material_id)):
                material = item.material_id is not None
                if material == (item.inventory_item_id is not None):
                    raise StockIssueValidationError("Pozycja RW musi wskazywać dokładnie jeden produkt.")
                model = CatalogMaterial if material else InventoryItem
                product_id = item.material_id if material else item.inventory_item_id
                product = db.session.scalar(select(model).where(model.id == product_id,
                    model.company_id == company_id, model.is_active.is_(True)).with_for_update()
                    .execution_options(populate_existing=True))
                if product is None:
                    raise StockIssueValidationError("Produkt RW nie istnieje lub jest nieaktywny.")
                if issue.branch_id is not None and product.branch_id not in {None, issue.branch_id}:
                    raise StockIssueValidationError("Produkt RW należy do innego oddziału.")
                quantity = self._quantity(item.quantity_issued, material=material)
                order_item = None
                if item.service_order_item_id:
                    order_item = db.session.scalar(select(ServiceOrderItem).where(
                        ServiceOrderItem.id == item.service_order_item_id,
                        ServiceOrderItem.company_id == company_id,
                        ServiceOrderItem.service_order_id == issue.service_order_id,
                        ServiceOrderItem.is_active.is_(True)).with_for_update().execution_options(populate_existing=True))
                    if (order_item is None or order_item.item_id != product_id or
                        order_item.item_type != ("MATERIAL" if material else "PART") or
                        order_item.version != item.settlement_version):
                        raise StockIssueValidationError("Pozycja zlecenia została zmieniona lub nie należy do RW.")
                reservation = None
                if item.reservation_id:
                    reservation = db.session.scalar(select(ServiceOrderPartReservation).where(
                        ServiceOrderPartReservation.id == item.reservation_id,
                        ServiceOrderPartReservation.company_id == company_id,
                        ServiceOrderPartReservation.service_order_id == issue.service_order_id,
                        ServiceOrderPartReservation.part_id == product_id,
                        ServiceOrderPartReservation.is_active.is_(True),
                        ServiceOrderPartReservation.status == "RESERVED").with_for_update().execution_options(populate_existing=True))
                    if reservation is None or quantity > Decimal(reservation.quantity):
                        raise StockIssueValidationError("Rezerwacja RW jest nieaktualna lub nie należy do zlecenia.")
                held = reserved_stock(item_type="MATERIAL" if material else "PART", item_id=product_id,
                    company_id=company_id)
                own_hold = Decimal(order_item.reserved_quantity) if order_item else (Decimal(reservation.quantity) if reservation else Decimal("0"))
                held = max(Decimal("0"), held - own_hold)
                before = Decimal(product.current_stock)
                if quantity > before - held:
                    raise StockIssueValidationError(f"Niewystarczająca dostępność {product.code}: stan {before}, rezerwacje innych {held}, brakuje {quantity - max(Decimal('0'), before - held)}.")
                after = before - quantity
                product.current_stock = after if material else int(after)
                db.session.add(CatalogStockMovement(item_type="MATERIAL" if material else "PART",
                    part_id=None if material else product_id, material_id=product_id if material else None,
                    movement_type="ISSUE", quantity=quantity, stock_before=before, stock_after=after,
                    reference_type="STOCK_ISSUE", reference_id=issue.issue_number,
                    note=f"Wydanie RW nr {issue.issue_number}", user_id=getattr(actor, "id", None),
                    service_order_id=issue.service_order_id, company_id=company_id, branch_id=issue.branch_id))
                if order_item is not None:
                    reserved = Decimal(order_item.reserved_quantity)
                    if not material:
                        ServiceOrderItemService.release_part_holds(order_item, reserved, getattr(actor, "id", None))
                    order_item.used_quantity += quantity
                    order_item.returned_quantity += max(Decimal("0"), reserved - quantity)
                    order_item.reserved_quantity = Decimal("0")
                    order_item.quantity = max(Decimal(order_item.quantity), Decimal(order_item.used_quantity) + Decimal(order_item.returned_quantity))
                    order_item.version += 1
                    order_item.updated_by = getattr(actor, "id", None)
                    released = max(Decimal("0"), reserved - quantity)
                    if released:
                        db.session.add(CatalogStockMovement(item_type=order_item.item_type,
                            part_id=None if material else product_id, material_id=product_id if material else None,
                            movement_type="RELEASE", quantity=released, stock_before=after, stock_after=after,
                            reference_type="STOCK_ISSUE", reference_id=issue.issue_number,
                            note="Zwolnienie niewykorzystanej rezerwacji przy rozliczeniu",
                            user_id=getattr(actor, "id", None), service_order_id=issue.service_order_id,
                            company_id=company_id, branch_id=issue.branch_id))
                    if not material:
                        db.session.flush()
                        try:
                            for demand in consistency.for_item(order_item):
                                consistency.synchronize(demand, getattr(actor, "id", None))
                        except PartDemandValidationError as exc:
                            raise StockIssueValidationError(str(exc)) from exc
                else:
                    self._settle_reservation_sql(item=item, actor=actor, service_order_id=issue.service_order_id, company_id=company_id)
                db.session.flush()
            issue.status = StockIssueStatusEnum.POSTED.value
            issue.updated_by = getattr(actor, "id", None)
            if inspect(db.session.connection()).has_table("audit_logs"):
                db.session.add(AuditLog(user_id=getattr(actor, "id", None), company_id=company_id, action="STOCK_ISSUE", object_type="StockIssue", object_id=str(issue.id), description=f"Zaksięgowano RW {issue.issue_number}", created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
            db.session.commit()
            return issue
        except Exception:
            db.session.rollback()
            raise

    def issue_reserved_parts(self, *, service_order_id: int, company_id: int, branch_id: int | None, actor, quantities: dict[int, Decimal] | None = None, notes: str | None = None) -> StockIssue:
        self._assert_manage(actor)
        query = select(ServiceOrderPartReservation).where(ServiceOrderPartReservation.service_order_id == service_order_id, ServiceOrderPartReservation.company_id == company_id, ServiceOrderPartReservation.is_active.is_(True), ServiceOrderPartReservation.status == "RESERVED")
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(ServiceOrderPartReservation.branch_id == branch_id, ServiceOrderPartReservation.branch_id.is_(None)))
        reservations = list(db.session.scalars(query).all())
        if not reservations:
            raise StockIssueValidationError("Brak aktywnych rezerwacji do wydania.")
        quantities = quantities or {}
        items = []
        for reservation in reservations:
            raw = quantities.get(reservation.id, reservation.quantity)
            if str(raw) in {"0", "0.0", "0.000"}:
                continue
            quantity = self._quantity(raw)
            items.append({"inventory_item_id": reservation.part_id, "quantity": quantity, "reservation_id": reservation.id})
        issue = self.create_issue(items=items, company_id=company_id, branch_id=branch_id, actor=actor, service_order_id=service_order_id, notes=notes)
        return self.post_issue(issue_id=issue.id, company_id=company_id, branch_id=branch_id, actor=actor)

    def _add_item(self, *, issue: StockIssue, payload: dict[str, object], company_id: int, branch_id: int | None) -> None:
        material = bool(payload.get("material_id"))
        item_id = self._positive_int(payload.get("material_id") if material else payload.get("inventory_item_id"), "produkt")
        quantity = self._quantity(payload.get("quantity"), material=material)
        model = CatalogMaterial if material else InventoryItem
        product = db.session.scalar(select(model).where(model.id == item_id, model.company_id == company_id, model.is_active.is_(True)))
        if product is None:
            raise StockIssueValidationError("Nieprawidłowy produkt.")
        order_item_id = payload.get("service_order_item_id")
        if order_item_id:
            order_item = db.session.scalar(select(ServiceOrderItem).where(ServiceOrderItem.id == int(order_item_id),
                ServiceOrderItem.company_id == company_id, ServiceOrderItem.service_order_id == issue.service_order_id,
                ServiceOrderItem.item_id == item_id, ServiceOrderItem.item_type == ("MATERIAL" if material else "PART"),
                ServiceOrderItem.is_active.is_(True)))
            if order_item is None or order_item.version != payload.get("settlement_version"):
                raise StockIssueValidationError("Nieprawidłowe powiązanie pozycji zlecenia.")
        demand_id = payload.get("part_demand_id") or None
        if demand_id is not None:
            demand = db.session.scalar(select(PartDemand).where(PartDemand.id == int(demand_id), PartDemand.company_id == company_id, PartDemand.inventory_item_id == item_id, PartDemand.is_active.is_(True)))
            if demand is None:
                raise StockIssueValidationError("Nieprawidłowe zapotrzebowanie.")
        reservation_id = payload.get("reservation_id") or None
        if reservation_id is not None:
            reservation = db.session.scalar(select(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == int(reservation_id), ServiceOrderPartReservation.company_id == company_id, ServiceOrderPartReservation.part_id == item_id, ServiceOrderPartReservation.status == "RESERVED", ServiceOrderPartReservation.is_active.is_(True)))
            if reservation is None or quantity > int(reservation.quantity) or reservation.service_order_id != issue.service_order_id:
                raise StockIssueValidationError("Nieprawidłowa rezerwacja RW.")
        if demand_id and demand.service_order_id != issue.service_order_id:
            raise StockIssueValidationError("Zapotrzebowanie nie należy do zlecenia RW.")
        db.session.add(StockIssueItem(stock_issue_id=issue.id, inventory_item_id=None if material else item_id,
            material_id=item_id if material else None, service_order_item_id=order_item_id,
            settlement_version=payload.get("settlement_version"), part_demand_id=int(demand_id) if demand_id else None,
            reservation_id=int(reservation_id) if reservation_id else None, quantity_issued=quantity,
            created_by=issue.created_by, updated_by=issue.updated_by))

    def _validate_order(self, order_id, company_id, branch_id, actor):
        if order_id is None:
            return
        query = select(ServiceOrder).where(ServiceOrder.id == order_id, ServiceOrder.company_id == company_id, ServiceOrder.is_active.is_(True))
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        if db.session.scalar(query) is None:
            raise StockIssueValidationError("Zlecenie RW nie istnieje w bieżącej firmie i oddziale.")

    def _quantity(self, value, *, material=False):
        try:
            quantity = Decimal(str(value))
        except Exception:
            raise StockIssueValidationError("Nieprawidłowa ilość RW.") from None
        if not quantity.is_finite() or quantity <= 0 or (not material and quantity != quantity.to_integral_value()) or quantity != quantity.quantize(Decimal("0.001")):
            raise StockIssueValidationError("Ilość RW musi być dodatnia; części wymagają ilości całkowitej, materiały do 3 miejsc po przecinku.")
        return quantity

    def _settle_reservation(self, *, item: StockIssueItem, actor, service_order_id: int | None, company_id: int) -> None:
        return self._settle_reservation_sql(item=item, actor=actor,
            service_order_id=service_order_id, company_id=company_id)

    def _settle_reservation_sql(self, *, item: StockIssueItem, actor, service_order_id: int | None, company_id: int) -> None:
        if item.reservation_id is None:
            return
        reservation = db.session.execute(select(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == item.reservation_id).with_for_update()).scalar_one_or_none()
        if reservation is None:
            return
        remaining = max(0, int(reservation.quantity) - int(item.quantity_issued))
        db.session.execute(update(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == reservation.id).values(quantity=remaining, status="RELEASED" if remaining == 0 else reservation.status, is_active=False if remaining == 0 else reservation.is_active, updated_by=getattr(actor, "id", None)))
        from app.models.inventory_reservation import InventoryReservation
        if inspect(db.session.connection()).has_table(InventoryReservation.__tablename__):
            left = Decimal(item.quantity_issued)
            mirrors = db.session.scalars(select(InventoryReservation).where(
                InventoryReservation.service_order_id == service_order_id,
                InventoryReservation.inventory_item_id == item.inventory_item_id,
                InventoryReservation.company_id == company_id,
                InventoryReservation.status == "RESERVED", InventoryReservation.is_active.is_(True)).with_for_update()).all()
            for mirror in mirrors:
                take = min(left, Decimal(mirror.quantity))
                mirror.quantity -= take
                left -= take
                if mirror.quantity == 0:
                    mirror.status = "CONSUMED"
                    mirror.is_active = False
                if left <= 0:
                    break
        if inspect(db.session.connection()).has_table(ServiceOrderItem.__tablename__):
            order_item = db.session.scalar(select(ServiceOrderItem).where(
                ServiceOrderItem.service_order_id == service_order_id,
                ServiceOrderItem.company_id == company_id, ServiceOrderItem.item_type == "PART",
                ServiceOrderItem.item_id == item.inventory_item_id,
                ServiceOrderItem.is_active.is_(True)).with_for_update())
            if order_item is not None:
                order_item.reserved_quantity = max(Decimal("0"), Decimal(order_item.reserved_quantity) - Decimal(item.quantity_issued))
                order_item.used_quantity += Decimal(item.quantity_issued)
                order_item.version += 1
                item.service_order_item_id = order_item.id
        demand = db.session.scalar(select(PartDemand).where(PartDemand.service_order_id == service_order_id, PartDemand.inventory_item_id == item.inventory_item_id, PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status != PartDemandStatusEnum.CANCELLED.value).order_by(PartDemand.created_at.asc(), PartDemand.id.asc())) if service_order_id is not None else None
        if demand is not None:
            from app.part_demands import consistency
            from app.part_demands.exceptions import PartDemandValidationError
            item.part_demand_id = demand.id
            db.session.flush()
            db.session.expire(reservation)
            try:
                consistency.synchronize(demand, getattr(actor, "id", None))
            except PartDemandValidationError as exc:
                raise StockIssueValidationError(str(exc)) from exc

    def _positive_int(self, value, label: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise StockIssueValidationError(f"Nieprawidłowa wartość pola: {label}.") from exc
        if result <= 0:
            raise StockIssueValidationError(f"Pole {label} musi być większe od zera.")
        if str(value).strip() not in {str(result), f"{result}.0", f"{result}.00"}:
            raise StockIssueValidationError(f"Pole {label} musi być liczbą całkowitą.")
        return result

    def _next_number(self, company_id: int) -> str:
        year = date.today().year
        prefix = f"RW/{year}/"
        count = db.session.scalar(select(func.count(StockIssue.id)).where(StockIssue.company_id == company_id, StockIssue.issue_number.like(f"{prefix}%"))) or 0
        return f"{prefix}{int(count) + 1:06d}"

    def _names(self, actor): return {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
    def _is_admin(self, actor): return "administrator" in self._names(actor)
    def _is_manager(self, actor): return "kierownik" in self._names(actor)
    def _is_warehouse(self, actor): return bool(self._names(actor) & {"magazyn", "magazynier", "zakupy", "warehouse"})
    def _assert_view(self, actor):
        if not (self._is_admin(actor) or self._is_manager(actor) or self._is_warehouse(actor) or bool(self._names(actor) & {"mechanik", "technik", "technician"})):
            raise StockIssuePermissionError("Brak uprawnień do podglądu wydań RW.")
    def _assert_manage(self, actor):
        if not (self._is_admin(actor) or self._is_warehouse(actor)):
            raise StockIssuePermissionError("Tylko magazynier może wydawać produkty.")


stock_issue_service = StockIssueService()
