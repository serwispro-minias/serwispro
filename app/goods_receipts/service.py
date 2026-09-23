from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_part import InventoryItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import Supplier
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptStatusEnum
from app.models.goods_receipt_item import GoodsReceiptItem
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.vat_rate import VatRate

from .exceptions import (
    GoodsReceiptNotFoundError,
    GoodsReceiptPermissionError,
    GoodsReceiptValidationError,
)


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
                selectinload(GoodsReceipt.items).selectinload(GoodsReceiptItem.inventory_item),
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

    def update_receipt(self, *, receipt_id: int, company_id: int, branch_id: int | None, actor, receipt_date: date | None = None, supplier_id: int | None = None, notes: str | None = None) -> GoodsReceipt:
        self._assert_manage(actor)
        receipt = self.get_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if receipt.status != GoodsReceiptStatusEnum.DRAFT.value:
            raise GoodsReceiptValidationError("Zaksięgowanego PZ nie można edytować.")
        effective_supplier_id = supplier_id if supplier_id is not None else receipt.supplier_id
        supplier = db.session.scalar(select(Supplier).where(Supplier.id == effective_supplier_id, Supplier.company_id == company_id, Supplier.is_active.is_(True)))
        if supplier is None:
            raise GoodsReceiptValidationError("Nieprawidłowy dostawca.")
        receipt.supplier_id = supplier.id
        if receipt_date is not None:
            receipt.receipt_date = receipt_date
        receipt.notes = (notes or "").strip() or None
        receipt.updated_by = getattr(actor, "id", None)
        db.session.commit()
        return receipt

    def create_receipt(self, *, purchase_order_id: int | None = None, items: list[dict[str, object]], company_id: int, branch_id: int | None, actor, receipt_date: date | None = None, supplier_id: int | None = None, notes: str | None = None) -> GoodsReceipt:
        self._assert_manage(actor)
        if not items:
            raise GoodsReceiptValidationError("Dokument PZ musi zawierać co najmniej jedną pozycję.")
        order = None
        if purchase_order_id is not None:
            order = db.session.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == purchase_order_id, PurchaseOrder.company_id == company_id, PurchaseOrder.is_active.is_(True)))
            if order is None:
                raise GoodsReceiptValidationError("Nie znaleziono zamówienia dostawcy.")
            if order.status == PurchaseOrderStatusEnum.CANCELLED.value:
                raise GoodsReceiptValidationError("Nie można przyjąć anulowanego zamówienia.")
        effective_supplier_id = supplier_id if supplier_id is not None else (order.supplier_id if order is not None else None)
        if effective_supplier_id is None:
            raise GoodsReceiptValidationError("PZ musi mieć dostawcę.")
        supplier = db.session.scalar(select(Supplier).where(Supplier.id == effective_supplier_id, Supplier.company_id == company_id, Supplier.is_active.is_(True)))
        if supplier is None:
            raise GoodsReceiptValidationError("Nieprawidłowy dostawca.")
        seen: set[int] = set()
        normalized: list[dict[str, object]] = []
        for payload in items:
            po_item = None
            if order is not None:
                item_id = self._positive_int(payload.get("purchase_order_item_id"), "pozycja zamówienia")
                if item_id in seen:
                    raise GoodsReceiptValidationError("Ta sama pozycja zamówienia została dodana dwa razy.")
                seen.add(item_id)
                po_item = next((row for row in order.items if row.id == item_id), None)
                if po_item is None:
                    raise GoodsReceiptValidationError("Pozycja PZ nie należy do wybranego zamówienia.")
            quantity = self._positive_quantity(payload.get("quantity_received"), "ilość dostarczona")
            if po_item is not None and quantity > Decimal(po_item.quantity_ordered) - Decimal(po_item.quantity_received):
                raise GoodsReceiptValidationError("Ilość dostarczona nie może przekroczyć ilości pozostałej w zamówieniu.")
            item_id = payload.get("inventory_item_id") or (po_item.part_id if po_item is not None else None)
            product_id = self._positive_int(item_id, "produkt")
            product = db.session.scalar(select(InventoryItem).options(selectinload(InventoryItem.vat)).where(InventoryItem.id == product_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)))
            if product is None:
                raise GoodsReceiptValidationError("Nieprawidłowy produkt.")
            vat_id = self._positive_int(payload.get("vat_id") or product.vat_id, "VAT")
            vat = db.session.scalar(select(VatRate).where(VatRate.id == vat_id, VatRate.company_id == company_id, VatRate.is_active.is_(True)))
            if vat is None:
                raise GoodsReceiptValidationError("Nieprawidłowa stawka VAT.")
            price = self._non_negative_decimal(payload.get("purchase_price_net") if payload.get("purchase_price_net") is not None else (po_item.unit_price_net if po_item is not None else product.purchase_price_net), "cena zakupu netto")
            sale_price = self._non_negative_decimal(payload.get("sale_price_net") if payload.get("sale_price_net") is not None else self._suggest_sale_price(product, price), "cena sprzedaży netto")
            normalized.append({"po_item": po_item, "product": product, "quantity": quantity, "vat": vat, "price": price, "sale_price": sale_price, "payload": payload})

        receipt = GoodsReceipt(
            receipt_number=self._next_number(company_id),
            receipt_date=receipt_date or date.today(),
            supplier_id=effective_supplier_id,
            purchase_order_id=order.id if order is not None else None,
            received_by=getattr(actor, "id", None),
            status=GoodsReceiptStatusEnum.DRAFT.value,
            notes=(notes or "").strip() or None,
            company_id=company_id,
            branch_id=branch_id,
            created_by=getattr(actor, "id", None),
            updated_by=getattr(actor, "id", None),
        )
        db.session.add(receipt)
        db.session.flush()
        for row in normalized:
            payload = row["payload"]
            po_item = row["po_item"]
            quantity = row["quantity"]
            product = row["product"]
            vat = row["vat"]
            db.session.add(
                GoodsReceiptItem(
                    goods_receipt_id=receipt.id,
                    purchase_order_item_id=po_item.id if po_item is not None else None,
                    inventory_item_id=product.id,
                    quantity_ordered=po_item.quantity_ordered if po_item is not None else quantity,
                    quantity_received=quantity,
                    purchase_price_net=row["price"],
                    sale_price_net=row["sale_price"],
                    vat_id=vat.id,
                    demand_id=payload.get("demand_id") or None,
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
        try:
            return self._post_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=branch_id, actor=actor)
        except Exception:
            db.session.rollback()
            raise

    def _post_receipt(self, *, receipt_id: int, company_id: int, branch_id: int | None, actor) -> GoodsReceipt:
        self._assert_manage(actor)
        receipt = self.get_receipt(receipt_id=receipt_id, company_id=company_id, branch_id=branch_id, actor=actor)
        if receipt.status == GoodsReceiptStatusEnum.CANCELLED.value:
            raise GoodsReceiptValidationError("Anulowanego dokumentu PZ nie można przyjąć.")
        if receipt.status == GoodsReceiptStatusEnum.POSTED.value:
            return receipt
        order = db.session.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.items)).where(PurchaseOrder.id == receipt.purchase_order_id)) if receipt.purchase_order_id else None
        if receipt.supplier_id is None and order is not None:
            receipt.supplier_id = order.supplier_id

        for item in receipt.items:
            part = db.session.scalar(select(InventoryItem).where(InventoryItem.id == item.inventory_item_id, InventoryItem.company_id == company_id, InventoryItem.is_active.is_(True)))
            if part is None:
                raise GoodsReceiptValidationError("Nie znaleziono części dla pozycji PZ.")
            before = Decimal(part.current_stock)
            part.current_stock = int(before + Decimal(item.quantity_received))
            part.purchase_price_net = item.purchase_price_net
            part.sale_price_net = item.sale_price_net
            db.session.add(part)
            db.session.add(
                CatalogStockMovement(
                    item_type="PART",
                    part_id=part.id,
                    movement_type="RECEIPT",
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
            if order is not None and item.purchase_order_item_id is not None:
                po_item = next(po_item for po_item in order.items if po_item.id == item.purchase_order_item_id)
                po_item.quantity_received = Decimal(po_item.quantity_received) + Decimal(item.quantity_received)

        receipt.status = GoodsReceiptStatusEnum.POSTED.value
        receipt.updated_by = getattr(actor, "id", None)
        if order is not None:
            received = sum((Decimal(item.quantity_received) for item in order.items), Decimal("0"))
            ordered = sum((Decimal(item.quantity_ordered) for item in order.items), Decimal("0"))
            order.status = PurchaseOrderStatusEnum.COMPLETED.value if received >= ordered else PurchaseOrderStatusEnum.PARTIAL.value
            order.updated_by = getattr(actor, "id", None)
        if inspect(db.engine).has_table("audit_logs"):
            db.session.add(AuditLog(user_id=getattr(actor, "id", None), company_id=company_id, action="GOODS_RECEIPT_POSTED", object_type="GoodsReceipt", object_id=str(receipt.id), description=f"Zaksięgowano PZ {receipt.receipt_number}", created_by=getattr(actor, "id", None), updated_by=getattr(actor, "id", None)))
        db.session.commit()
        return receipt

    def _non_negative_decimal(self, value, label: str) -> Decimal:
        result = self._positive_decimal(value, label, allow_zero=True)
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _suggest_sale_price(self, product: InventoryItem, purchase_price: Decimal) -> Decimal:
        current_purchase = Decimal(product.purchase_price_net or 0)
        current_sale = Decimal(product.sale_price_net or 0)
        if current_purchase <= 0:
            return current_sale.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        multiplier = current_sale / current_purchase
        return (purchase_price * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

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

    def _positive_decimal(self, value, label: str, allow_zero: bool = False) -> Decimal:
        try:
            result = Decimal(str(value))
        except Exception:
            raise GoodsReceiptValidationError(f"Nieprawidłowa wartość pola: {label}.") from None
        if result < 0 or (result == 0 and not allow_zero):
            raise GoodsReceiptValidationError(f"Pole {label} musi być większe od zera.")
        return result

    def _positive_quantity(self, value, label: str) -> Decimal:
        result = self._positive_decimal(value, label)
        if result != result.to_integral_value():
            raise GoodsReceiptValidationError(f"Pole {label} musi być liczbą całkowitą.")
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