from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptStatusEnum
from app.models.goods_receipt_item import GoodsReceiptItem
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation

from .exceptions import GoodsReceiptNotFoundError, GoodsReceiptPermissionError, GoodsReceiptValidationError


class GoodsReceiptService:
    def list_receipts(self, *, company_id: int, branch_id: int | None, actor):
        self._assert_view(actor)
        query = (
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.supplier), selectinload(GoodsReceipt.purchase_order), selectinload(GoodsReceipt.items), selectinload(GoodsReceipt.receiver))
            .where(GoodsReceipt.company_id == company_id, GoodsReceipt.is_active.is_(True))
            .order_by(GoodsReceipt.receipt_date.desc(), GoodsReceipt.id.desc())
        )
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(GoodsReceipt.branch_id == branch_id, GoodsReceipt.branch_id.is_(None)))
        return list(db.session.scalars(query).unique().all())

    def get_receipt(self, *, receipt_id: int, company_id: int, branch_id: int | None, actor) -> GoodsReceipt:
        self._assert_view(actor)
        query = (
            select(GoodsReceipt)
            .options(
                selectinload(GoodsReceipt.supplier),
                selectinload(GoodsReceipt.purchase_order),
                selectinload(GoodsReceipt.receiver),
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.part),
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.purchase_order_item).selectinload(PurchaseOrderItem.demand_links).selectinload(PurchaseOrderDemandLink.demand),
            )
            .where(GoodsReceipt.id == receipt_id, GoodsReceipt.company_id == company_id, GoodsReceipt.is_active.is_(True))
        )
        if branch_id is not None and not self._is_admin(actor):
            query = query.where(or_(GoodsReceipt.branch_id == branch_id, GoodsReceipt.branch_id.is_(None)))
        receipt = db.session.scalar(query)
        if receipt is None:
            raise GoodsReceiptNotFoundError("Nie znaleziono dokumentu PZ.")
        return receipt

    def create_receipt(self, *, purchase_order_id: int, items: list[dict[str, object]], company_id: int, branch_id: int | None, actor, receipt_date: date | None = None) -> GoodsReceipt:
        self._assert_manage(actor)
        if not items:
            raise GoodsReceiptValidationError("Dokument PZ musi zawierać co najmniej jedną pozycję.")
        order = db.session.scalar(
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items), selectinload(PurchaseOrder.supplier))
            .where(PurchaseOrder.id == purchase_order_id, PurchaseOrder.company_id == company_id, PurchaseOrder.is_active.is_(True))
        )
        if order is None:
            raise GoodsReceiptValidationError("Nie znaleziono zamówienia dostawcy.")
        if order.status == PurchaseOrderStatusEnum.CANCELLED.value:
            raise GoodsReceiptValidationError("Nie można przyjąć anulowanego zamówienia.")
        item_map = {item.id: item for item in order.items}
        seen: set[int] = set()
        normalized: list[tuple[PurchaseOrderItem, Decimal]] = []
        for payload in items:
            item_id = self._positive_int(payload.get("purchase_order_item_id"), "pozycja zamówienia")
            if item_id in seen:
                raise GoodsReceiptValidationError("Ta sama pozycja zamówienia została dodana dwa razy.")
            seen.add(item_id)
            po_item = item_map.get(item_id)
            if po_item is None:
                raise GoodsReceiptValidationError("Pozycja PZ nie należy do wybranego zamówienia.")
            quantity = self._positive_decimal(payload.get("quantity_received"), "ilość dostarczona")
            remaining = Decimal(po_item.quantity_ordered) - Decimal(po_item.quantity_received)
            if quantity > remaining:
                raise GoodsReceiptValidationError("Ilość dostarczona nie może przekroczyć ilości pozostałej w zamówieniu.")
            normalized.append((po_item, quantity))

        receipt = GoodsReceipt(
            receipt_number=self._next_number(company_id),
            receipt_date=receipt_date or date.today(),
            supplier_id=order.supplier_id,
            purchase_order_id=order.id,
            received_by=getattr(actor, "id", None),
            status=GoodsReceiptStatusEnum.NEW.value,
            company_id=company_id,
            branch_id=branch_id,
            created_by=getattr(actor, "id", None),
            updated_by=getattr(actor, "id", None),
        )
        db.session.add(receipt)
        db.session.flush()
        for payload, (po_item, quantity) in zip(items, normalized):
            db.session.add(
                GoodsReceiptItem(
                    goods_receipt_id=receipt.id,
                    purchase_order_item_id=po_item.id,
                    part_id=po_item.part_id,
                    quantity_ordered=po_item.quantity_ordered,
                    quantity_received=quantity,
                    purchase_price_net=po_item.unit_price_net,
                    batch_number=(str(payload.get("batch_number") or "").strip() or None),
                    serial_number=(str(payload.get("serial_number") or "").strip() or None),
                    notes=(str(payload.get("notes") or "").strip() or None),
                    created_by=getattr(actor, "id", None),
                    updated_by=getattr(actor, "id", None),
                )
            )
        db.session.commit()
        return receipt

    def accept_receipt(self, *, receipt_id: int, company_id: int, branch_id: int | None, actor) -> GoodsReceipt:
        self._assert_manage(actor)
        receipt = self.get_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if receipt.status == GoodsReceiptStatusEnum.CANCELLED.value:
            raise GoodsReceiptValidationError("Anulowanego dokumentu PZ nie można przyjąć.")
        if receipt.status == GoodsReceiptStatusEnum.ACCEPTED.value:
            raise GoodsReceiptValidationError("Dokument PZ został już przyjęty.")
        order = db.session.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == receipt.purchase_order_id))
        if order is None or order.status == PurchaseOrderStatusEnum.CANCELLED.value:
            raise GoodsReceiptValidationError("Powiązane zamówienie jest anulowane lub nie istnieje.")

        for item in receipt.items:
            part = db.session.scalar(select(CatalogPart).where(CatalogPart.id == item.part_id, CatalogPart.company_id == company_id, CatalogPart.is_active.is_(True)))
            if part is None:
                raise GoodsReceiptValidationError("Nie znaleziono części dla pozycji PZ.")
            before = Decimal(part.current_stock)
            part.current_stock = before + Decimal(item.quantity_received)
            db.session.add(part)
            db.session.add(
                CatalogStockMovement(
                    item_type="PART",
                    part_id=part.id,
                    movement_type="IN",
                    quantity=item.quantity_received,
                    stock_before=before,
                    stock_after=part.current_stock,
                    reference_type="GOODS_RECEIPT",
                    reference_id=receipt.receipt_number,
                    note=f"Przyjęcie PZ nr {receipt.receipt_number}",
                    user_id=getattr(actor, "id", None),
                    company_id=company_id,
                    branch_id=branch_id,
                )
            )
            po_item = next(po_item for po_item in order.items if po_item.id == item.purchase_order_item_id)
            po_item.quantity_received = Decimal(po_item.quantity_received) + Decimal(item.quantity_received)
            self._fulfill_demands(part=part, quantity=Decimal(item.quantity_received), company_id=company_id, branch_id=branch_id, actor=actor)

        receipt.status = GoodsReceiptStatusEnum.ACCEPTED.value
        receipt.updated_by = getattr(actor, "id", None)
        received = sum((Decimal(item.quantity_received) for item in order.items), Decimal("0"))
        ordered = sum((Decimal(item.quantity_ordered) for item in order.items), Decimal("0"))
        order.status = PurchaseOrderStatusEnum.COMPLETED.value if received >= ordered else PurchaseOrderStatusEnum.PARTIAL.value
        order.updated_by = getattr(actor, "id", None)
        db.session.commit()
        return receipt

    def _fulfill_demands(self, *, part: CatalogPart, quantity: Decimal, company_id: int, branch_id: int | None, actor) -> None:
        remaining = quantity
        query = select(PartDemand).where(PartDemand.inventory_item_id == part.id, PartDemand.company_id == company_id, PartDemand.is_active.is_(True), PartDemand.status.in_([PartDemandStatusEnum.NEW.value, PartDemandStatusEnum.TO_ORDER.value, PartDemandStatusEnum.IN_PURCHASE.value, PartDemandStatusEnum.ORDERED.value])).order_by(PartDemand.created_at.asc(), PartDemand.id.asc())
        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        demands = db.session.scalars(query).all()
        for demand in demands:
            if remaining <= 0:
                break
            missing = max(Decimal("0"), Decimal(demand.requested_quantity) - Decimal(demand.reserved_quantity))
            allocated = min(remaining, missing)
            if allocated <= 0:
                continue
            demand.reserved_quantity = Decimal(demand.reserved_quantity) + allocated
            demand.missing_quantity = max(Decimal("0"), Decimal(demand.requested_quantity) - Decimal(demand.reserved_quantity))
            demand.status = PartDemandStatusEnum.DELIVERED.value if demand.missing_quantity == 0 else PartDemandStatusEnum.ORDERED.value
            demand.updated_by = getattr(actor, "id", None)
            part.current_stock = Decimal(part.current_stock) - allocated
            db.session.add(
                ServiceOrderPartReservation(
                    service_order_id=demand.service_order_id,
                    part_id=part.id,
                    quantity=allocated,
                    status="RESERVED",
                    company_id=company_id,
                    branch_id=branch_id,
                    created_by=getattr(actor, "id", None),
                    updated_by=getattr(actor, "id", None),
                )
            )
            remaining -= allocated

    def _next_number(self, company_id: int) -> str:
        year = date.today().year
        prefix = f"PZ/{year}/"
        count = db.session.scalar(select(func.count(GoodsReceipt.id)).where(GoodsReceipt.company_id == company_id, GoodsReceipt.receipt_number.like(f"{prefix}%"))) or 0
        return f"{prefix}{int(count) + 1:05d}"

    def _positive_int(self, value, label: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise GoodsReceiptValidationError(f"Nieprawidłowa wartość pola: {label}.") from None
        if result <= 0:
            raise GoodsReceiptValidationError(f"Pole {label} musi być większe od zera.")
        return result

    def _positive_decimal(self, value, label: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except Exception:
            raise GoodsReceiptValidationError(f"Nieprawidłowa wartość pola: {label}.") from None
        if result <= 0:
            raise GoodsReceiptValidationError(f"Pole {label} musi być większe od zera.")
        return result

    def _assert_view(self, actor):
        if not (self._is_admin(actor) or self._is_manager(actor) or self._is_warehouse(actor) or self._is_mechanic(actor)):
            raise GoodsReceiptPermissionError("Brak uprawnień do podglądu PZ.")

    def _assert_manage(self, actor):
        if not (self._is_admin(actor) or self._is_warehouse(actor)):
            raise GoodsReceiptPermissionError("Tylko magazynier lub administrator może obsługiwać PZ.")

    def _names(self, actor):
        return {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}

    def _is_admin(self, actor): return "administrator" in self._names(actor)
    def _is_manager(self, actor): return "kierownik" in self._names(actor)
    def _is_warehouse(self, actor): return bool(self._names(actor) & {"magazyn", "magazynier", "zakupy", "zakupowiec", "warehouse"})
    def _is_mechanic(self, actor): return bool(self._names(actor) & {"mechanik", "technik", "technician", "repairman"})


goods_receipt_service = GoodsReceiptService()