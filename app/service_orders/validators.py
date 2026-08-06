"""Validation helpers for service orders."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict

from app.models.service_order import (
    SERVICE_ORDER_PRIORITY_CHOICES,
    SERVICE_ORDER_STATUS_CHOICES,
)

from .exceptions import ServiceOrderValidationError


_TEXT_FIELDS = (
    "order_number",
    "status",
    "priority",
    "issue_description",
    "diagnosis",
    "repair_description",
    "technician_notes",
    "customer_notes",
    "external_reference",
)

_ALLOWED_STATUS = {value for value, _ in SERVICE_ORDER_STATUS_CHOICES}
_ALLOWED_PRIORITY = {value for value, _ in SERVICE_ORDER_PRIORITY_CHOICES}


class ServiceOrderValidator:
    """Validator for service order payloads."""

    def validate(self, data: Dict[str, Any]) -> None:
        """Validate a normalized service order payload."""

        required_fields = {
            "customer_id": "Wybierz klienta.",
            "device_id": "Wybierz urządzenie.",
            "order_number": "Numer zlecenia jest wymagany.",
            "status": "Status zlecenia jest wymagany.",
            "priority": "Priorytet zlecenia jest wymagany.",
            "intake_date": "Data przyjęcia jest wymagana.",
            "issue_description": "Opis usterki jest wymagany.",
        }

        for field_name, message in required_fields.items():
            if data.get(field_name) in (None, ""):
                raise ServiceOrderValidationError(message)

        customer_id = data.get("customer_id")
        device_id = data.get("device_id")
        if not isinstance(customer_id, int) or customer_id <= 0:
            raise ServiceOrderValidationError("Wybierz poprawnego klienta.")
        if not isinstance(device_id, int) or device_id <= 0:
            raise ServiceOrderValidationError("Wybierz poprawne urządzenie.")

        order_number = data.get("order_number")
        if not isinstance(order_number, str) or not order_number.strip():
            raise ServiceOrderValidationError("Numer zlecenia jest wymagany.")
        if len(order_number) > 50:
            raise ServiceOrderValidationError("Numer zlecenia może mieć maksymalnie 50 znaków.")

        status = data.get("status")
        if status not in _ALLOWED_STATUS:
            raise ServiceOrderValidationError("Wybrano nieprawidłowy status zlecenia.")

        priority = data.get("priority")
        if priority not in _ALLOWED_PRIORITY:
            raise ServiceOrderValidationError("Wybrano nieprawidłowy priorytet zlecenia.")

        intake_date = data.get("intake_date")
        if not isinstance(intake_date, date):
            raise ServiceOrderValidationError("Data przyjęcia jest nieprawidłowa.")

        planned_finish_date = data.get("planned_finish_date")
        if planned_finish_date is not None and not isinstance(planned_finish_date, date):
            raise ServiceOrderValidationError("Planowana data zakończenia jest nieprawidłowa.")

        finished_at = data.get("finished_at")
        if finished_at is not None and not hasattr(finished_at, "year"):
            raise ServiceOrderValidationError("Data zakończenia jest nieprawidłowa.")

        estimated_cost = data.get("estimated_cost")
        if estimated_cost is not None and not isinstance(estimated_cost, Decimal):
            raise ServiceOrderValidationError("Szacowany koszt jest nieprawidłowy.")

        final_cost = data.get("final_cost")
        if final_cost is not None and not isinstance(final_cost, Decimal):
            raise ServiceOrderValidationError("Końcowy koszt jest nieprawidłowy.")

    def validate_create(self, data: Dict[str, Any]) -> None:
        """Validate data for creating a service order."""

        self.validate(data)

    def validate_update(self, order_id: int, data: Dict[str, Any]) -> None:
        """Validate data for updating a service order."""

        _ = order_id
        self.validate(data)

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize service order payload values."""

        normalized: Dict[str, Any] = dict(data)

        for field_name in _TEXT_FIELDS:
            value = normalized.get(field_name)
            if isinstance(value, str):
                value = " ".join(value.strip().split())
                if field_name in {"status", "priority"}:
                    value = value.upper()
                normalized[field_name] = value or None

        for field_name in ["external_reference"]:
            value = normalized.get(field_name)
            if isinstance(value, str):
                normalized[field_name] = value.strip() or None

        for key, value in list(normalized.items()):
            if isinstance(value, str) and not value.strip():
                normalized[key] = None

        return normalized
