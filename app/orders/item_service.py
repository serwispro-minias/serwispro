from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select, update

from app.extensions import db
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.service_order_item import (
    SERVICE_ORDER_ITEM_TYPE_CHOICES,
    SERVICE_ORDER_ITEM_TYPE_LABELS,
    ServiceOrderItem,
)

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

    def search_catalog_items(self, *, query_text: str | None, company_id: int, branch_id: int | None = None) -> list[dict[str, Any]]:
        results = self.repository.search_catalog_items(query_text=query_text, company_id=company_id, branch_id=branch_id)
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
                "available_stock": None if item.current_stock is None else str(max(Decimal("0"), item.current_stock - self._reserved(item.item_type, item.item_id, company_id))),
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
        reserve: bool = True,
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
        if normalized_type == "PART" and quantity != quantity.to_integral_value():
            raise ServiceOrderItemValidationError("Ilość części musi być całkowita.")
        reserved_quantity = Decimal("0")
        if normalized_type in {"PART", "MATERIAL"}:
            product = self._lock_product(normalized_type, resolved.item_id, company_id)
            if order.branch_id is not None and product.branch_id not in {None, order.branch_id}:
                raise ServiceOrderItemValidationError("Produkt należy do innego oddziału.")
            from app.inventory.reservation_service import reserved_stock
            available = max(Decimal("0"), Decimal(product.current_stock) - reserved_stock(
                item_type=normalized_type, item_id=resolved.item_id, company_id=company_id))
            if reserve:
                reserved_quantity = min(quantity, available)

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
                "reserved_quantity": reserved_quantity,
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
            self._assert_no_pending_issue(existing)
            self._claim_item(existing, existing.version)
            existing.quantity = Decimal(existing.quantity) + quantity
            if normalized_type in {"PART", "MATERIAL"}:
                existing.reserved_quantity = Decimal(existing.reserved_quantity) + reserved_quantity
            existing.unit_price_net = unit_price_net
            existing.discount_percent = discount_percent
            existing.vat_rate = vat_rate
            existing.total_net = self._line_total(existing.quantity, unit_price_net, discount_percent)
            if notes:
                existing.notes = (notes or "").strip() or existing.notes
            existing.updated_by = user_id
            item = self.repository.update_item(existing, {})

        if normalized_type == "PART":
            if reserved_quantity > 0:
                from app.models.service_order_part_reservation import ServiceOrderPartReservation
                db.session.add(ServiceOrderPartReservation(
                    service_order_id=order.id, part_id=resolved.item_id, quantity=reserved_quantity,
                    status="RESERVED", company_id=company_id, branch_id=order.branch_id,
                    created_by=user_id, updated_by=user_id,
                ))
            if quantity > available:
                from app.part_demands.service import PartDemandService
                shortage = PartDemandService().create_or_update_from_shortage(
                    order_id=order.id, part_id=resolved.item_id,
                    requested_quantity=quantity, available_quantity=available,
                    company_id=company_id, branch_id=order.branch_id, actor_id=user_id,
                    service_order_item_id=item.id, commit=False,
                )
                shortage.demand.reserved_quantity += reserved_quantity
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
        actor=None,
        expected_version: int | None = None,
    ):
        item = self._get_order_item(order_id=order_id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item.item_type == "SERVICE":
            raise ServiceOrderItemValidationError("Usługi nie posiadają ruchów magazynowych.")
        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise ServiceOrderItemValidationError("Ilość zużycia musi być większa od zera.")
        from app.models.stock_issue import StockIssue
        from app.models.stock_issue_item import StockIssueItem
        from app.stock_issues.exceptions import StockIssueError
        from app.stock_issues.service import stock_issue_service
        if actor is None:
            raise ServiceOrderItemValidationError("Brak użytkownika rozliczającego.")
        try:
            stock_issue_service._assert_manage(actor)
            # Lock/claim the current version before searching for an existing draft.
            self._claim_item(item, expected_version)
            pending = db.session.scalar(select(StockIssue).join(StockIssueItem).where(
                StockIssueItem.service_order_item_id == item.id,
                StockIssue.status == "DRAFT", StockIssue.company_id == company_id,
                StockIssue.is_active.is_(True),
            ))
            if pending:
                db.session.rollback()
                return pending
            payload = {"quantity": quantity, "service_order_item_id": item.id,
                       "settlement_version": item.version}
            payload["inventory_item_id" if item.item_type == "PART" else "material_id"] = item.item_id
            return stock_issue_service.create_issue(
                items=[payload], company_id=company_id, branch_id=item.branch_id,
                actor=actor, service_order_id=order_id,
                notes="Rozliczenie rzeczywistego zużycia; pozostała rezerwacja zostanie zwolniona przy księgowaniu.",
            )
        except StockIssueError as exc:
            db.session.rollback()
            raise ServiceOrderItemValidationError(str(exc)) from exc
        except Exception:
            db.session.rollback()
            raise

    def return_item(
        self,
        *,
        order_id: int,
        item_id: int,
        quantity_raw: Any,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        expected_version: int | None = None,
        reserve: bool = False,
    ) -> ServiceOrderItem:
        item = self._get_order_item(order_id=order_id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item.item_type == "SERVICE":
            raise ServiceOrderItemValidationError("Usługi nie podlegają zwrotowi magazynowemu.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise ServiceOrderItemValidationError("Ilość zwrotu musi być większa od zera.")

        self._claim_item(item, expected_version)
        self._assert_no_pending_issue(item)
        product = self._lock_product(item.item_type, item.item_id, company_id)
        if item.branch_id is not None and product.branch_id not in {None, item.branch_id}:
            db.session.rollback()
            raise ServiceOrderItemValidationError("Produkt należy do innego oddziału.")
        from app.inventory.reservation_service import reserved_stock
        if reserve:
            available = max(Decimal("0"), Decimal(product.current_stock) - reserved_stock(item_type=item.item_type, item_id=item.item_id, company_id=company_id))
            if quantity > available:
                db.session.rollback()
                raise ServiceOrderItemValidationError(f"Niewystarczająca dostępność: {available}.")
            if item.item_type == "PART" and quantity != quantity.to_integral_value():
                db.session.rollback()
                raise ServiceOrderItemValidationError("Ilość części musi być całkowita.")
            item.reserved_quantity += quantity
            if item.item_type == "PART":
                from app.models.service_order_part_reservation import ServiceOrderPartReservation
                db.session.add(ServiceOrderPartReservation(service_order_id=order_id, part_id=item.item_id,
                    quantity=quantity, status="RESERVED", company_id=company_id, branch_id=item.branch_id,
                    created_by=user_id, updated_by=user_id))
            item.quantity = max(Decimal(item.quantity), Decimal(item.used_quantity) + Decimal(item.returned_quantity) + Decimal(item.reserved_quantity))
            item.updated_by = user_id
            self._sync_demand(item, user_id)
            db.session.commit()
            return item
        if Decimal(item.reserved_quantity) < quantity:
            db.session.rollback()
            raise ServiceOrderItemValidationError("Brak wystarczającej ilości zarezerwowanej do zwrotu.")
        if item.item_type == "PART":
            self.release_part_holds(item, quantity, user_id)
        db.session.add(CatalogStockMovement(
            item_type=item.item_type, part_id=item.item_id if item.item_type == "PART" else None,
            material_id=item.item_id if item.item_type == "MATERIAL" else None,
            service_order_id=order_id, movement_type="RELEASE", quantity=quantity,
            stock_before=product.current_stock, stock_after=product.current_stock,
            reference_type="SERVICE_ORDER_ITEM", reference_id=str(item.id),
            note="Zwolnienie niewykorzystanej rezerwacji", user_id=user_id,
            company_id=company_id, branch_id=item.branch_id,
        ))
        item.reserved_quantity = Decimal(item.reserved_quantity) - quantity
        item.returned_quantity = Decimal(item.returned_quantity) + quantity
        item.updated_by = user_id
        self._sync_demand(item, user_id)
        db.session.add(item)
        db.session.commit()
        return item

    def _lock_product(self, item_type, item_id, company_id):
        model = CatalogPart if item_type == "PART" else CatalogMaterial
        product = db.session.scalar(select(model).where(model.id == item_id, model.company_id == company_id,
            model.is_active.is_(True)).with_for_update().execution_options(populate_existing=True))
        if product is None:
            raise ServiceOrderItemNotFoundError("Nie znaleziono produktu.")
        return product

    def _sync_demand(self, item, user_id):
        from app.models.part_demand import PartDemand
        rows = db.session.scalars(select(PartDemand).where(
            PartDemand.service_order_item_id == item.id,
            PartDemand.company_id == item.company_id, PartDemand.is_active.is_(True),
            PartDemand.status != "CANCELLED")).all()
        for demand in rows:
            demand.reserved_quantity = item.reserved_quantity
            demand.missing_quantity = max(Decimal("0"), Decimal(demand.requested_quantity) - Decimal(item.used_quantity) - Decimal(item.returned_quantity) - Decimal(item.reserved_quantity))
            demand.updated_by = user_id

    def _claim_item(self, item, expected_version):
        version = int(expected_version) if expected_version is not None else item.version
        result = db.session.execute(update(ServiceOrderItem).where(
            ServiceOrderItem.id == item.id, ServiceOrderItem.version == version,
        ).values(version=ServiceOrderItem.version + 1).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            db.session.rollback()
            raise ServiceOrderItemValidationError("Pozycja została zmieniona. Odśwież zlecenie.")
        db.session.refresh(item)

    def _assert_no_pending_issue(self, item):
        from app.models.stock_issue import StockIssue
        from app.models.stock_issue_item import StockIssueItem
        pending = db.session.scalar(select(StockIssue.id).join(StockIssueItem).where(
            StockIssueItem.service_order_item_id == item.id, StockIssue.status == "DRAFT"))
        if pending:
            db.session.rollback()
            raise ServiceOrderItemValidationError("Najpierw rozlicz istniejący roboczy RW.")

    @staticmethod
    def release_part_holds(item, quantity, user_id):
        from sqlalchemy import inspect

        from app.models.inventory_reservation import InventoryReservation
        from app.models.service_order_part_reservation import ServiceOrderPartReservation

        # Release mirror legacy holds in both existing tables, not twice from stock.
        for model, column in ((ServiceOrderPartReservation, ServiceOrderPartReservation.part_id),
                              (InventoryReservation, InventoryReservation.inventory_item_id)):
            if not inspect(db.session.connection()).has_table(model.__tablename__):
                continue
            left = Decimal(quantity)
            rows = db.session.scalars(select(model).where(model.service_order_id == item.service_order_id,
                column == item.item_id, model.company_id == item.company_id,
                model.status == "RESERVED", model.is_active.is_(True)).order_by(model.id).with_for_update()).all()
            for row in rows:
                take = min(left, Decimal(row.quantity))
                row.quantity -= take
                left -= take
                row.updated_by = user_id
                if row.quantity == 0:
                    row.status = "RELEASED"
                    row.is_active = False
                if left <= 0:
                    break

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
        if self.repository.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id) is None:
            raise ServiceOrderItemNotFoundError("Nie znaleziono zlecenia.")
        item = self.repository.get_item(item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item is None or item.service_order_id != order_id:
            raise ServiceOrderItemNotFoundError("Nie znaleziono pozycji zlecenia.")
        return item

    def _serialize_item(self, item: ServiceOrderItem, resolved: ResolvedCatalogItem | None) -> dict[str, Any]:
        from sqlalchemy import inspect

        from app.models.stock_issue import StockIssue
        from app.models.stock_issue_item import StockIssueItem
        issues = []
        if inspect(db.session.connection()).has_table(StockIssue.__tablename__):
            issues = db.session.scalars(select(StockIssue).join(StockIssueItem).where(
                StockIssueItem.service_order_item_id == item.id, StockIssue.company_id == item.company_id,
                StockIssue.is_active.is_(True)).order_by(StockIssue.id)).all()
        held = self._reserved(item.item_type, item.item_id, item.company_id) if item.item_type != "SERVICE" else Decimal("0")
        available = None if resolved is None or resolved.current_stock is None else max(Decimal("0"), resolved.current_stock - held)
        waiting = max(Decimal("0"), Decimal(item.quantity) - Decimal(item.used_quantity) - Decimal(item.returned_quantity) - Decimal(item.reserved_quantity))
        vat_amount = self._line_vat(Decimal(item.total_net), Decimal(item.vat_rate))
        gross_amount = (Decimal(item.total_net) + vat_amount).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        return {
            "version": item.version,
            "waiting_quantity": str(waiting),
            "stock_reserved": str(held),
            "available_stock": None if available is None else str(available),
            "issues": [{"id": rw.id, "number": rw.issue_number, "status": rw.status} for rw in issues],
            "settlement_status": "RW roboczy" if any(rw.status == "DRAFT" for rw in issues) else ("Rozliczono" if item.used_quantity else ("Oczekuje / bez rezerwacji" if waiting else "Zarezerwowano")),
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
            part.current_stock = int(stock_after)
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
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount != amount.quantize(Decimal("1").scaleb(-places)):
                raise ValueError()
            return amount
        except Exception:
            raise ServiceOrderItemValidationError("Nieprawidłowa liczba lub zbyt duża dokładność.") from None

    @staticmethod
    def _reserved(item_type, item_id, company_id):
        from app.inventory.reservation_service import reserved_stock
        return reserved_stock(item_type=item_type, item_id=item_id, company_id=company_id)
