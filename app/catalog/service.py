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
        if repository is self.parts or repository is self.materials:
            if _safe_decimal(data.get("current_stock")) != 0:
                raise CatalogValidationError("Nowy produkt musi mieć stan 0. Przyjęcie wykonaj dokumentem magazynowym.")
        data.update(self._tenant_payload(company_id=company_id, branch_id=branch_id))
        data = self._normalize_foreign_keys(data)
        self._validate_part_vat(repository, data, company_id=company_id)
        self._assert_unique(repository, data.get("code"), company_id=company_id)
        entity = repository.create(data)
        db.session.commit()
        return entity

    def update_entity(self, repository: Any, entity_id: int, data: dict[str, Any], *, company_id: int | None, branch_id: int | None = None) -> Any:
        entity = repository.get(entity_id, company_id=company_id)
        if entity is None:
            raise CatalogNotFoundError("Nie znaleziono rekordu.")

        data = self._sanitize_form_payload(data)
        if repository is self.parts or repository is self.materials:
            if branch_id is not None and entity.branch_id not in {None, branch_id}:
                raise CatalogValidationError("Produkt niedostępny w bieżącym oddziale.")
            if "current_stock" in data and _safe_decimal(data["current_stock"]) != Decimal(entity.current_stock):
                raise CatalogValidationError("Edycja kartoteki nie zmienia stanu. Użyj jawnej korekty lub dokumentu magazynowego.")
            data.pop("current_stock", None)
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
        actor=None,
    ) -> CatalogStockMovement:
        from sqlalchemy import or_, select

        from app.stock_issues.exceptions import StockIssuePermissionError
        from app.stock_issues.service import stock_issue_service

        try:
            stock_issue_service._assert_manage(actor)
            if company_id is None or getattr(actor, "company_id", None) != company_id or getattr(actor, "branch_id", None) != branch_id:
                raise CatalogValidationError("Nieprawidłowy zakres firmy lub oddziału użytkownika.")
            if movement_type != "ADJUSTMENT":
                raise CatalogValidationError("Katalog dopuszcza wyłącznie jawną korektę. Wydanie wykonaj przez RW, rezerwację i zwolnienie przez zlecenie, przyjęcie przez PZ lub bilans otwarcia.")
            if entity_type not in {"part", "material"}:
                raise CatalogValidationError("Nieprawidłowy typ produktu.")
            try:
                quantity = Decimal(str(quantity))
            except Exception:
                raise CatalogValidationError("Nieprawidłowy stan po korekcie.") from None
            if not quantity.is_finite() or quantity < 0 or quantity != quantity.quantize(Decimal("0.001")):
                raise CatalogValidationError("Stan po korekcie musi być nieujemny, do 3 miejsc po przecinku.")
            if entity_type == "part" and quantity != quantity.to_integral_value():
                raise CatalogValidationError("Stan części musi być całkowity.")
            if not (note or "").strip() or not (reference_id or "").strip():
                raise CatalogValidationError("Korekta wymaga uzasadnienia i numeru dokumentu.")
            model = CatalogPart if entity_type == "part" else CatalogMaterial
            query = select(model).where(model.id == entity_id, model.company_id == company_id, model.is_active.is_(True))
            if branch_id is not None:
                query = query.where(or_(model.branch_id == branch_id, model.branch_id.is_(None)))
            product = db.session.scalar(query.with_for_update().execution_options(populate_existing=True))
            if product is None:
                raise CatalogNotFoundError("Produkt niedostępny w bieżącej firmie i oddziale.")
            from app.inventory.reservation_service import reserved_stock
            held = reserved_stock(item_type="PART" if entity_type == "part" else "MATERIAL", item_id=product.id, company_id=company_id)
            if quantity < held:
                raise CatalogValidationError("Korekta nie może obniżyć stanu poniżej aktywnych rezerwacji. Najpierw uzgodnij rezerwacje.")
            updater = self.stock.update_part_stock if entity_type == "part" else self.stock.update_material_stock
            before, after = updater(product, quantity=quantity, movement_type="ADJUSTMENT")
            movement = self.stock.create_movement({
                **self._tenant_payload(company_id=company_id, branch_id=branch_id),
                "item_type": "PART" if entity_type == "part" else "MATERIAL",
                "part_id" if entity_type == "part" else "material_id": product.id,
                "movement_type": "ADJUSTMENT", "quantity": quantity,
                "stock_before": before, "stock_after": after,
                "reference_type": "ADJUSTMENT", "reference_id": reference_id.strip(),
                "note": note.strip(), "user_id": getattr(actor, "id", None),
                "created_by": getattr(actor, "id", None), "updated_by": getattr(actor, "id", None),
            })
            db.session.commit()
            return movement
        except StockIssuePermissionError as exc:
            db.session.rollback()
            raise CatalogValidationError(str(exc)) from exc
        except Exception:
            db.session.rollback()
            raise

    def reserve_part_for_order(
        self,
        *,
        order_id: int,
        part_id: int,
        quantity: Decimal,
        user_id: int | None,
        company_id: int | None,
        branch_id: int | None,
        create_shortage: bool = True,
        commit: bool = True,
    ) -> ReservePartForOrderResult:
        if not quantity.is_finite() or quantity <= Decimal("0"):
            raise CatalogValidationError("Ilość rezerwacji musi być większa od zera.")
        if quantity != quantity.to_integral_value():
            raise CatalogValidationError("Ilość części musi być całkowita.")

        order = self.stock.get_service_order(order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise CatalogNotFoundError("Nie znaleziono zlecenia serwisowego.")

        part = self.parts.get(part_id, company_id=company_id)
        if part is None:
            raise CatalogNotFoundError("Nie znaleziono części.")
        if order.branch_id is not None and part.branch_id not in {None, order.branch_id}:
            raise CatalogValidationError("Produkt należy do innego oddziału.")

        from sqlalchemy import select

        from app.inventory.reservation_service import reserved_stock
        from app.models.catalog_part import InventoryItem
        part = db.session.scalar(select(InventoryItem).where(InventoryItem.id == part.id).with_for_update().execution_options(populate_existing=True))
        current_stock = max(Decimal("0"), Decimal(part.current_stock) - reserved_stock(item_type="PART", item_id=part.id, company_id=company_id))
        reserved_quantity = min(quantity, current_stock)
        missing_quantity = max(Decimal("0"), quantity - reserved_quantity)

        if current_stock <= Decimal("0"):
            if not create_shortage:
                return ReservePartForOrderResult(reservation=None, demand_id=None, demand_missing_quantity=quantity)
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
                commit=commit,
            )
            return ReservePartForOrderResult(
                reservation=None,
                demand_id=demand_result.demand.id,
                demand_missing_quantity=demand_result.missing_quantity,
            )

        movement = self.stock.create_movement({
            **self._tenant_payload(company_id=company_id, branch_id=branch_id),
            "item_type": "PART", "part_id": part.id, "movement_type": "RESERVATION",
            "quantity": reserved_quantity, "stock_before": part.current_stock,
            "stock_after": part.current_stock, "service_order_id": order.id,
            "reference_type": "SERVICE_ORDER", "reference_id": str(order.id),
            "note": "Rezerwacja bez zmiany stanu fizycznego", "user_id": user_id,
        })

        reservation = self.stock.reserve_part(
            {
                **self._tenant_payload(company_id=company_id, branch_id=branch_id),
                "service_order_id": order.id,
                "part_id": part.id,
                "quantity": reserved_quantity,
                "status": "RESERVED",
            }
        )

        if missing_quantity > Decimal("0") and company_id is not None and create_shortage:
            from app.part_demands.service import PartDemandService

            demand_result = PartDemandService().create_or_update_from_shortage(
                order_id=order.id,
                part_id=part.id,
                requested_quantity=quantity,
                available_quantity=current_stock,
                company_id=company_id,
                branch_id=branch_id,
                actor_id=user_id,
                commit=False,
            )
            db.session.flush()
            _ = demand_result

        _ = movement
        if commit:
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
