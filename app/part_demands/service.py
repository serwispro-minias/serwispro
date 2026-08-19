from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models.part_demand import (
    PART_DEMAND_PRIORITY_CHOICES,
    PART_DEMAND_PRIORITY_LABELS,
    PART_DEMAND_STATUS_CHOICES,
    PART_DEMAND_STATUS_LABELS,
    PartDemand,
    PartDemandPriorityEnum,
    PartDemandStatusEnum,
)
from app.models.service_order import SERVICE_ORDER_PRIORITY_LABELS

from .exceptions import PartDemandNotFoundError, PartDemandPermissionError, PartDemandValidationError
from .repository import PartDemandGroupedRow, PartDemandRepository


@dataclass(slots=True)
class ReserveShortageResult:
    demand: PartDemand
    missing_quantity: Decimal


class PartDemandService:
    def __init__(self, repository: PartDemandRepository | None = None) -> None:
        self.repository = repository or PartDemandRepository()

    def get_status_choices(self) -> list[tuple[str, str]]:
        return list(PART_DEMAND_STATUS_CHOICES)

    def get_priority_choices(self) -> list[tuple[str, str]]:
        return list(PART_DEMAND_PRIORITY_CHOICES)

    def get_status_labels(self) -> dict[str, str]:
        return dict(PART_DEMAND_STATUS_LABELS)

    def get_priority_labels(self) -> dict[str, str]:
        return dict(PART_DEMAND_PRIORITY_LABELS)

    def list_part_choices(self, *, company_id: int) -> list[tuple[int, str]]:
        return [(0, "Wszystkie")] + self.repository.list_part_choices(company_id=company_id)

    def list_branch_choices(self, *, company_id: int) -> list[tuple[int, str]]:
        return [(0, "Wszystkie") ] + self.repository.list_branch_choices(company_id=company_id)

    def list_demands(
        self,
        *,
        company_id: int,
        actor,
        branch_scope_id: int | None,
        status: str | None,
        priority: str | None,
        branch_filter_id: int | None,
        order_id: int | None,
        inventory_item_id: int | None,
        expected_date_from: date | None,
        expected_date_to: date | None,
        query_text: str | None,
    ) -> list[PartDemand]:
        self._assert_can_view(actor)

        normalized_status = self._normalize_optional_status(status)
        normalized_priority = self._normalize_optional_priority(priority)
        normalized_branch_filter = self._normalize_optional_int(branch_filter_id)
        normalized_part_id = self._normalize_optional_int(inventory_item_id)

        if branch_scope_id is not None and normalized_branch_filter is not None and normalized_branch_filter != branch_scope_id:
            if not self._is_admin(actor):
                raise PartDemandPermissionError("Brak dostępu do wskazanego magazynu.")

        return self.repository.list_for_scope(
            company_id=company_id,
            branch_id=(branch_scope_id if not self._is_admin(actor) else None),
            status=normalized_status,
            priority=normalized_priority,
            branch_filter_id=normalized_branch_filter,
            order_id=order_id,
            inventory_item_id=normalized_part_id,
            expected_date_from=expected_date_from,
            expected_date_to=expected_date_to,
            query_text=query_text,
        )

    def list_grouped(
        self,
        *,
        company_id: int,
        actor,
        branch_scope_id: int | None,
        status: str | None,
        priority: str | None,
        branch_filter_id: int | None,
        expected_date_from: date | None,
        expected_date_to: date | None,
    ) -> list[PartDemandGroupedRow]:
        self._assert_can_view(actor)

        return self.repository.list_grouped(
            company_id=company_id,
            branch_id=(branch_scope_id if not self._is_admin(actor) else None),
            status=self._normalize_optional_status(status),
            priority=self._normalize_optional_priority(priority),
            branch_filter_id=self._normalize_optional_int(branch_filter_id),
            expected_date_from=expected_date_from,
            expected_date_to=expected_date_to,
        )

    def get_demand(self, *, demand_id: int, company_id: int, branch_scope_id: int | None, actor) -> PartDemand:
        self._assert_can_view(actor)
        row = self.repository.get_by_id(demand_id=demand_id, company_id=company_id, branch_id=(branch_scope_id if not self._is_admin(actor) else None))
        if row is None:
            raise PartDemandNotFoundError("Nie znaleziono zapotrzebowania.")
        return row

    def create_demand(
        self,
        *,
        data: dict[str, object],
        company_id: int,
        branch_scope_id: int | None,
        actor,
    ) -> PartDemand:
        self._assert_can_manage(actor)
        payload = self._normalize_payload(data, company_id=company_id, branch_scope_id=branch_scope_id, actor=actor)
        row = self.repository.create(payload)
        db.session.commit()
        return row

    def update_demand(
        self,
        *,
        demand_id: int,
        data: dict[str, object],
        company_id: int,
        branch_scope_id: int | None,
        actor,
    ) -> PartDemand:
        self._assert_can_manage(actor)
        row = self.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=branch_scope_id, actor=actor)
        payload = self._normalize_payload(data, company_id=company_id, branch_scope_id=row.branch_id, actor=actor)
        payload["updated_by"] = getattr(actor, "id", None)
        updated = self.repository.update(row, payload)
        db.session.commit()
        return updated

    def delete_demand(self, *, demand_id: int, company_id: int, branch_scope_id: int | None, actor) -> None:
        self._assert_can_manage(actor)
        row = self.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=branch_scope_id, actor=actor)
        self.repository.soft_delete(row, actor_id=getattr(actor, "id", None))
        db.session.commit()

    def create_or_update_from_shortage(
        self,
        *,
        order_id: int,
        part_id: int,
        requested_quantity: Decimal,
        available_quantity: Decimal,
        company_id: int,
        branch_id: int | None,
        actor_id: int | None,
        service_order_item_id: int | None = None,
    ) -> ReserveShortageResult:
        if requested_quantity <= Decimal("0"):
            raise PartDemandValidationError("Ilość zapotrzebowania musi być większa od zera.")

        missing = (requested_quantity - max(Decimal("0"), available_quantity)).quantize(Decimal("0.001"))
        if missing <= Decimal("0"):
            raise PartDemandValidationError("Brak niedoboru części, zapotrzebowanie nie jest wymagane.")

        order = self.repository.get_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            raise PartDemandValidationError("Nie znaleziono zlecenia serwisowego.")

        part = self.repository.get_part(part_id=part_id, company_id=company_id, branch_id=branch_id)
        if part is None:
            raise PartDemandValidationError("Nie znaleziono części.")

        existing = self.repository.find_open_for_order_part(order_id=order_id, part_id=part_id, company_id=company_id, branch_id=branch_id)
        if existing is not None:
            payload = {
                "requested_quantity": Decimal(existing.requested_quantity) + requested_quantity,
                "missing_quantity": Decimal(existing.missing_quantity) + missing,
                "status": PartDemandStatusEnum.TO_ORDER.value,
                "updated_by": actor_id,
            }
            updated = self.repository.update(existing, payload)
            db.session.commit()
            return ReserveShortageResult(demand=updated, missing_quantity=missing)

        priority = self._map_order_priority(order.priority)
        row = self.repository.create(
            {
                "service_order_id": order.id,
                "service_order_item_id": service_order_item_id,
                "inventory_item_id": part.id,
                "requested_quantity": requested_quantity,
                "reserved_quantity": Decimal("0"),
                "missing_quantity": missing,
                "status": PartDemandStatusEnum.TO_ORDER.value,
                "priority": priority,
                "expected_date": None,
                "notes": "Utworzono automatycznie podczas rezerwacji z niedoborem stanu.",
                "company_id": company_id,
                "branch_id": branch_id,
                "created_by": actor_id,
                "updated_by": actor_id,
            }
        )
        db.session.commit()
        return ReserveShortageResult(demand=row, missing_quantity=missing)

    def fulfill_demand(
        self,
        *,
        demand_id: int,
        reserve_quantity: Decimal,
        company_id: int,
        branch_scope_id: int | None,
        actor,
    ) -> PartDemand:
        self._assert_can_manage(actor)
        demand = self.get_demand(demand_id=demand_id, company_id=company_id, branch_scope_id=branch_scope_id, actor=actor)

        if reserve_quantity <= Decimal("0"):
            raise PartDemandValidationError("Ilość przypisania musi być większa od zera.")

        if demand.status in {PartDemandStatusEnum.DELIVERED.value, PartDemandStatusEnum.CANCELLED.value}:
            raise PartDemandValidationError("To zapotrzebowanie jest już zamknięte.")

        # Local import avoids circular dependency with catalog module.
        from app.catalog.service import CatalogService

        CatalogService().reserve_part_for_order(
            order_id=demand.service_order_id,
            part_id=demand.inventory_item_id,
            quantity=reserve_quantity,
            user_id=getattr(actor, "id", None),
            company_id=company_id,
            branch_id=demand.branch_id,
        )

        total_reserved = Decimal(demand.reserved_quantity) + reserve_quantity
        missing = max(Decimal("0"), Decimal(demand.requested_quantity) - total_reserved)
        status = PartDemandStatusEnum.DELIVERED.value if missing == Decimal("0") else PartDemandStatusEnum.ORDERED.value

        updated = self.repository.update(
            demand,
            {
                "reserved_quantity": total_reserved,
                "missing_quantity": missing,
                "status": status,
                "updated_by": getattr(actor, "id", None),
            },
        )
        db.session.commit()
        return updated

    def _normalize_payload(self, data: dict[str, object], *, company_id: int, branch_scope_id: int | None, actor) -> dict[str, object]:
        service_order_id = self._required_int(data.get("service_order_id"), field_name="zlecenie")
        inventory_item_id = self._required_int(data.get("inventory_item_id"), field_name="część")
        service_order_item_id = self._normalize_optional_int(data.get("service_order_item_id"))

        requested_quantity = self._required_decimal(data.get("requested_quantity"), field_name="ilość wymagana")
        reserved_quantity = self._optional_decimal(data.get("reserved_quantity"), default=Decimal("0"))
        missing_quantity = max(Decimal("0"), requested_quantity - reserved_quantity)

        status = self._normalize_status(data.get("status"))
        priority = self._normalize_priority(data.get("priority"))
        expected_date = data.get("expected_date")
        notes = (str(data.get("notes") or "").strip() or None)

        order = self.repository.get_order(order_id=service_order_id, company_id=company_id, branch_id=(branch_scope_id if not self._is_admin(actor) else None))
        if order is None:
            raise PartDemandValidationError("Nie znaleziono zlecenia serwisowego w bieżącym zakresie.")

        part = self.repository.get_part(part_id=inventory_item_id, company_id=company_id, branch_id=order.branch_id)
        if part is None:
            raise PartDemandValidationError("Nie znaleziono części w bieżącym zakresie.")

        if requested_quantity < Decimal("0") or reserved_quantity < Decimal("0") or missing_quantity < Decimal("0"):
            raise PartDemandValidationError("Ilości nie mogą być ujemne.")

        missing_quantity = max(Decimal("0"), requested_quantity - reserved_quantity)

        return {
            "service_order_id": order.id,
            "service_order_item_id": service_order_item_id,
            "inventory_item_id": part.id,
            "requested_quantity": requested_quantity,
            "reserved_quantity": reserved_quantity,
            "missing_quantity": missing_quantity,
            "status": status,
            "priority": priority,
            "expected_date": expected_date,
            "notes": notes,
            "company_id": company_id,
            "branch_id": order.branch_id,
            "created_by": getattr(actor, "id", None),
            "updated_by": getattr(actor, "id", None),
        }

    def _assert_can_manage(self, actor) -> None:
        if self._is_admin(actor) or self._is_warehouse(actor):
            return
        raise PartDemandPermissionError("Tylko magazynier lub administrator może zarządzać zapotrzebowaniami.")

    def _assert_can_view(self, actor) -> None:
        if self._is_admin(actor) or self._is_warehouse(actor) or self._is_manager(actor):
            return
        raise PartDemandPermissionError("Brak uprawnień do podglądu zapotrzebowań.")

    def _is_admin(self, actor) -> bool:
        role_names = {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
        return "administrator" in role_names

    def _is_manager(self, actor) -> bool:
        role_names = {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
        return "kierownik" in role_names

    def _is_warehouse(self, actor) -> bool:
        role_names = {(role.name or "").strip().lower() for role in getattr(actor, "roles", [])}
        return bool(role_names.intersection({"magazynier", "magazyn", "zakupy", "zakupowiec", "warehouse"}))

    def _normalize_optional_status(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().upper()
        if normalized not in PART_DEMAND_STATUS_LABELS:
            return None
        return normalized

    def _normalize_optional_priority(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().upper()
        if normalized not in PART_DEMAND_PRIORITY_LABELS:
            return None
        return normalized

    def _normalize_status(self, value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in PART_DEMAND_STATUS_LABELS:
            raise PartDemandValidationError("Nieprawidłowy status zapotrzebowania.")
        return normalized

    def _normalize_priority(self, value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in PART_DEMAND_PRIORITY_LABELS:
            raise PartDemandValidationError("Nieprawidłowy priorytet zapotrzebowania.")
        return normalized

    def _map_order_priority(self, value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if normalized in PART_DEMAND_PRIORITY_LABELS:
            return normalized
        if normalized in SERVICE_ORDER_PRIORITY_LABELS:
            return normalized
        return PartDemandPriorityEnum.NORMAL.value

    def _required_int(self, value: object, *, field_name: str) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            raise PartDemandValidationError(f"Pole {field_name} jest wymagane.") from None
        if normalized <= 0:
            raise PartDemandValidationError(f"Pole {field_name} jest wymagane.")
        return normalized

    def _normalize_optional_int(self, value: object) -> int | None:
        if value in (None, "", 0, "0"):
            return None
        return int(value)

    def _required_decimal(self, value: object, *, field_name: str) -> Decimal:
        try:
            normalized = Decimal(str(value))
        except Exception:
            raise PartDemandValidationError(f"Pole {field_name} ma nieprawidłową wartość.") from None
        if normalized <= Decimal("0"):
            raise PartDemandValidationError(f"Pole {field_name} musi być większe od zera.")
        return normalized

    def _optional_decimal(self, value: object, *, default: Decimal) -> Decimal:
        if value in (None, ""):
            return default
        try:
            return Decimal(str(value))
        except Exception:
            raise PartDemandValidationError("Nieprawidłowa wartość ilości.") from None
