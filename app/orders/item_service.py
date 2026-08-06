from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.service_order_item import SERVICE_ORDER_ITEM_TYPE_CHOICES, SERVICE_ORDER_ITEM_TYPE_LABELS, ServiceOrderItem

from .item_repository import ResolvedCatalogItem, ServiceOrderItemRepository


THREE_DP = Decimal("0.001")
TWO_DP = Decimal("0.01")


@dataclass(slots=True)
class OrderItemTotals:
    parts_net: Decimal
    materials_net: Decimal
    services_net: Decimal
    vat: Decimal
    gross: Decimal


class ServiceOrderItemError(Exception):
    pass


class ServiceOrderItemNotFoundError(ServiceOrderItemError):
    pass


class ServiceOrderItemValidationError(ServiceOrderItemError):
    pass


class ServiceOrderItemService:
    def __init__(self, repository: ServiceOrderItemRepository | None = None) -> None:
        self.repository = repository or ServiceOrderItemRepository()

    def get_type_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ORDER_ITEM_TYPE_CHOICES)

    def get_type_labels(self) -> dict[str, str]:
        return dict(SERVICE_ORDER_ITEM_TYPE_LABELS)

    def list_items(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> list[dict[str, Any]]:
        items = self.repository.list_items(order_id=order_id, company_id=company_id, branch_id=branch_id)
        result: list[dict[str, Any]] = []
        for item in items:
            resolved = self.repository.resolve_catalog_item(item_type=item.item_type, item_id=item.item_id, company_id=company_id)
            result.append(self._serialize_item(item, resolved))
        return result

    def search_catalog_items(self, *, query_text: str | None, company_id: int) -> list[dict[str, Any]]:
        results = self.repository.search_catalog_items(query_text=query_text, company_id=company_id)
        return [
            {
                "item_type": item.item_type,
                "item_id": item.item_id,
                "code": item.code,
                "name": item.name,
                "barcode": item.barcode,
                "unit_price_net": f"{item.unit_price_net:.2f}",
                "vat_rate": f"{item.vat_rate:.2f}",
                "current_stock": f"{item.current_stock:.3f}" if item.current_stock is not None else None,
                "source_label": item.source_label,
            }
            for item in results
        ]

    def add_item(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        item_type: str,
        item_id: int,
        quantity_raw: Any,
        unit_price_net_raw: Any | None,
        discount_percent_raw: Any | None,
        notes: str | None,
    ) -> ServiceOrderItem:
        order = self.repository.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise ServiceOrderItemNotFoundError("Nie znaleziono zlecenia.")

        normalized_type = (item_type or "").strip().upper()
        if normalized_type not in {choice[0] for choice in SERVICE_ORDER_ITEM_TYPE_CHOICES}:
            raise ServiceOrderItemValidationError("Wybierz poprawny typ pozycji.")

        resolved = self.repository.resolve_catalog_item(item_type=normalized_type, item_id=item_id, company_id=company_id)
        if resolved is None:
            raise ServiceOrderItemNotFoundError("Nie znaleziono wybranego elementu katalogu.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise ServiceOrderItemValidationError("Ilość musi być większa od zera.")

        unit_price_net = self._to_decimal(unit_price_net_raw, places=2, default=resolved.unit_price_net)
        if unit_price_net < Decimal("0"):
            raise ServiceOrderItemValidationError("Cena netto nie może być ujemna.")

        discount_percent = self._to_decimal(discount_percent_raw, places=2, default=Decimal("0"))
        if discount_percent < Decimal("0") or discount_percent > Decimal("100"):
            raise ServiceOrderItemValidationError("Rabat musi mieścić się w zakresie 0-100.")

        vat_rate = resolved.vat_rate
        existing = self.repository.find_existing(
            order_id=order.id,
            item_type=normalized_type,
            item_id=resolved.item_id,
            company_id=company_id,
            branch_id=branch_id,
        )

        if existing is None:
            payload = {
                "service_order_id": order.id,
                "item_type": normalized_type,
                "item_id": resolved.item_id,
                "quantity": quantity,
                "reserved_quantity": quantity if normalized_type in {"PART", "MATERIAL"} else Decimal("0"),
                "used_quantity": Decimal("0"),
                "returned_quantity": Decimal("0"),
                "unit_price_net": unit_price_net,
                "discount_percent": discount_percent,
                "vat_rate": vat_rate,
                "total_net": self._line_total(quantity, unit_price_net, discount_percent),
                "notes": (notes or "").strip() or None,
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
            item = self.repository.create_item(payload)
        else:
            existing.quantity = Decimal(existing.quantity) + quantity
            if normalized_type in {"PART", "MATERIAL"}:
                existing.reserved_quantity = Decimal(existing.reserved_quantity) + quantity
            existing.unit_price_net = unit_price_net
            existing.discount_percent = discount_percent
            existing.vat_rate = vat_rate
            existing.total_net = self._line_total(existing.quantity, unit_price_net, discount_percent)
            if notes:
                existing.notes = (notes or "").strip() or existing.notes
            existing.updated_by = user_id
            item = self.repository.update_item(existing, {})

        db.session.commit()
        return item

    def mark_used(
        self,
        *,
        order_id: int,
        item_id: int,
        quantity_raw: Any,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
    ) -> ServiceOrderItem:
        item = self._get_order_item(order_id=order_id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item.item_type == "SERVICE":
            raise ServiceOrderItemValidationError("Usługi nie posiadają ruchów magazynowych.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise ServiceOrderItemValidationError("Ilość zużycia musi być większa od zera.")

        if Decimal(item.reserved_quantity) < quantity:
            raise ServiceOrderItemValidationError("Brak wystarczającej ilości zarezerwowanej do zużycia.")

        self._create_usage_movement(
            item=item,
            quantity=quantity,
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
            movement_type="SERVICE_USAGE",
        )
        item.reserved_quantity = Decimal(item.reserved_quantity) - quantity
        item.used_quantity = Decimal(item.used_quantity) + quantity
        item.updated_by = user_id
        db.session.add(item)
        db.session.commit()
        return item

    def return_item(
        self,
        *,
        order_id: int,
        item_id: int,
        quantity_raw: Any,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
    ) -> ServiceOrderItem:
        item = self._get_order_item(order_id=order_id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item.item_type == "SERVICE":
            raise ServiceOrderItemValidationError("Usługi nie podlegają zwrotowi magazynowemu.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise ServiceOrderItemValidationError("Ilość zwrotu musi być większa od zera.")

        if Decimal(item.reserved_quantity) < quantity:
            raise ServiceOrderItemValidationError("Brak wystarczającej ilości zarezerwowanej do zwrotu.")

        self._create_usage_movement(
            item=item,
            quantity=quantity,
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
            movement_type="RETURN",
        )
        item.reserved_quantity = Decimal(item.reserved_quantity) - quantity
        item.returned_quantity = Decimal(item.returned_quantity) + quantity
        item.updated_by = user_id
        db.session.add(item)
        db.session.commit()
        return item

    def compute_totals(self, items: list[dict[str, Any]]) -> OrderItemTotals:
        parts_net = Decimal("0")
        materials_net = Decimal("0")
        services_net = Decimal("0")
        vat = Decimal("0")
        gross = Decimal("0")

        for item in items:
            total_net = Decimal(item["total_net"])
            vat_amount = self._line_vat(total_net, Decimal(item["vat_rate"]))
            gross_amount = (total_net + vat_amount).quantize(TWO_DP, rounding=ROUND_HALF_UP)
            if item["item_type"] == "PART":
                parts_net += total_net
            elif item["item_type"] == "MATERIAL":
                materials_net += total_net
            else:
                services_net += total_net
            vat += vat_amount
            gross += gross_amount

        return OrderItemTotals(
            parts_net=parts_net.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            materials_net=materials_net.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            services_net=services_net.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            vat=vat.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            gross=gross.quantize(TWO_DP, rounding=ROUND_HALF_UP),
        )

    def get_item_for_order(self, *, order_id: int, item_id: int, company_id: int, branch_id: int | None) -> ServiceOrderItem:
        item = self._get_order_item(order_id=order_id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        return item

    def _get_order_item(self, *, order_id: int, item_id: int, company_id: int, branch_id: int | None) -> ServiceOrderItem:
        item = self.repository.get_item(item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item is None or item.service_order_id != order_id:
            raise ServiceOrderItemNotFoundError("Nie znaleziono pozycji zlecenia.")
        return item

    def _serialize_item(self, item: ServiceOrderItem, resolved: ResolvedCatalogItem | None) -> dict[str, Any]:
        vat_amount = self._line_vat(Decimal(item.total_net), Decimal(item.vat_rate))
        gross_amount = (Decimal(item.total_net) + vat_amount).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        return {
            "id": item.id,
            "service_order_id": item.service_order_id,
            "item_type": item.item_type,
            "item_type_label": SERVICE_ORDER_ITEM_TYPE_LABELS.get(item.item_type, item.item_type),
            "item_id": item.item_id,
            "quantity": f"{Decimal(item.quantity):.3f}",
            "reserved_quantity": f"{Decimal(item.reserved_quantity):.3f}",
            "used_quantity": f"{Decimal(item.used_quantity):.3f}",
            "returned_quantity": f"{Decimal(item.returned_quantity):.3f}",
            "unit_price_net": f"{Decimal(item.unit_price_net):.2f}",
            "discount_percent": f"{Decimal(item.discount_percent):.2f}",
            "vat_rate": f"{Decimal(item.vat_rate):.2f}",
            "total_net": f"{Decimal(item.total_net):.2f}",
            "total_vat": f"{vat_amount:.2f}",
            "total_gross": f"{gross_amount:.2f}",
            "notes": item.notes,
            "resolved": None if resolved is None else {
                "code": resolved.code,
                "name": resolved.name,
                "barcode": resolved.barcode,
                "current_stock": None if resolved.current_stock is None else f"{resolved.current_stock:.3f}",
                "unit_price_net": f"{resolved.unit_price_net:.2f}",
                "vat_rate": f"{resolved.vat_rate:.2f}",
            },
        }

    def _create_usage_movement(
        self,
        *,
        item: ServiceOrderItem,
        quantity: Decimal,
        user_id: int | None,
        company_id: int,
        branch_id: int | None,
        movement_type: str,
    ) -> None:
        resolved = self.repository.resolve_catalog_item(item_type=item.item_type, item_id=item.item_id, company_id=company_id)
        if resolved is None or resolved.current_stock is None:
            raise ServiceOrderItemNotFoundError("Nie można odnaleźć stanu magazynowego elementu.")

        stock_before = Decimal(resolved.current_stock)
        if movement_type == "SERVICE_USAGE":
            stock_after = stock_before - quantity
        else:
            stock_after = stock_before + quantity

        if stock_after < Decimal("0"):
            raise ServiceOrderItemValidationError("Stan magazynowy nie może spaść poniżej zera.")

        if item.item_type == "PART":
            part = db.session.scalar(
                select(CatalogPart).where(CatalogPart.id == item.item_id).where(CatalogPart.company_id == company_id)
            )
            if part is None:
                raise ServiceOrderItemNotFoundError("Nie znaleziono części.")
            part.current_stock = stock_after.quantize(THREE_DP, rounding=ROUND_HALF_UP)
            db.session.add(part)
            db.session.flush()
            db.session.add(
                CatalogStockMovement(
                    item_type="PART",
                    part_id=part.id,
                    user_id=user_id,
                    service_order_id=item.service_order_id,
                    movement_type=movement_type,
                    operation_at=db.func.now(),
                    quantity=quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP),
                    stock_before=stock_before.quantize(THREE_DP, rounding=ROUND_HALF_UP),
                    stock_after=part.current_stock,
                    reference_type="SERVICE_ORDER_ITEM",
                    reference_id=str(item.id),
                    note="Zużycie/zwrot pozycji zlecenia",
                    company_id=company_id,
                    branch_id=branch_id,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
            db.session.flush()
            return

        if item.item_type == "MATERIAL":
            material = db.session.scalar(
                select(CatalogMaterial).where(CatalogMaterial.id == item.item_id).where(CatalogMaterial.company_id == company_id)
            )
            if material is None:
                raise ServiceOrderItemNotFoundError("Nie znaleziono materiału.")
            material.current_stock = stock_after.quantize(THREE_DP, rounding=ROUND_HALF_UP)
            db.session.add(material)
            db.session.flush()
            db.session.add(
                CatalogStockMovement(
                    item_type="MATERIAL",
                    material_id=material.id,
                    user_id=user_id,
                    service_order_id=item.service_order_id,
                    movement_type=movement_type,
                    operation_at=db.func.now(),
                    quantity=quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP),
                    stock_before=stock_before.quantize(THREE_DP, rounding=ROUND_HALF_UP),
                    stock_after=material.current_stock,
                    reference_type="SERVICE_ORDER_ITEM",
                    reference_id=str(item.id),
                    note="Zużycie/zwrot pozycji zlecenia",
                    company_id=company_id,
                    branch_id=branch_id,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
            db.session.flush()
            return

        raise ServiceOrderItemValidationError("Usługi nie wykonują ruchów magazynowych.")

    def _line_total(self, quantity: Decimal, unit_price_net: Decimal, discount_percent: Decimal) -> Decimal:
        discounted = unit_price_net * (Decimal("1") - (discount_percent / Decimal("100")))
        return (quantity * discounted).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    def _line_vat(self, total_net: Decimal, vat_rate: Decimal) -> Decimal:
        return (total_net * (vat_rate / Decimal("100"))).quantize(TWO_DP, rounding=ROUND_HALF_UP)

    def _to_decimal(self, value: Any, *, places: int, default: Decimal | None = None) -> Decimal:
        if value is None or (isinstance(value, str) and not value.strip()):
            if default is not None:
                return default
            return Decimal("0")
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0." + "0" * (places - 1) + "1"), rounding=ROUND_HALF_UP) if places else value
        return Decimal(str(value))
