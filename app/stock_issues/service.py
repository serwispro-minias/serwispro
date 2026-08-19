from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue, StockIssueStatusEnum
from app.models.stock_issue_item import StockIssueItem

from .exceptions import StockIssueNotFoundError, StockIssuePermissionError, StockIssueValidationError


class StockIssueService:
    def list_issues(self, *, company_id: int, branch_id: int | None, actor, issue_number=None, order_id=None, issued_by=None, date_from=None, date_to=None, status=None):
        self._assert_view(actor)
        query = select(StockIssue).options(selectinload(StockIssue.service_order), selectinload(StockIssue.issuer), selectinload(StockIssue.branch), selectinload(StockIssue.items)).where(StockIssue.company_id == company_id, StockIssue.is_active.is_(True))
        # A document with no branch_id (created outside a branch scope) must stay visible to all branches.
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
        query = query.order_by(StockIssue.issue_date.desc(), StockIssue.id.desc())
        return list(db.session.scalars(query).unique().all())

    def get_issue(self, *, issue_id: int, company_id: int, branch_id: int | None, actor) -> StockIssue:
        self._assert_view(actor)
        query = select(StockIssue).options(selectinload(StockIssue.service_order), selectinload(StockIssue.issuer), selectinload(StockIssue.branch), selectinload(StockIssue.items).selectinload(StockIssueItem.part), selectinload(StockIssue.items).selectinload(StockIssueItem.demand), selectinload(StockIssue.items).selectinload(StockIssueItem.reservation)).where(StockIssue.id == issue_id, StockIssue.company_id == company_id, StockIssue.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(StockIssue.branch_id == branch_id, StockIssue.branch_id.is_(None)))
        issue = db.session.scalar(query)
        if issue is None:
            raise StockIssueNotFoundError("Nie znaleziono dokumentu RW.")
        return issue

    def issue_reserved_parts(self, *, service_order_id: int, company_id: int, branch_id: int | None, actor, quantities: dict[int, Decimal] | None = None, notes: str | None = None) -> StockIssue:
        self._assert_manage(actor)
        reservation_query = select(ServiceOrderPartReservation).options(selectinload(ServiceOrderPartReservation.part)).where(ServiceOrderPartReservation.service_order_id == service_order_id, ServiceOrderPartReservation.company_id == company_id, ServiceOrderPartReservation.is_active.is_(True), ServiceOrderPartReservation.status == "RESERVED")
        if branch_id is not None and not self._is_admin(actor):
            reservation_query = reservation_query.where(or_(ServiceOrderPartReservation.branch_id == branch_id, ServiceOrderPartReservation.branch_id.is_(None)))
        reservations = list(db.session.scalars(reservation_query).all())
        if not reservations:
            raise StockIssueValidationError("Brak aktywnych rezerwacji do wydania.")
        quantities = quantities or {}
        issue = StockIssue(issue_number=self._next_number(company_id), issue_date=date.today(), service_order_id=service_order_id, branch_id=branch_id, issued_by=getattr(actor, "id", None), status=StockIssueStatusEnum.DRAFT.value, notes=(notes or "").strip() or None, company_id=company_id, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None))
        db.session.add(issue)
        db.session.flush()
        for reservation in reservations:
            quantity = Decimal(quantities.get(reservation.id, reservation.quantity))
            if quantity <= 0:
                continue
            if quantity > Decimal(reservation.quantity):
                raise StockIssueValidationError("Ilość wydania nie może przekroczyć rezerwacji.")
            part = reservation.part or db.session.get(CatalogPart, reservation.part_id)
            if part is None or Decimal(part.current_stock) < quantity:
                raise StockIssueValidationError("Niewystarczający stan magazynowy dla wydawanej części.")
            demand = db.session.scalar(select(PartDemand).where(PartDemand.service_order_id == service_order_id, PartDemand.inventory_item_id == reservation.part_id, PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status != PartDemandStatusEnum.CANCELLED.value).order_by(PartDemand.created_at.asc(), PartDemand.id.asc()))
            db.session.add(StockIssueItem(stock_issue_id=issue.id, part_id=reservation.part_id, part_demand_id=demand.id if demand else None, reservation_id=reservation.id, quantity_issued=quantity, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
            before = Decimal(part.current_stock)
            part.current_stock = before - quantity
            db.session.add(CatalogStockMovement(item_type="PART", part_id=part.id, movement_type="ISSUE", quantity=quantity, stock_before=before, stock_after=part.current_stock, reference_type="STOCK_ISSUE", reference_id=issue.issue_number, note=f"Wydanie RW nr {issue.issue_number}", user_id=getattr(actor, "id", None), company_id=company_id, branch_id=branch_id))
            remaining = Decimal(reservation.quantity) - quantity
            if remaining == 0:
                reservation.quantity = Decimal("0")
                reservation.status = "RELEASED"
                reservation.is_active = False
            else:
                reservation.quantity = remaining
            db.session.add(reservation)
            if demand is not None:
                remaining_demand = max(Decimal("0"), Decimal(reservation.quantity))
                demand.reserved_quantity = remaining_demand
                demand.missing_quantity = remaining_demand
                demand.status = PartDemandStatusEnum.DELIVERED.value if remaining_demand == 0 else PartDemandStatusEnum.ORDERED.value
                demand.updated_by = getattr(actor, "id", None)
        if not issue.items:
            raise StockIssueValidationError("Wybierz co najmniej jedną dodatnią ilość do wydania.")
        issue.status = StockIssueStatusEnum.ISSUED.value
        db.session.add(AuditLog(user_id=getattr(actor, "id", None), company_id=company_id, action="STOCK_ISSUE", object_type="StockIssue", object_id=str(issue.id), description=f"Wydano części dokumentem RW nr {issue.issue_number}", created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
        db.session.commit()
        return issue

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
            raise StockIssuePermissionError("Tylko magazynier może wydawać części.")


stock_issue_service = StockIssueService()