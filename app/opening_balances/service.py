from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_part import InventoryItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.opening_balance import OpeningBalance, OpeningBalanceStatusEnum
from app.models.opening_balance_item import OpeningBalanceItem
from app.models.vat_rate import VatRate

from .exceptions import (
    OpeningBalanceNotFoundError,
    OpeningBalancePermissionError,
    OpeningBalanceValidationError,
)


class OpeningBalanceService:
    def create(self, *, items: list[dict[str, object]], company_id: int, branch_id: int | None, actor, document_date: date | None = None, notes: str | None = None) -> OpeningBalance:
        self._assert_manage(actor)
        if not items:
            raise OpeningBalanceValidationError("Bilans otwarcia musi zawierać co najmniej jedną pozycję.")
        balance = OpeningBalance(document_number=self._next_number(company_id), document_date=document_date or date.today(), notes=(notes or "").strip() or None, company_id=company_id, branch_id=branch_id, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None))
        db.session.add(balance)
        db.session.flush()
        for payload in items:
            item_id = self._positive_int(payload.get("inventory_item_id"), "produkt")
            quantity = self._positive_int(payload.get("quantity"), "ilość")
            product = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)))
            if product is None:
                raise OpeningBalanceValidationError("Nieprawidłowy produkt.")
            vat_id = self._positive_int(payload.get("vat_id") or product.vat_id, "VAT")
            vat = db.session.scalar(select(VatRate).where(VatRate.id == vat_id, VatRate.company_id == company_id, VatRate.is_active.is_(True)))
            if vat is None:
                raise OpeningBalanceValidationError("Nieprawidłowa stawka VAT.")
            price = self._non_negative_decimal(payload.get("purchase_price_net", product.purchase_price_net), "cena zakupu netto")
            net = (Decimal(quantity) * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat_value = (net * Decimal(vat.rate) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            db.session.add(OpeningBalanceItem(opening_balance_id=balance.id, inventory_item_id=item_id, quantity=quantity, purchase_price_net=price, vat_id=vat.id, net_value=net, vat_value=vat_value, gross_value=net + vat_value, created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
        db.session.commit()
        return balance

    def get(self, *, balance_id: int, company_id: int, branch_id: int | None, actor) -> OpeningBalance:
        self._assert_view(actor)
        query = select(OpeningBalance).options(selectinload(OpeningBalance.items).selectinload(OpeningBalanceItem.inventory_item)).where(OpeningBalance.id == balance_id, OpeningBalance.company_id == company_id, OpeningBalance.is_active.is_(True))
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(OpeningBalance.branch_id == branch_id, OpeningBalance.branch_id.is_(None)))
        balance = db.session.scalar(query)
        if balance is None:
            raise OpeningBalanceNotFoundError("Nie znaleziono bilansu otwarcia.")
        return balance

    def list(self, *, company_id: int, branch_id: int | None, actor) -> list[OpeningBalance]:
        self._assert_view(actor)
        query = select(OpeningBalance).where(OpeningBalance.company_id == company_id, OpeningBalance.is_active.is_(True)).order_by(OpeningBalance.document_date.desc(), OpeningBalance.id.desc())
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(OpeningBalance.branch_id == branch_id, OpeningBalance.branch_id.is_(None)))
        return list(db.session.scalars(query).all())

    def post(self, *, balance_id: int, company_id: int, branch_id: int | None, actor) -> OpeningBalance:
        try:
            return self._post(balance_id=balance_id, company_id=company_id, branch_id=branch_id, actor=actor)
        except Exception:
            db.session.rollback()
            raise

    def _post(self, *, balance_id: int, company_id: int, branch_id: int | None, actor) -> OpeningBalance:
        self._assert_manage(actor)
        balance = self.get(balance_id=balance_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if balance.status == OpeningBalanceStatusEnum.POSTED.value:
            return balance
        if balance.status == OpeningBalanceStatusEnum.CANCELLED.value:
            raise OpeningBalanceValidationError("Anulowanego bilansu nie można zaksięgować.")
        if not balance.items:
            raise OpeningBalanceValidationError("Bilans otwarcia nie ma pozycji.")
        for item in balance.items:
            product = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item.inventory_item_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)).with_for_update())
            if product is None:
                raise OpeningBalanceValidationError("Produkt bilansu nie istnieje lub jest nieaktywny.")
            before = Decimal(product.current_stock)
            product.current_stock = int(before + item.quantity)
            db.session.add(CatalogStockMovement(item_type="PART", part_id=product.id, movement_type="OPENING_BALANCE", quantity=Decimal(item.quantity), stock_before=before, stock_after=Decimal(product.current_stock), reference_type="OPENING_BALANCE", reference_id=balance.document_number, note=f"Bilans otwarcia {balance.document_number}", user_id=getattr(actor, "id", None), company_id=company_id, branch_id=branch_id))
        balance.status = OpeningBalanceStatusEnum.POSTED.value
        balance.updated_by = getattr(actor, "id", None)
        if inspect(db.engine).has_table("audit_logs"):
            db.session.add(AuditLog(user_id=getattr(actor, "id", None), company_id=company_id, action="OPENING_BALANCE_POSTED", object_type="OpeningBalance", object_id=str(balance.id), description=f"Zaksięgowano bilans {balance.document_number}", created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
        db.session.commit()
        return balance

    def _next_number(self, company_id: int) -> str:
        year = date.today().year
        prefix = f"BO/{year}/"
        count = db.session.scalar(select(func.count(OpeningBalance.id)).where(OpeningBalance.company_id == company_id, OpeningBalance.document_number.like(f"{prefix}%"))) or 0
        return f"{prefix}{int(count) + 1:06d}"

    def _positive_int(self, value, label: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise OpeningBalanceValidationError(f"Nieprawidłowa wartość pola: {label}.") from exc
        if result <= 0:
            raise OpeningBalanceValidationError(f"Pole {label} musi być większe od zera.")
        return result

    def _non_negative_decimal(self, value, label: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except Exception as exc:
            raise OpeningBalanceValidationError(f"Nieprawidłowa wartość pola: {label}.") from exc
        if result < 0:
            raise OpeningBalanceValidationError(f"Pole {label} nie może być ujemne.")
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _names(self, actor): return {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
    def _is_admin(self, actor): return "administrator" in self._names(actor)
    def _is_warehouse(self, actor): return bool(self._names(actor) & {"magazyn", "magazynier", "zakupy", "warehouse"})
    def _assert_view(self, actor):
        if not (self._is_admin(actor) or self._is_warehouse(actor)):
            raise OpeningBalancePermissionError("Brak uprawnień do podglądu bilansów otwarcia.")
    def _assert_manage(self, actor):
        if not (self._is_admin(actor) or self._is_warehouse(actor)):
            raise OpeningBalancePermissionError("Tylko magazynier lub administrator może obsługiwać bilans otwarcia.")


opening_balance_service = OpeningBalanceService()
