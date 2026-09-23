from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, inspect, or_, select, update
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_part import InventoryItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue, StockIssueStatusEnum
from app.models.stock_issue_item import StockIssueItem

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
            query = query.where(StockIssue.issue_number.ilike(f"%{issue_number.strip()}%"))
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
        self._assert_manage(actor)
        if not items:
            raise StockIssueValidationError("RW musi zawierać co najmniej jedną pozycję.")
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
            target_stocks: list[tuple[int, int]] = []
            for item in issue.items:
                product = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item.inventory_item_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)).with_for_update())
                if product is None:
                    raise StockIssueValidationError("Produkt RW nie istnieje lub jest nieaktywny.")
                quantity = int(item.quantity_issued)
                if quantity <= 0:
                    raise StockIssueValidationError("Ilość RW musi być większa od zera.")
                if int(product.current_stock) < quantity:
                    raise StockIssueValidationError(f"Niewystarczający stan produktu {product.code}.")
            for item in issue.items:
                product = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item.inventory_item_id).with_for_update())
                if product is None:
                    raise StockIssueValidationError("Produkt RW nie istnieje.")
                before = int(product.current_stock)
                after = before - int(item.quantity_issued)
                target_stocks.append((product.id, after))
                db.session.add(CatalogStockMovement(item_type="PART", part_id=product.id, movement_type="ISSUE", quantity=Decimal(item.quantity_issued), stock_before=Decimal(before), stock_after=Decimal(after), reference_type="STOCK_ISSUE", reference_id=issue.issue_number, note=f"Wydanie RW nr {issue.issue_number}", user_id=getattr(actor, "id", None), service_order_id=issue.service_order_id, company_id=company_id, branch_id=branch_id))
            issue.status = StockIssueStatusEnum.POSTED.value
            issue.updated_by = getattr(actor, "id", None)
            if inspect(db.engine).has_table("audit_logs"):
                db.session.add(AuditLog(user_id=getattr(actor, "id", None), company_id=company_id, action="STOCK_ISSUE", object_type="StockIssue", object_id=str(issue.id), description=f"Zaksięgowano RW {issue.issue_number}", created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
            db.session.flush()
            for item in issue.items:
                self._settle_reservation_sql(item=item, actor=actor, service_order_id=issue.service_order_id, company_id=company_id)
            for product_id, target_stock in target_stocks:
                db.session.execute(update(InventoryItem).where(InventoryItem.id == product_id).values(current_stock=target_stock))
            db.session.expire_all()
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
        items = [{"inventory_item_id": reservation.part_id, "quantity": int(quantities.get(reservation.id, reservation.quantity)), "reservation_id": reservation.id} for reservation in reservations if int(quantities.get(reservation.id, reservation.quantity)) > 0]
        issue = self.create_issue(items=items, company_id=company_id, branch_id=branch_id, actor=actor, service_order_id=service_order_id, notes=notes)
        return self.post_issue(issue_id=issue.id, company_id=company_id, branch_id=branch_id, actor=actor)

    def _add_item(self, *, issue: StockIssue, payload: dict[str, object], company_id: int, branch_id: int | None) -> None:
        item_id = self._positive_int(payload.get("inventory_item_id"), "produkt")
        quantity = self._positive_int(payload.get("quantity"), "ilość")
        product = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)))
        if product is None:
            raise StockIssueValidationError("Nieprawidłowy produkt.")
        demand_id = payload.get("part_demand_id") or None
        if demand_id is not None:
            demand = db.session.scalar(select(PartDemand).where(PartDemand.id == int(demand_id), PartDemand.company_id == company_id, PartDemand.inventory_item_id == item_id, PartDemand.is_active.is_(True)))
            if demand is None:
                raise StockIssueValidationError("Nieprawidłowe zapotrzebowanie.")
        reservation_id = payload.get("reservation_id") or None
        if reservation_id is not None:
            reservation = db.session.scalar(select(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == int(reservation_id), ServiceOrderPartReservation.company_id == company_id, ServiceOrderPartReservation.part_id == item_id, ServiceOrderPartReservation.status == "RESERVED", ServiceOrderPartReservation.is_active.is_(True)))
            if reservation is None or quantity > int(reservation.quantity):
                raise StockIssueValidationError("Nieprawidłowa rezerwacja RW.")
        db.session.add(StockIssueItem(stock_issue_id=issue.id, inventory_item_id=item_id, part_demand_id=int(demand_id) if demand_id else None, reservation_id=int(reservation_id) if reservation_id else None, quantity_issued=quantity, created_by=issue.created_by, updated_by=issue.updated_by))

    def _settle_reservation(self, *, item: StockIssueItem, actor, service_order_id: int | None, company_id: int) -> None:
        if item.reservation is None:
            return
        reservation = item.reservation
        remaining = int(reservation.quantity) - int(item.quantity_issued)
        if remaining <= 0:
            reservation.quantity = 0
            reservation.status = "RELEASED"
            reservation.is_active = False
        else:
            reservation.quantity = remaining
        reservation.updated_by = getattr(actor, "id", None)
        demand = item.demand
        if demand is None and service_order_id is not None:
            demand = db.session.scalar(select(PartDemand).where(PartDemand.service_order_id == service_order_id, PartDemand.inventory_item_id == item.inventory_item_id, PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status != PartDemandStatusEnum.CANCELLED.value).order_by(PartDemand.created_at.asc(), PartDemand.id.asc()))
        if demand is not None:
            demand.reserved_quantity = max(Decimal("0"), Decimal(remaining))
            demand.missing_quantity = max(Decimal("0"), Decimal(demand.requested_quantity) - Decimal(demand.reserved_quantity))
            demand.updated_by = getattr(actor, "id", None)

    def _settle_reservation_sql(self, *, item: StockIssueItem, actor, service_order_id: int | None, company_id: int) -> None:
        if item.reservation_id is None:
            return
        reservation = db.session.execute(select(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == item.reservation_id).with_for_update()).scalar_one_or_none()
        if reservation is None:
            return
        remaining = max(0, int(reservation.quantity) - int(item.quantity_issued))
        db.session.execute(update(ServiceOrderPartReservation).where(ServiceOrderPartReservation.id == reservation.id).values(quantity=remaining, status="RELEASED" if remaining == 0 else reservation.status, is_active=False if remaining == 0 else reservation.is_active, updated_by=getattr(actor, "id", None)))
        demand = db.session.scalar(select(PartDemand).where(PartDemand.service_order_id == service_order_id, PartDemand.inventory_item_id == item.inventory_item_id, PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status != PartDemandStatusEnum.CANCELLED.value).order_by(PartDemand.created_at.asc(), PartDemand.id.asc())) if service_order_id is not None else None
        if demand is not None:
            reserved = Decimal(remaining)
            db.session.execute(update(PartDemand).where(PartDemand.id == demand.id).values(reserved_quantity=reserved, missing_quantity=max(Decimal("0"), Decimal(demand.requested_quantity) - reserved), updated_by=getattr(actor, "id", None)))

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
