from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.extensions import db
from app.models.inventory_part import InventoryPart
from app.models.inventory_stock_operation import INVENTORY_OPERATION_TYPE_LABELS
from app.models.service_order_part_usage import ServiceOrderPartUsage

from .exceptions import InventoryNotFoundError, InventoryValidationError
from .repository import InventoryRepository


THREE_DP = Decimal("0.001")
TWO_DP = Decimal("0.01")


@dataclass(slots=True)
class OrderUsageTotals:
    net: Decimal
    vat: Decimal
    gross: Decimal


class InventoryService:
    def __init__(self, repository: InventoryRepository | None = None) -> None:
        self.repository = repository or InventoryRepository()

    def list_parts(self, *, page: int, per_page: int, company_id: int | None, query_text: str | None) -> dict[str, Any]:
        return self.repository.list_parts(
            page=max(page, 1),
            per_page=max(per_page, 1),
            company_id=company_id,
            query_text=(query_text or "").strip() or None,
        )

    def get_part(self, part_id: int, *, company_id: int | None) -> InventoryPart | None:
        return self.repository.get_part(part_id, company_id=company_id)

    def create_part(self, data: dict[str, Any], *, company_id: int | None, branch_id: int | None, user_id: int | None) -> InventoryPart:
        if company_id is None:
            raise InventoryValidationError("Brak identyfikatora firmy.")

        payload = self._normalize_part_payload(data)
        existing = self.repository.get_by_code(payload["part_code"], company_id=company_id)
        if existing is not None:
            raise InventoryValidationError("Część o podanym kodzie już istnieje.")

        payload["company_id"] = company_id
        payload["branch_id"] = branch_id
        payload["quantity_total"] = payload["current_stock"]
        payload["quantity_reserved"] = Decimal("0")
        payload["created_by"] = user_id
        payload["updated_by"] = user_id

        part = self.repository.create_part(payload)
        if part.current_stock > Decimal("0"):
            self._create_stock_operation(
                part=part,
                operation_type="INVENTORY",
                quantity=part.current_stock,
                document_number="OTWARCIE",
                comment="Stan początkowy podczas zakładania karty.",
                user_id=user_id,
                service_order_id=None,
                override_before=Decimal("0"),
                override_after=Decimal(part.current_stock),
            )

        db.session.commit()
        return part

    def update_part(
        self,
        part_id: int,
        data: dict[str, Any],
        *,
        company_id: int | None,
        branch_id: int | None,
        user_id: int | None,
    ) -> InventoryPart:
        part = self.repository.get_part(part_id, company_id=company_id)
        if part is None:
            raise InventoryNotFoundError("Nie znaleziono części.")

        payload = self._normalize_part_payload(data)
        existing = self.repository.get_by_code(payload["part_code"], company_id=company_id)
        if existing is not None and existing.id != part.id:
            raise InventoryValidationError("Część o podanym kodzie już istnieje.")

        stock_before = Decimal(part.current_stock)
        stock_after = payload["current_stock"]

        payload["branch_id"] = branch_id
        payload["quantity_total"] = stock_after
        payload["quantity_reserved"] = Decimal(part.quantity_reserved)
        payload["updated_by"] = user_id
        self.repository.update_part(part, payload)

        if stock_before != stock_after:
            delta = (stock_after - stock_before).quantize(THREE_DP, rounding=ROUND_HALF_UP)
            operation_type = "ADJUSTMENT" if delta != Decimal("0") else "INVENTORY"
            self._create_stock_operation(
                part=part,
                operation_type=operation_type,
                quantity=delta,
                document_number="KOREKTA",
                comment="Zmiana stanu podczas edycji karty części.",
                user_id=user_id,
                service_order_id=None,
                override_before=stock_before,
                override_after=stock_after,
            )

        db.session.commit()
        return part

    def register_operation(
        self,
        *,
        part_id: int,
        operation_type: str,
        quantity_raw: Any,
        document_number: str | None,
        comment: str | None,
        company_id: int | None,
        branch_id: int | None,
        user_id: int | None,
    ):
        part = self.repository.get_part(part_id, company_id=company_id)
        if part is None:
            raise InventoryNotFoundError("Nie znaleziono części.")

        operation_key = (operation_type or "").strip().upper()
        if operation_key not in INVENTORY_OPERATION_TYPE_LABELS:
            raise InventoryValidationError("Nieprawidłowy typ operacji magazynowej.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if operation_key in {"RECEIPT", "ISSUE", "INVENTORY"} and quantity < Decimal("0"):
            raise InventoryValidationError("Ilość nie może być ujemna dla tej operacji.")
        if quantity == Decimal("0"):
            raise InventoryValidationError("Ilość nie może być równa 0.")

        operation = self._create_stock_operation(
            part=part,
            operation_type=operation_key,
            quantity=quantity,
            document_number=(document_number or "").strip() or None,
            comment=(comment or "").strip() or None,
            user_id=user_id,
            service_order_id=None,
            branch_id=branch_id,
        )
        db.session.commit()
        return operation

    def consume_for_order(
        self,
        *,
        order_id: int,
        part_id: int,
        quantity_raw: Any,
        unit_net_price_raw: Any,
        company_id: int | None,
        branch_id: int | None,
        user_id: int | None,
    ) -> ServiceOrderPartUsage:
        part = self.repository.get_part(part_id, company_id=company_id)
        if part is None:
            raise InventoryNotFoundError("Nie znaleziono części.")

        order = self.repository.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise InventoryNotFoundError("Nie znaleziono zlecenia.")

        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise InventoryValidationError("Ilość zużycia musi być większa od 0.")

        default_price = Decimal(part.sale_price_net)
        unit_net_price = self._to_decimal(unit_net_price_raw, places=2, default=default_price)
        if unit_net_price < Decimal("0"):
            raise InventoryValidationError("Cena jednostkowa netto nie może być ujemna.")

        vat_rate = Decimal(part.vat_rate)
        net_value = (quantity * unit_net_price).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        vat_value = (net_value * vat_rate / Decimal("100")).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        gross_value = (net_value + vat_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)

        operation = self._create_stock_operation(
            part=part,
            operation_type="ISSUE",
            quantity=quantity,
            document_number=f"SO-{order.id}",
            comment="Automatyczne wydanie części do zlecenia serwisowego.",
            user_id=user_id,
            service_order_id=order.id,
            branch_id=branch_id,
        )

        usage = self.repository.create_order_usage(
            {
                "service_order_id": order.id,
                "part_id": part.id,
                "stock_operation_id": operation.id,
                "quantity": quantity,
                "unit_net_price": unit_net_price,
                "vat_rate": vat_rate,
                "net_value": net_value,
                "vat_value": vat_value,
                "gross_value": gross_value,
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        db.session.commit()
        return usage

    def list_part_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.repository.list_part_choices(company_id=company_id)

    def list_order_usages(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceOrderPartUsage]:
        return self.repository.list_order_usages(order_id, company_id=company_id, branch_id=branch_id)

    def compute_order_usage_totals(self, usages: list[ServiceOrderPartUsage]) -> OrderUsageTotals:
        net = Decimal("0")
        vat = Decimal("0")
        gross = Decimal("0")
        for usage in usages:
            net += Decimal(usage.net_value)
            vat += Decimal(usage.vat_value)
            gross += Decimal(usage.gross_value)
        return OrderUsageTotals(
            net=net.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            vat=vat.quantize(TWO_DP, rounding=ROUND_HALF_UP),
            gross=gross.quantize(TWO_DP, rounding=ROUND_HALF_UP),
        )

    def low_stock_count(self, *, company_id: int | None) -> int:
        return self.repository.low_stock_count(company_id=company_id)

    def low_stock_list(self, *, company_id: int | None) -> list[InventoryPart]:
        return self.repository.low_stock_list(company_id=company_id)

    def stock_summary(self, *, company_id: int | None) -> dict[str, Decimal]:
        return self.repository.stock_summary(company_id=company_id)

    def list_part_operations(self, part_id: int, *, company_id: int | None):
        return self.repository.list_part_operations(part_id, company_id=company_id)

    def _create_stock_operation(
        self,
        *,
        part: InventoryPart,
        operation_type: str,
        quantity: Decimal,
        document_number: str | None,
        comment: str | None,
        user_id: int | None,
        service_order_id: int | None,
        branch_id: int | None = None,
        override_before: Decimal | None = None,
        override_after: Decimal | None = None,
    ):
        stock_before = override_before if override_before is not None else Decimal(part.current_stock)

        if override_after is not None:
            stock_after = override_after
        elif operation_type == "RECEIPT":
            stock_after = stock_before + quantity
        elif operation_type == "ISSUE":
            stock_after = stock_before - quantity
        elif operation_type == "INVENTORY":
            stock_after = quantity
        else:
            stock_after = stock_before + quantity

        if stock_after < Decimal("0"):
            raise InventoryValidationError("Stan magazynowy nie może spaść poniżej 0.")

        part.current_stock = stock_after.quantize(THREE_DP, rounding=ROUND_HALF_UP)
        db.session.add(part)
        db.session.flush()

        stored_quantity = quantity
        if operation_type == "ISSUE":
            stored_quantity = quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP)
        elif operation_type == "RECEIPT":
            stored_quantity = quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP)
        elif operation_type == "INVENTORY":
            stored_quantity = quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP)
        else:
            stored_quantity = quantity.quantize(THREE_DP, rounding=ROUND_HALF_UP)

        return self.repository.create_stock_operation(
            {
                "part_id": part.id,
                "user_id": user_id,
                "service_order_id": service_order_id,
                "operation_type": operation_type,
                "quantity": stored_quantity,
                "stock_before": stock_before.quantize(THREE_DP, rounding=ROUND_HALF_UP),
                "stock_after": part.current_stock,
                "document_number": document_number,
                "comment": comment,
                "company_id": part.company_id,
                "branch_id": branch_id if branch_id is not None else part.branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )

    def _normalize_part_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "part_code": self._require_text(data.get("part_code"), "Kod części jest wymagany.", max_len=80).upper(),
            "name": self._require_text(data.get("name"), "Nazwa jest wymagana.", max_len=255),
            "category": self._optional_text(data.get("category"), max_len=120),
            "manufacturer": self._optional_text(data.get("manufacturer"), max_len=120),
            "catalog_number": self._optional_text(data.get("catalog_number"), max_len=120),
            "barcode": self._optional_text(data.get("barcode"), max_len=120),
            "description": self._optional_text(data.get("description"), max_len=10000),
            "unit": self._require_text(data.get("unit"), "Jednostka jest wymagana.", max_len=40),
            "minimum_stock": self._to_decimal(data.get("minimum_stock"), places=3),
            "current_stock": self._to_decimal(data.get("current_stock"), places=3),
            "location": self._optional_text(data.get("location"), max_len=120),
            "purchase_price_net": self._to_decimal(data.get("purchase_price_net"), places=2),
            "sale_price_net": self._to_decimal(data.get("sale_price_net"), places=2),
            "vat_rate": self._to_decimal(data.get("vat_rate"), places=2),
            "supplier": self._optional_text(data.get("supplier"), max_len=180),
            "image_path": self._optional_text(data.get("image_path"), max_len=500),
            "is_record_active": self._to_bool(data.get("is_record_active")),
        }
        if payload["minimum_stock"] < Decimal("0") or payload["current_stock"] < Decimal("0"):
            raise InventoryValidationError("Stany magazynowe nie mogą być ujemne.")
        if payload["purchase_price_net"] < Decimal("0") or payload["sale_price_net"] < Decimal("0"):
            raise InventoryValidationError("Ceny nie mogą być ujemne.")
        if payload["vat_rate"] < Decimal("0"):
            raise InventoryValidationError("Stawka VAT nie może być ujemna.")
        return payload

    def _require_text(self, value: Any, message: str, *, max_len: int) -> str:
        text = (value or "").strip()
        if not text:
            raise InventoryValidationError(message)
        if len(text) > max_len:
            raise InventoryValidationError("Wartość przekracza dopuszczalną długość pola.")
        return text

    def _optional_text(self, value: Any, *, max_len: int) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        if len(text) > max_len:
            raise InventoryValidationError("Wartość przekracza dopuszczalną długość pola.")
        return text

    def _to_decimal(self, value: Any, *, places: int, default: Decimal | None = None) -> Decimal:
        if value is None or (isinstance(value, str) and not value.strip()):
            if default is not None:
                return default
            return Decimal("0").quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_UP)
        try:
            decimal_value = Decimal(str(value).replace(",", "."))
        except Exception as exc:
            raise InventoryValidationError("Nieprawidłowa wartość numeryczna.") from exc
        quantum = Decimal("1").scaleb(-places)
        return decimal_value.quantize(quantum, rounding=ROUND_HALF_UP)

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "tak", "yes", "on"}
