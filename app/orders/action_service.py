from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction, SERVICE_ORDER_ACTION_TYPE_CHOICES

from .action_exceptions import ServiceOrderActionNotFoundError, ServiceOrderActionValidationError
from .action_repository import ServiceOrderActionRepository


class ServiceOrderActionService:
    """Business layer for service order action history."""

    def __init__(self, repository: ServiceOrderActionRepository | None = None) -> None:
        self.repository = repository or ServiceOrderActionRepository()

    def get_action_type_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ORDER_ACTION_TYPE_CHOICES)

    def get_action_type_labels(self) -> dict[str, str]:
        return dict(SERVICE_ORDER_ACTION_TYPE_CHOICES)

    def get_technician_choices(self, *, company_id: int) -> list[tuple[int, str]]:
        technicians = self.repository.list_technicians(company_id=company_id)
        choices: list[tuple[int, str]] = [(0, "- brak -")]
        for user in technicians:
            full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            label = full_name or user.login or f"Użytkownik #{user.id}"
            choices.append((user.id, label))
        return choices

    def list_actions(self, *, order_id: int, company_id: int, branch_id: int | None) -> list[ServiceOrderAction]:
        self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        return self.repository.list_for_order(order_id=order_id)

    def get_action(
        self,
        *,
        action_id: int,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> ServiceOrderAction:
        self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        action = self.repository.get_for_order(action_id=action_id, order_id=order_id)
        if action is None:
            raise ServiceOrderActionNotFoundError("Nie znaleziono wpisu historii.")
        return action

    def create_action(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        data: dict[str, object],
    ) -> ServiceOrderAction:
        service_order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        payload = self._normalize_payload(data, company_id=company_id)
        payload["service_order_id"] = service_order.id
        payload["company_id"] = service_order.company_id
        payload["branch_id"] = service_order.branch_id
        payload["created_by"] = user_id
        payload["updated_by"] = user_id

        action = self.repository.create(payload)
        db.session.commit()
        return action

    def update_action(
        self,
        *,
        action_id: int,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        data: dict[str, object],
    ) -> ServiceOrderAction:
        action = self.get_action(
            action_id=action_id,
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        payload = self._normalize_payload(data, company_id=company_id)
        payload["updated_by"] = user_id
        updated = self.repository.update(action, payload)
        db.session.commit()
        return updated

    def delete_action(
        self,
        *,
        action_id: int,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> None:
        action = self.get_action(
            action_id=action_id,
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        self.repository.delete(action)
        db.session.commit()

    def _get_scoped_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder:
        service_order = db.session.scalar(
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if service_order is None:
            raise ServiceOrderActionNotFoundError("Nie znaleziono zlecenia.")

        if branch_id is None and service_order.branch_id is None:
            return service_order
        if branch_id is None and service_order.branch_id is not None:
            raise ServiceOrderActionValidationError("Brak dostępu do wskazanego oddziału.")
        if branch_id is not None and service_order.branch_id != branch_id:
            raise ServiceOrderActionValidationError("Brak dostępu do wskazanego oddziału.")
        return service_order

    def _normalize_payload(self, data: dict[str, object], *, company_id: int) -> dict[str, object]:
        action_type = str(data.get("action_type") or "").strip().upper()
        if action_type not in self.get_action_type_labels():
            raise ServiceOrderActionValidationError("Wybierz poprawny rodzaj czynności.")

        action_date = data.get("action_date")
        if not isinstance(action_date, date):
            raise ServiceOrderActionValidationError("Podaj poprawną datę czynności.")

        description = str(data.get("description") or "").strip()
        if not description:
            raise ServiceOrderActionValidationError("Opis czynności jest wymagany.")

        technician_id_raw = data.get("technician_id")
        technician_id = int(technician_id_raw) if technician_id_raw not in (None, "") else 0
        if technician_id == 0:
            technician_id = None
        else:
            valid_ids = {item[0] for item in self.get_technician_choices(company_id=company_id)}
            if technician_id not in valid_ids:
                raise ServiceOrderActionValidationError("Wybrany serwisant jest nieprawidłowy.")

        work_time_minutes = data.get("work_time_minutes")
        if work_time_minutes in (None, ""):
            work_time_minutes = None
        elif int(work_time_minutes) < 0:
            raise ServiceOrderActionValidationError("Czas pracy nie może być ujemny.")
        else:
            work_time_minutes = int(work_time_minutes)

        cost = data.get("cost")
        if cost in (None, ""):
            cost = None
        elif Decimal(str(cost)) < Decimal("0"):
            raise ServiceOrderActionValidationError("Koszt nie może być ujemny.")
        else:
            cost = Decimal(str(cost))

        return {
            "action_date": action_date,
            "technician_id": technician_id,
            "action_type": action_type,
            "description": description,
            "work_time_minutes": work_time_minutes,
            "cost": cost,
            "is_visible_for_customer": bool(data.get("is_visible_for_customer")),
        }
