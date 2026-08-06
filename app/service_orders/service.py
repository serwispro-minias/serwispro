"""Service layer for service orders."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import (
    SERVICE_ORDER_PRIORITY_CHOICES,
    SERVICE_ORDER_STATUS_BADGE_CLASSES,
    SERVICE_ORDER_STATUS_CHOICES,
    SERVICE_ORDER_STATUS_LABELS,
    ServiceOrder,
    ServiceOrderStatusEnum,
)
from app.models.service_order_status_history import ServiceOrderStatusHistory

from .exceptions import ServiceOrderNotFoundError, ServiceOrderValidationError
from .repository import ServiceOrderRepository
from .validators import ServiceOrderValidator


logger = logging.getLogger(__name__)


class ServiceOrderService:
    """Business service for service order operations."""

    def __init__(self, repository: ServiceOrderRepository, validator: ServiceOrderValidator | None = None) -> None:
        self.repository = repository
        self.validator = validator or ServiceOrderValidator()

    def get_service_order(self, order_id: int, company_id: int | None = None) -> ServiceOrder | None:
        """Return a service order by id."""

        return self.repository.get_by_id(order_id, company_id=company_id)

    def list_service_orders(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
        status: str | None = None,
        customer_id: int | None = None,
        order_number: str | None = None,
        device_serial_number: str | None = None,
        query: str | None = None,
        sort_by: str = "date",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        """Return paginated service orders."""

        normalized_status = (status or "").strip() or None
        normalized_order_number = (order_number or "").strip() or None
        normalized_device_serial_number = (device_serial_number or "").strip() or None
        normalized_query = (query or "").strip() or None
        normalized_sort_by = (sort_by or "date").strip().lower() or "date"
        normalized_sort_dir = (sort_dir or "desc").strip().lower() or "desc"

        logger.debug(
            "ServiceOrderService.list_service_orders params: page=%s per_page=%s company_id=%s "
            "status=%r customer_id=%s order_number=%r device_serial_number=%r query=%r sort_by=%s sort_dir=%s",
            page,
            per_page,
            company_id,
            normalized_status,
            customer_id,
            normalized_order_number,
            normalized_device_serial_number,
            normalized_query,
            normalized_sort_by,
            normalized_sort_dir,
        )

        return self.repository.paginate(
            page=page,
            per_page=per_page,
            company_id=company_id,
            status=normalized_status,
            customer_id=customer_id,
            order_number=normalized_order_number,
            device_serial_number=normalized_device_serial_number,
            query=normalized_query,
            sort_by=normalized_sort_by,
            sort_dir=normalized_sort_dir,
        )

    def create_service_order(self, data: dict[str, Any], *, company_id: int | None, branch_id: int | None) -> ServiceOrder:
        """Validate, normalize and create a service order."""

        if company_id is None:
            raise ServiceOrderValidationError("Brak identyfikatora firmy.")

        normalized = self.validator.normalize(data)
        payload = self._filter_payload(normalized)
        payload["company_id"] = company_id
        payload["branch_id"] = branch_id
        self.validator.validate_create(payload)
        self._validate_customer_device(payload["customer_id"], payload["device_id"], company_id)

        service_order = self.repository.create(payload)
        self.repository.create_status_history(
            service_order_id=service_order.id,
            old_status=None,
            new_status=service_order.status,
            changed_by=payload.get("created_by"),
            ip_address=None,
            note="Utworzenie zlecenia",
        )
        db.session.commit()
        return service_order

    def update_service_order(
        self,
        order_id: int,
        data: dict[str, Any],
        *,
        company_id: int | None,
        branch_id: int | None,
    ) -> ServiceOrder:
        """Validate, normalize and update a service order."""

        if company_id is None:
            raise ServiceOrderValidationError("Brak identyfikatora firmy.")

        normalized = self.validator.normalize(data)
        payload = self._filter_payload(normalized)
        payload["company_id"] = company_id
        payload["branch_id"] = branch_id
        self.validator.validate_update(order_id, payload)
        self._validate_customer_device(payload["customer_id"], payload["device_id"], company_id)

        existing = self.repository.get_by_id(order_id, company_id=company_id)
        if existing is None:
            raise ServiceOrderNotFoundError(f"Zlecenie o id {order_id} nie istnieje.")

        old_status = existing.status
        new_status = payload.get("status", old_status)
        self._validate_status_transition(old_status, new_status)

        service_order = self.repository.update(order_id, payload, company_id=company_id)
        if service_order is None:
            raise ServiceOrderNotFoundError(f"Zlecenie o id {order_id} nie istnieje.")

        if old_status != new_status:
            self.repository.create_status_history(
                service_order_id=service_order.id,
                old_status=old_status,
                new_status=new_status,
                changed_by=payload.get("updated_by") or payload.get("created_by"),
                ip_address=None,
                note=payload.get("technician_notes"),
            )

        db.session.commit()
        return service_order

    def delete_service_order(self, order_id: int, *, company_id: int | None) -> None:
        """Soft delete a service order."""

        service_order = self.repository.get_by_id(order_id, company_id=company_id)
        if service_order is None:
            raise ServiceOrderNotFoundError(f"Zlecenie o id {order_id} nie istnieje.")

        self.repository.soft_delete(order_id, company_id=company_id)
        db.session.commit()

    def get_customer_choices(self, company_id: int | None) -> list[tuple[int, str]]:
        """Return select-field choices for active customers."""

        if company_id is None:
            return []

        customers = db.session.scalars(
            select(Customer)
            .where(Customer.company_id == company_id)
            .where(Customer.is_active.is_(True))
            .order_by(func.coalesce(Customer.full_name, "").asc(), Customer.id.asc())
        ).all()

        choices: list[tuple[int, str]] = []
        for customer in customers:
            label = (
                customer.full_name
                or customer.short_name
                or f"{(customer.first_name or '').strip()} {(customer.last_name or '').strip()}".strip()
                or f"Klient #{customer.id}"
            )
            choices.append((customer.id, label))
        return choices

    def get_device_choices(self, company_id: int | None, customer_id: int | None) -> list[tuple[int, str]]:
        """Return select-field choices for active devices belonging to a customer."""

        if company_id is None or customer_id is None:
            return []

        devices = db.session.scalars(
            select(Device)
            .where(Device.company_id == company_id)
            .where(Device.customer_id == customer_id)
            .where(Device.is_active.is_(True))
            .order_by(
                func.coalesce(Device.manufacturer, "").asc(),
                func.coalesce(Device.model, "").asc(),
                Device.id.asc(),
            )
        ).all()

        choices: list[tuple[int, str]] = []
        for device in devices:
            label_parts = [
                device.manufacturer or "-",
                device.model or "-",
                device.serial_number or "-",
            ]
            label = " / ".join(label_parts)
            if device.inventory_number:
                label = f"{label} | INV: {device.inventory_number}"
            choices.append((device.id, label))
        return choices

    def get_status_choices(self) -> list[tuple[str, str]]:
        """Return status select choices."""

        return list(SERVICE_ORDER_STATUS_CHOICES)

    def get_priority_choices(self) -> list[tuple[str, str]]:
        """Return priority select choices."""

        return list(SERVICE_ORDER_PRIORITY_CHOICES)

    def get_status_labels(self) -> dict[str, str]:
        """Return labels for status values."""

        return dict(SERVICE_ORDER_STATUS_LABELS)

    def get_status_badge_classes(self) -> dict[str, str]:
        """Return badge class mapping per status value."""

        return dict(SERVICE_ORDER_STATUS_BADGE_CLASSES)

    def get_status_history(self, order_id: int, company_id: int | None) -> list[ServiceOrderStatusHistory]:
        """Return status history for a service order."""

        return self.repository.get_status_history(order_id, company_id=company_id)

    def change_status(
        self,
        *,
        order_id: int,
        new_status: str,
        company_id: int | None,
        changed_by: int | None,
        note: str | None,
    ) -> ServiceOrder:
        """Change service order status and append history record."""

        service_order = self.repository.get_by_id(order_id, company_id=company_id)
        if service_order is None:
            raise ServiceOrderNotFoundError(f"Zlecenie o id {order_id} nie istnieje.")

        old_status = service_order.status
        self._validate_status_transition(old_status, new_status)

        if old_status == new_status:
            raise ServiceOrderValidationError("Nowy status jest taki sam jak aktualny.")

        service_order.status = new_status
        db.session.add(service_order)
        db.session.flush()

        self.repository.create_status_history(
            service_order_id=service_order.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            ip_address=None,
            note=note,
        )
        db.session.commit()
        return service_order

    def has_customer_devices(self, company_id: int | None, customer_id: int | None) -> bool:
        """Return True when selected customer has at least one active device."""

        return len(self.get_device_choices(company_id, customer_id)) > 0

    def _validate_customer_device(self, customer_id: int, device_id: int, company_id: int) -> None:
        customer = db.session.scalar(
            select(Customer)
            .where(Customer.id == customer_id)
            .where(Customer.company_id == company_id)
            .where(Customer.is_active.is_(True))
        )
        if customer is None:
            raise ServiceOrderValidationError("Wybrany klient nie istnieje lub jest nieaktywny.")

        device = db.session.scalar(
            select(Device)
            .where(Device.id == device_id)
            .where(Device.company_id == company_id)
            .where(Device.customer_id == customer_id)
            .where(Device.is_active.is_(True))
        )
        if device is None:
            raise ServiceOrderValidationError("Wybrane urządzenie nie należy do wskazanego klienta.")

    def _validate_status_transition(self, old_status: str, new_status: str) -> None:
        """Validate whether a status transition is allowed."""

        if old_status == ServiceOrderStatusEnum.ISSUED.value and new_status != old_status:
            raise ServiceOrderValidationError("Nie można zmienić statusu z 'Wydane' na wcześniejszy status.")

        if old_status == ServiceOrderStatusEnum.CANCELLED.value and new_status != old_status:
            raise ServiceOrderValidationError("Nie można zmienić statusu z 'Anulowane' na inny status.")

    def _filter_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "customer_id",
            "device_id",
            "order_number",
            "status",
            "priority",
            "intake_date",
            "planned_finish_date",
            "finished_at",
            "warranty_repair",
            "issue_description",
            "diagnosis",
            "repair_description",
            "technician_notes",
            "customer_notes",
            "estimated_cost",
            "final_cost",
            "external_reference",
            "company_id",
            "branch_id",
        }
        return {key: value for key, value in data.items() if key in allowed_keys}
