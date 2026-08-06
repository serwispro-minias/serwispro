from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.extensions import db
from app.models.service_estimate import SERVICE_ESTIMATE_STATUS_CHOICES, SERVICE_ESTIMATE_STATUS_LABELS, ServiceEstimate
from app.models.service_estimate_item import SERVICE_ESTIMATE_ITEM_SOURCE_CHOICES, SERVICE_ESTIMATE_ITEM_SOURCE_LABELS, ServiceEstimateItem
from app.models.service_order_item import ServiceOrderItem
from app.orders.print_repository import ServiceOrderPrintRepository

from .pdf_generator import EstimatePdfGenerator
from .print_service import EstimateDocument, EstimatePrintService
from .repository import EstimateRepository


TWO_DP = Decimal("0.01")


@dataclass(slots=True)
class EstimateTotals:
    parts_net: Decimal
    materials_net: Decimal
    services_net: Decimal
    discount_total: Decimal
    net_total: Decimal
    vat_total: Decimal
    gross_total: Decimal


class EstimateError(Exception):
    pass


class EstimateNotFoundError(EstimateError):
    pass


class EstimateValidationError(EstimateError):
    pass


class EstimateService:
    def __init__(self, repository: EstimateRepository | None = None, print_service: EstimatePrintService | None = None) -> None:
        self.repository = repository or EstimateRepository()
        self.print_service = print_service or EstimatePrintService(self.repository, ServiceOrderPrintRepository(), EstimatePdfGenerator())

    def get_status_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ESTIMATE_STATUS_CHOICES)

    def get_status_labels(self) -> dict[str, str]:
        return dict(SERVICE_ESTIMATE_STATUS_LABELS)

    def get_item_source_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ESTIMATE_ITEM_SOURCE_CHOICES)

    def get_item_source_labels(self) -> dict[str, str]:
        return dict(SERVICE_ESTIMATE_ITEM_SOURCE_LABELS)

    def list_estimates(self, *, company_id: int | None, branch_id: int | None) -> list[ServiceEstimate]:
        return self.repository.list_estimates(company_id=company_id, branch_id=branch_id)

    def list_estimates_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceEstimate]:
        return self.repository.list_estimates_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)

    def get_estimate(self, *, estimate_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimate | None:
        return self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)

    def get_latest_estimate(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimate | None:
        return self.repository.get_latest_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)

    def create_from_order(
        self,
        *,
        order_id: int,
        company_id: int | None,
        branch_id: int | None,
        user_id: int | None,
        valid_until: date | None = None,
        notes: str | None = None,
    ) -> ServiceEstimate:
        order = self.repository.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise EstimateNotFoundError("Nie znaleziono zlecenia.")

        version_number = self.repository.get_next_version_number(order_id=order.id, company_id=company_id, branch_id=branch_id)
        estimate = self.repository.create_estimate(
            {
                "service_order_id": order.id,
                "version_number": version_number,
                "status": "DRAFT",
                "title": f"Kosztorys naprawy {order.order_number}",
                "valid_until": valid_until or (date.today() + timedelta(days=14)),
                "notes": (notes or "").strip() or None,
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._populate_from_order_sources(estimate=estimate, order_id=order.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        self.recalculate_estimate(estimate_id=estimate.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.commit()
        return estimate

    def add_manual_item(
        self,
        *,
        estimate_id: int,
        company_id: int | None,
        branch_id: int | None,
        user_id: int | None,
        name: str,
        quantity_raw: Any,
        unit: str | None,
        unit_net_price_raw: Any,
        discount_percent_raw: Any | None,
        vat_rate_raw: Any | None,
        description: str | None,
        sort_order: int | None,
    ) -> ServiceEstimate:
        estimate = self._ensure_editable_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        quantity = self._to_decimal(quantity_raw, places=3)
        if quantity <= Decimal("0"):
            raise EstimateValidationError("Ilość musi być większa od zera.")
        unit_net_price = self._to_decimal(unit_net_price_raw, places=2)
        if unit_net_price < Decimal("0"):
            raise EstimateValidationError("Cena netto nie może być ujemna.")
        discount_percent = self._to_decimal(discount_percent_raw, places=2, default=Decimal("0"))
        vat_rate = self._to_decimal(vat_rate_raw, places=2, default=Decimal("23"))
        item = self.repository.create_item(
            {
                "estimate_id": estimate.id,
                "sort_order": int(sort_order) if sort_order is not None else len(estimate.items) + 1,
                "source_type": "MANUAL",
                "source_id": None,
                "code": None,
                "name": name.strip(),
                "description": (description or "").strip() or None,
                "quantity": quantity,
                "unit": (unit or "szt.").strip() or "szt.",
                "unit_net_price": unit_net_price,
                "discount_percent": discount_percent,
                "vat_rate": vat_rate,
                "net_value": Decimal("0"),
                "vat_value": Decimal("0"),
                "gross_value": Decimal("0"),
                "is_manual": True,
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._update_item_totals(item)
        self.recalculate_estimate(estimate_id=estimate.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.commit()
        return estimate

    def delete_item(self, *, estimate_id: int, item_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self._ensure_editable_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        item = self._get_item(estimate_id=estimate.id, item_id=item_id, company_id=company_id, branch_id=branch_id)
        if item is None:
            raise EstimateNotFoundError("Nie znaleziono pozycji kosztorysu.")
        self.repository.delete_item(item)
        self.recalculate_estimate(estimate_id=estimate.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.commit()
        return estimate

    def reorder_items(self, *, estimate_id: int, item_ids: list[int], company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self._ensure_editable_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        items_by_id = {item.id: item for item in estimate.items}
        for index, item_id in enumerate(item_ids, start=1):
            item = items_by_id.get(item_id)
            if item is not None:
                item.sort_order = index
                item.updated_by = user_id
                self.repository.save(item)
        self.recalculate_estimate(estimate_id=estimate.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.commit()
        return estimate

    def recalculate_estimate(self, *, estimate_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self._ensure_editable_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.expire(estimate, ["items"])

        totals = EstimateTotals(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
        for item in sorted(estimate.items, key=lambda row: (row.sort_order, row.id)):
            self._update_item_totals(item)
            discount_amount = (Decimal(item.quantity) * Decimal(item.unit_net_price)) - Decimal(item.net_value)
            totals.discount_total += discount_amount
            totals.vat_total += Decimal(item.vat_value)
            totals.gross_total += Decimal(item.gross_value)
            totals.net_total += Decimal(item.net_value)
            if item.source_type == "PART":
                totals.parts_net += Decimal(item.net_value)
            elif item.source_type == "MATERIAL":
                totals.materials_net += Decimal(item.net_value)
            else:
                totals.services_net += Decimal(item.net_value)
            self.repository.save(item)

        estimate.parts_net = totals.parts_net.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.materials_net = totals.materials_net.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.services_net = totals.services_net.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.discount_total = totals.discount_total.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.net_total = totals.net_total.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.vat_total = totals.vat_total.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.gross_total = totals.gross_total.quantize(TWO_DP, rounding=ROUND_HALF_UP)
        estimate.updated_by = user_id
        self.repository.save(estimate)

        order = estimate.service_order
        if order is not None:
            order.estimated_cost = estimate.gross_total
            order.updated_by = user_id
            self.repository.save(order)
        return estimate

    def send_to_client(self, *, estimate_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            raise EstimateNotFoundError("Nie znaleziono kosztorysu.")
        estimate.status = "SENT"
        estimate.sent_at = datetime.now(timezone.utc)
        estimate.updated_by = user_id
        self.repository.save(estimate)
        db.session.commit()
        return estimate

    def clone_for_revision(self, *, estimate_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            raise EstimateNotFoundError("Nie znaleziono kosztorysu.")
        version_number = self.repository.get_next_version_number(order_id=estimate.service_order_id, company_id=company_id, branch_id=branch_id)
        clone = self.repository.create_estimate(
            {
                "service_order_id": estimate.service_order_id,
                "parent_estimate_id": estimate.id,
                "version_number": version_number,
                "status": "DRAFT",
                "title": estimate.title,
                "notes": estimate.notes,
                "valid_until": estimate.valid_until,
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        for item in estimate.items:
            self.repository.create_item(
                {
                    "estimate_id": clone.id,
                    "sort_order": item.sort_order,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "code": item.code,
                    "name": item.name,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "unit_net_price": item.unit_net_price,
                    "discount_percent": item.discount_percent,
                    "vat_rate": item.vat_rate,
                    "net_value": item.net_value,
                    "vat_value": item.vat_value,
                    "gross_value": item.gross_value,
                    "is_manual": item.is_manual,
                    "company_id": company_id,
                    "branch_id": branch_id,
                    "created_by": user_id,
                    "updated_by": user_id,
                }
            )
        self.recalculate_estimate(estimate_id=clone.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        db.session.commit()
        return clone

    def build_pdf(self, *, estimate_id: int, company_id: int, branch_id: int | None, upload_root: Any) -> EstimateDocument | None:
        return self.print_service.build_pdf(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id, upload_root=upload_root)

    def _populate_from_order_sources(self, *, estimate: ServiceEstimate, order_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> None:
        sources = self.repository.get_order_sources(order_id=order_id, company_id=company_id, branch_id=branch_id)
        sort_order = 1
        for reservation in sources["parts"]:
            part = reservation.part
            if part is None:
                continue
            item = self.repository.create_item(
                {
                    "estimate_id": estimate.id,
                    "sort_order": sort_order,
                    "source_type": "PART",
                    "source_id": reservation.part_id,
                    "code": part.code,
                    "name": part.name,
                    "description": part.description,
                    "quantity": reservation.quantity,
                    "unit": part.unit,
                    "unit_net_price": part.sale_price_net,
                    "discount_percent": Decimal("0"),
                    "vat_rate": part.vat_rate,
                    "net_value": Decimal("0"),
                    "vat_value": Decimal("0"),
                    "gross_value": Decimal("0"),
                    "is_manual": False,
                    "company_id": company_id,
                    "branch_id": branch_id,
                    "created_by": user_id,
                    "updated_by": user_id,
                }
            )
            self._update_item_totals(item)
            sort_order += 1

        for usage in sources["materials"]:
            material = usage.material
            if material is None:
                continue
            item = self.repository.create_item(
                {
                    "estimate_id": estimate.id,
                    "sort_order": sort_order,
                    "source_type": "MATERIAL",
                    "source_id": usage.material_id,
                    "code": material.code,
                    "name": material.name,
                    "description": material.description,
                    "quantity": usage.quantity,
                    "unit": material.unit,
                    "unit_net_price": usage.unit_net_price,
                    "discount_percent": Decimal("0"),
                    "vat_rate": usage.vat_rate,
                    "net_value": Decimal("0"),
                    "vat_value": Decimal("0"),
                    "gross_value": Decimal("0"),
                    "is_manual": False,
                    "company_id": company_id,
                    "branch_id": branch_id,
                    "created_by": user_id,
                    "updated_by": user_id,
                }
            )
            self._update_item_totals(item)
            sort_order += 1

        for line in sources["services"]:
            service_item = line.service_item
            if service_item is None:
                continue
            item = self.repository.create_item(
                {
                    "estimate_id": estimate.id,
                    "sort_order": sort_order,
                    "source_type": "SERVICE",
                    "source_id": line.service_item_id,
                    "code": service_item.code,
                    "name": service_item.name,
                    "description": service_item.description,
                    "quantity": line.quantity,
                    "unit": "szt.",
                    "unit_net_price": line.unit_net_price,
                    "discount_percent": Decimal("0"),
                    "vat_rate": line.vat_rate,
                    "net_value": Decimal("0"),
                    "vat_value": Decimal("0"),
                    "gross_value": Decimal("0"),
                    "is_manual": False,
                    "company_id": company_id,
                    "branch_id": branch_id,
                    "created_by": user_id,
                    "updated_by": user_id,
                }
            )
            self._update_item_totals(item)
            sort_order += 1

    def _ensure_editable_estimate(self, *, estimate_id: int, company_id: int | None, branch_id: int | None, user_id: int | None) -> ServiceEstimate:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            raise EstimateNotFoundError("Nie znaleziono kosztorysu.")
        if estimate.status != "DRAFT":
            estimate = self.clone_for_revision(estimate_id=estimate.id, company_id=company_id, branch_id=branch_id, user_id=user_id)
        return estimate

    def _get_item(self, *, estimate_id: int, item_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimateItem | None:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            return None
        for item in estimate.items:
            if item.id == item_id:
                return item
        return None

    def _update_item_totals(self, item: ServiceEstimateItem) -> None:
        quantity = Decimal(item.quantity)
        unit_net_price = Decimal(item.unit_net_price)
        discount_percent = Decimal(item.discount_percent)
        vat_rate = Decimal(item.vat_rate)
        discounted = unit_net_price * (Decimal("1") - (discount_percent / Decimal("100")))
        net_value = (quantity * discounted).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        vat_value = (net_value * (vat_rate / Decimal("100"))).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        gross_value = (net_value + vat_value).quantize(TWO_DP, rounding=ROUND_HALF_UP)
        item.net_value = net_value
        item.vat_value = vat_value
        item.gross_value = gross_value

    def _to_decimal(self, value: Any, *, places: int, default: Decimal | None = None) -> Decimal:
        if value is None or (isinstance(value, str) and not value.strip()):
            if default is not None:
                return default
            return Decimal("0")
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0." + "0" * (places - 1) + "1"), rounding=ROUND_HALF_UP) if places else value
        return Decimal(str(value))


estimate_service = EstimateService()
