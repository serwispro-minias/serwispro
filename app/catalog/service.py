from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.catalog_category import CatalogCategory
from app.models.catalog_manufacturer import CatalogManufacturer
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_service_item import CatalogServiceItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.inventory_reservation import InventoryReservation, InventoryReservationStatusEnum
from app.models.service_order_material_usage import ServiceOrderMaterialUsage
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.service_order_service_line import ServiceOrderServiceLine
from app.models.vat_rate import VatRate

from .exceptions import CatalogNotFoundError, CatalogValidationError
from .repository import (
    CategoriesRepository,
    ManufacturersRepository,
    MaterialsRepository,
    PartsRepository,
    ServicesRepository,
    StockRepository,
    SuppliersRepository,
    VatRatesRepository,
)


@dataclass(slots=True)
class ReservePartForOrderResult:
    reservation: ServiceOrderPartReservation | None
    demand_id: int | None
    demand_missing_quantity: Decimal | None

    @property
    def demand_created(self) -> bool:
        return self.demand_id is not None


def _safe_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _prices(qty: Decimal, unit_net: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    net = (qty * unit_net).quantize(Decimal("0.01"))
    vat = (net * (vat_rate / Decimal("100"))).quantize(Decimal("0.01"))
    gross = (net + vat).quantize(Decimal("0.01"))
    return net, vat, gross


class CatalogService:
    def __init__(self) -> None:
        self.categories = CategoriesRepository()
        self.suppliers = SuppliersRepository()
        self.manufacturers = ManufacturersRepository()
        self.vat_rates = VatRatesRepository()
        self.parts = PartsRepository()
        self.materials = MaterialsRepository()
        self.services = ServicesRepository()
        self.stock = StockRepository()

    def _tenant_payload(self, *, company_id: int | None, branch_id: int | None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if company_id is not None:
            payload["company_id"] = company_id
        if branch_id is not None:
            payload["branch_id"] = branch_id
        return payload

    def _last_demand_id_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> int | None:
        from app.models.part_demand import PartDemand

        query = db.session.query(PartDemand).filter(PartDemand.service_order_id == order_id, PartDemand.is_active.is_(True))
        if company_id is not None:
            query = query.filter(PartDemand.company_id == company_id)
        if branch_id is not None:
            query = query.filter(PartDemand.branch_id == branch_id)
        demand = query.order_by(PartDemand.created_at.desc(), PartDemand.id.desc()).first()
        return demand.id if demand is not None else None

    def list_entities(self, repository: Any, *, page: int, per_page: int, company_id: int | None, query_text: str | None) -> dict[str, Any]:
        return repository.list_paginated(page=page, per_page=per_page, company_id=company_id, query_text=query_text)

    def category_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.categories.list_choices(company_id=company_id)

    def supplier_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.suppliers.list_choices(company_id=company_id)

    def manufacturer_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.manufacturers.list_choices(company_id=company_id)

    def vat_rate_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.vat_rates.list_choices(company_id=company_id)

    def part_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.parts.list_choices(company_id=company_id)

    def material_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.materials.list_choices(company_id=company_id)

    def service_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        return self.services.list_choices(company_id=company_id)

    def create_entity(self, repository: Any, data: dict[str, Any], *, company_id: int | None, branch_id: int | None) -> Any:
        data = self._sanitize_form_payload(data)
        data.update(self._tenant_payload(company_id=company_id, branch_id=branch_id))
        data = self._normalize_foreign_keys(data)
        self._validate_part_vat(repository, data, company_id=company_id)
        self._assert_unique(repository, data.get("code"), company_id=company_id)
        entity = repository.create(data)
        db.session.commit()
        return entity

    def update_entity(self, repository: Any, entity_id: int, data: dict[str, Any], *, company_id: int | None) -> Any:
        entity = repository.get(entity_id, company_id=company_id)
        if entity is None:
            raise CatalogNotFoundError("Nie znaleziono rekordu.")

        data = self._sanitize_form_payload(data)
        data = self._normalize_foreign_keys(data)
        self._validate_part_vat(repository, data, company_id=company_id)

        code = data.get("code")
        if code and getattr(entity, "code", None) != code:
            self._assert_unique(repository, code, company_id=company_id)

        updated = repository.update(entity, data)
        db.session.commit()
        return updated

    def _sanitize_form_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        # Flask-WTF adds helper fields that are not model columns.
        return {k: v for k, v in data.items() if k not in {"csrf_token", "submit"}}

    def delete_entity(self, repository: Any, entity_id: int, *, company_id: int | None) -> None:
        entity = repository.get(entity_id, company_id=company_id)
        if entity is None:
            raise CatalogNotFoundError("Nie znaleziono rekordu.")
        repository.soft_delete(entity)
        db.session.commit()

    def get_entity_or_404(self, repository: Any, entity_id: int, *, company_id: int | None) -> Any:
        entity = repository.get(entity_id, company_id=company_id)
        if entity is None:
            raise CatalogNotFoundError("Nie znaleziono rekordu.")
        return entity

    def add_stock_movement(
        self,
        *,
        entity_type: str,
        entity_id: int,
        movement_type: str,
        quantity: Decimal,
        reference_type: str | None,
        reference_id: str | None,
        note: str | None,
        user_id: int | None,
        company_id: int | None,
        branch_id: int | None,
    ) -> CatalogStockMovement:
        if quantity <= Decimal("0"):
            raise CatalogValidationError("Ilość musi być większa od zera.")

        tenant = self._tenant_payload(company_id=company_id, branch_id=branch_id)

        if entity_type == "part":
            part = self.parts.get(entity_id, company_id=company_id)
            if part is None:
                raise CatalogNotFoundError("Nie znaleziono części.")

            if movement_type in {"ISSUE", "RESERVATION", "SALE", "AUTO_ISSUE"} and Decimal(part.current_stock) < quantity:
                raise CatalogValidationError("Brak wystarczającego stanu magazynowego części.")

            stock_before, stock_after = self.stock.update_part_stock(part, quantity=quantity, movement_type=movement_type)
            movement = self.stock.create_movement(
                {
                    **tenant,
                    "item_type": "PART",
                    "part_id": part.id,
                    "movement_type": movement_type,
                    "quantity": quantity,
                    "stock_before": stock_before,
                    "stock_after": stock_after,
                    "reference_type": reference_type,
                    "reference_id": reference_id,
                    "note": note,
                    "user_id": user_id,
                }
            )
            db.session.commit()
            return movement

        material = self.materials.get(entity_id, company_id=company_id)
        if material is None:
            raise CatalogNotFoundError("Nie znaleziono materiału.")

        if movement_type in {"ISSUE", "AUTO_ISSUE"} and Decimal(material.current_stock) < quantity:
            raise CatalogValidationError("Brak wystarczającego stanu magazynowego materiału.")

        stock_before, stock_after = self.stock.update_material_stock(material, quantity=quantity, movement_type=movement_type)
        movement = self.stock.create_movement(
            {
                **tenant,
                "item_type": "MATERIAL",
                "material_id": material.id,
                "movement_type": movement_type,
                "quantity": quantity,
                "stock_before": stock_before,
                "stock_after": stock_after,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "note": note,
                "user_id": user_id,
            }
        )
        db.session.commit()
        return movement

    def reserve_part_for_order(
        self,
        *,
        order_id: int,
        part_id: int,
        quantity: Decimal,
        user_id: int | None,
        company_id: int | None,
        branch_id: int | None,
    ) -> ReservePartForOrderResult:
        if quantity <= Decimal("0"):
            raise CatalogValidationError("Ilość rezerwacji musi być większa od zera.")

        order = self.stock.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise CatalogNotFoundError("Nie znaleziono zlecenia serwisowego.")

        part = self.parts.get(part_id, company_id=company_id)
        if part is None:
            raise CatalogNotFoundError("Nie znaleziono części.")

        current_stock = Decimal(part.current_stock)
        reserved_quantity = min(quantity, current_stock)
        missing_quantity = max(Decimal("0"), quantity - reserved_quantity)

        if current_stock <= Decimal("0"):
            if company_id is None:
                raise CatalogValidationError("Brak kontekstu firmy dla zapotrzebowania na część.")
            from app.part_demands.service import PartDemandService

            demand_result = PartDemandService().create_or_update_from_shortage(
                order_id=order.id,
                part_id=part.id,
                requested_quantity=quantity,
                available_quantity=current_stock,
                company_id=company_id,
                branch_id=branch_id,
                actor_id=user_id,
            )
            return ReservePartForOrderResult(
                reservation=None,
                demand_id=demand_result.demand.id,
                demand_missing_quantity=demand_result.missing_quantity,
            )

        movement = self.add_stock_movement(
            entity_type="part",
            entity_id=part.id,
            movement_type="RESERVATION",
            quantity=reserved_quantity,
            reference_type="SERVICE_ORDER",
            reference_id=str(order.id),
            note="Rezerwacja części dla zlecenia",
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )

        reservation = self.stock.reserve_part(
            {
                **self._tenant_payload(company_id=company_id, branch_id=branch_id),
                "service_order_id": order.id,
                "part_id": part.id,
                "quantity": reserved_quantity,
                "status": "RESERVED",
            }
        )

        inventory_reservation = InventoryReservation()
        inventory_reservation.inventory_item_id = part.id
        inventory_reservation.service_order_id = order.id
        inventory_reservation.quantity = reserved_quantity
        inventory_reservation.reserved_by = user_id
        inventory_reservation.status = InventoryReservationStatusEnum.RESERVED.value
        if company_id is not None:
            inventory_reservation.company_id = company_id
        inventory_reservation.branch_id = branch_id
        inventory_reservation.created_by = user_id
        inventory_reservation.updated_by = user_id
        db.session.add(inventory_reservation)

        if missing_quantity > Decimal("0") and company_id is not None:
            from app.part_demands.service import PartDemandService

            demand_result = PartDemandService().create_or_update_from_shortage(
                order_id=order.id,
                part_id=part.id,
                requested_quantity=quantity,
                available_quantity=current_stock,
                company_id=company_id,
                branch_id=branch_id,
                actor_id=user_id,
            )
            db.session.flush()
            _ = demand_result

        _ = movement
        db.session.commit()
        return ReservePartForOrderResult(
            reservation=reservation,
            demand_id=None if missing_quantity <= Decimal("0") else self._last_demand_id_for_order(order_id=order.id, company_id=company_id, branch_id=branch_id),
            demand_missing_quantity=missing_quantity if missing_quantity > Decimal("0") else None,
        )

    def issue_material_to_order(
        self,
        *,
        order_id: int,
        material_id: int,
        quantity: Decimal,
        user_id: int | None,
        company_id: int | None,
        branch_id: int | None,
    ) -> ServiceOrderMaterialUsage:
        if quantity <= Decimal("0"):
            raise CatalogValidationError("Ilość zużycia musi być większa od zera.")

        order = self.stock.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise CatalogNotFoundError("Nie znaleziono zlecenia serwisowego.")

        material = self.materials.get(material_id, company_id=company_id)
        if material is None:
            raise CatalogNotFoundError("Nie znaleziono materiału.")

        movement = self.add_stock_movement(
            entity_type="material",
            entity_id=material.id,
            movement_type="AUTO_ISSUE",
            quantity=quantity,
            reference_type="SERVICE_ORDER",
            reference_id=str(order.id),
            note="Automatyczne odpisanie materiału",
            user_id=user_id,
            company_id=company_id,
            branch_id=branch_id,
        )

        unit_net = Decimal(material.purchase_price_net)
        vat_rate = Decimal(material.vat_rate)
        net, vat, gross = _prices(quantity, unit_net, vat_rate)

        usage = self.stock.create_material_usage(
            {
                **self._tenant_payload(company_id=company_id, branch_id=branch_id),
                "service_order_id": order.id,
                "material_id": material.id,
                "stock_movement_id": movement.id,
                "quantity": quantity,
                "unit_net_price": unit_net,
                "vat_rate": vat_rate,
                "net_value": net,
                "vat_value": vat,
                "gross_value": gross,
            }
        )
        db.session.commit()
        return usage

    def add_service_line_to_order(
        self,
        *,
        order_id: int,
        service_item_id: int,
        quantity: Decimal,
        company_id: int | None,
        branch_id: int | None,
    ) -> ServiceOrderServiceLine:
        if quantity <= Decimal("0"):
            raise CatalogValidationError("Ilość usługi musi być większa od zera.")

        order = self.stock.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise CatalogNotFoundError("Nie znaleziono zlecenia serwisowego.")

        service = self.services.get(service_item_id, company_id=company_id)
        if service is None:
            raise CatalogNotFoundError("Nie znaleziono usługi.")

        unit_net = Decimal(service.default_price_net)
        vat_rate = Decimal(service.vat_rate)
        net, vat, gross = _prices(quantity, unit_net, vat_rate)

        line = self.stock.create_service_line(
            {
                **self._tenant_payload(company_id=company_id, branch_id=branch_id),
                "service_order_id": order.id,
                "service_item_id": service.id,
                "quantity": quantity,
                "unit_net_price": unit_net,
                "vat_rate": vat_rate,
                "net_value": net,
                "vat_value": vat,
                "gross_value": gross,
                "duration_minutes": int(service.standard_duration_minutes or 0),
            }
        )
        db.session.commit()
        return line

    def apply_auto_issue_materials(self, *, order_id: int, user_id: int | None, company_id: int | None, branch_id: int | None) -> list[ServiceOrderMaterialUsage]:
        auto_materials = self.materials.list_auto_issue(company_id=company_id)
        result: list[ServiceOrderMaterialUsage] = []
        for material in auto_materials:
            qty = Decimal(material.default_usage_qty)
            if qty <= Decimal("0"):
                continue
            if Decimal(material.current_stock) < qty:
                continue
            usage = self.issue_material_to_order(
                order_id=order_id,
                material_id=material.id,
                quantity=qty,
                user_id=user_id,
                company_id=company_id,
                branch_id=branch_id,
            )
            result.append(usage)
        return result

    def get_order_catalog_summary(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> dict[str, Any]:
        order = self.stock.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise CatalogNotFoundError("Nie znaleziono zlecenia serwisowego.")

        return {
            "order": order,
            "reservations": self.stock.list_part_reservations(order_id=order.id, company_id=company_id, branch_id=branch_id),
            "usages": self.stock.list_material_usages(order_id=order.id, company_id=company_id, branch_id=branch_id),
            "service_lines": self.stock.list_service_lines(order_id=order.id, company_id=company_id, branch_id=branch_id),
        }

    def _assert_unique(self, repository: Any, code: str | None, *, company_id: int | None) -> None:
        if not code:
            return
        existing = repository.get_by_code(code, company_id=company_id)
        if existing is not None:
            raise CatalogValidationError("Kod już istnieje.")

    def _validate_part_vat(self, repository: Any, data: dict[str, Any], *, company_id: int | None) -> None:
        if repository is not self.parts or "vat_id" not in data:
            return
        vat_id = data.get("vat_id")
        if vat_id is None:
            raise CatalogValidationError("Stawka VAT jest wymagana.")
        vat = db.session.get(VatRate, int(vat_id))
        if vat is None or vat.company_id != company_id or not vat.is_active:
            raise CatalogValidationError("Nieprawidłowa stawka VAT dla produktu.")

    def _normalize_foreign_keys(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(data)
        for fk in ("category_id", "manufacturer_id", "vat_id"):
            if fk in normalized and normalized[fk] in ("", 0, "0", None):
                normalized[fk] = None
        return normalized


def tenant_catalog_context(current_user: Any) -> tuple[int | None, int | None, int | None]:
    company_id = getattr(current_user, "company_id", None)
    branch_id = getattr(current_user, "branch_id", None)
    user_id = getattr(current_user, "id", None)
    return company_id, branch_id, user_id


def default_part_payload() -> dict[str, Any]:
    return {
        "current_stock": 0,
        "purchase_price_net": _safe_decimal("0"),
        "sale_price_net": _safe_decimal("0"),
    }


def default_material_payload() -> dict[str, Any]:
    return {
        "unit": "szt",
        "current_stock": _safe_decimal("0"),
        "minimum_stock": _safe_decimal("0"),
        "purchase_price_net": _safe_decimal("0"),
        "default_usage_qty": _safe_decimal("1"),
        "vat_rate": _safe_decimal("23"),
        "auto_issue_on_order": False,
    }


def default_service_payload() -> dict[str, Any]:
    return {
        "default_price_net": _safe_decimal("0"),
        "vat_rate": _safe_decimal("23"),
        "standard_duration_minutes": 60,
        "is_sellable": True,
    }
