"""Service layer for devices module."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrderStatusEnum
from app.models.user import User

from .exceptions import DeviceNotFoundError, DeviceValidationError
from .repository import DeviceRepository


class DeviceService:
    """Orchestrates device operations and delegates persistence to repository."""

    def __init__(self, repository: DeviceRepository) -> None:
        self.repository = repository

    def get_device(self, device_id: int, company_id: int | None = None) -> Device | None:
        """Return one active device by id."""

        return self.repository.get_by_id(device_id, company_id=company_id)

    def list_devices(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        """Return paginated list of active devices."""

        return self.repository.paginate(page=page, per_page=per_page, company_id=company_id)

    def search_devices(
        self,
        *,
        query: str,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        """Search active devices with pagination."""

        if not query or not query.strip():
            return self.list_devices(page=page, per_page=per_page, company_id=company_id)

        return self.repository.search(
            query=query,
            page=page,
            per_page=per_page,
            company_id=company_id,
        )

    def create_device(self, data: dict[str, Any], company_id: int | None) -> Device:
        """Create a device and commit transaction."""

        if company_id is None:
            raise DeviceValidationError("Brak identyfikatora firmy.")

        payload = self._filter_payload(data)
        if payload.get("customer_id") is None:
            raise DeviceValidationError("Wybierz klienta.")

        payload["company_id"] = company_id
        self._validate_customer_scope(payload["customer_id"], company_id)

        device = self.repository.create(payload)
        db.session.commit()
        return device

    def update_device(
        self,
        device_id: int,
        data: dict[str, Any],
        company_id: int | None,
    ) -> Device:
        """Update a device and commit transaction."""

        payload = self._filter_payload(data)
        if payload.get("customer_id") is None:
            raise DeviceValidationError("Wybierz klienta.")

        if company_id is None:
            raise DeviceValidationError("Brak identyfikatora firmy.")

        self._validate_customer_scope(payload["customer_id"], company_id)
        device = self.repository.update(device_id, payload, company_id=company_id)
        if device is None:
            raise DeviceNotFoundError(f"Urzadzenie o id {device_id} nie istnieje.")

        db.session.commit()
        return device

    def delete_device(self, device_id: int, company_id: int | None) -> None:
        """Soft delete device and commit transaction."""

        device = self.repository.get_by_id(device_id, company_id=company_id)
        if device is None:
            raise DeviceNotFoundError(f"Urzadzenie o id {device_id} nie istnieje.")

        self.repository.soft_delete(device_id, company_id=company_id)
        db.session.commit()

    def list_recent_customer_devices(
        self,
        customer_id: int,
        company_id: int | None,
        limit: int = 10,
    ) -> list[Device]:
        """Return recent devices belonging to selected customer."""

        return self.repository.get_recent_by_customer(
            customer_id=customer_id,
            company_id=company_id,
            limit=limit,
        )

    def get_customer_choices(self, company_id: int | None) -> list[tuple[int, str]]:
        """Return active customer list for select field choices."""

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

    def get_repair_history_context(
        self,
        *,
        device_id: int,
        company_id: int,
        branch_id: int | None,
        query_text: str | None,
    ) -> dict[str, Any]:
        """Return scoped repair history rows and summary for one device."""

        all_orders = self.repository.list_device_service_orders(
            device_id=device_id,
            company_id=company_id,
            branch_id=branch_id,
            query_text=None,
        )
        visible_orders = self.repository.list_device_service_orders(
            device_id=device_id,
            company_id=company_id,
            branch_id=branch_id,
            query_text=(query_text or "").strip() or None,
        )

        technician_ids = {
            order.updated_by or order.created_by
            for order in all_orders
            if (order.updated_by or order.created_by) is not None
        }
        technician_map: dict[int, str] = {}
        if technician_ids:
            users = db.session.scalars(select(User).where(User.id.in_(technician_ids))).all()
            for user in users:
                full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
                technician_map[user.id] = full_name or user.login

        intake_dates = [item.intake_date for item in all_orders if item.intake_date is not None]
        summary = {
            "total_repairs": len(all_orders),
            "first_repair": min(intake_dates) if intake_dates else None,
            "last_repair": max(intake_dates) if intake_dates else None,
            "completed_count": sum(1 for item in all_orders if item.status == ServiceOrderStatusEnum.ISSUED.value),
            "cancelled_count": sum(1 for item in all_orders if item.status == ServiceOrderStatusEnum.CANCELLED.value),
        }

        return {
            "rows": visible_orders,
            "summary": summary,
            "technician_map": technician_map,
        }

    def _validate_customer_scope(self, customer_id: int, company_id: int) -> None:
        customer = db.session.scalar(
            select(Customer)
            .where(Customer.id == customer_id)
            .where(Customer.company_id == company_id)
            .where(Customer.is_active.is_(True))
        )
        if customer is None:
            raise DeviceValidationError("Wybrany klient nie istnieje lub jest nieaktywny.")

    def _filter_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "customer_id",
            "manufacturer",
            "model",
            "serial_number",
            "inventory_number",
            "device_type",
            "purchase_date",
            "warranty_until",
            "password",
            "condition_description",
            "accessories",
            "notes",
            "company_id",
        }

        payload = {key: value for key, value in data.items() if key in allowed_keys}

        for key in [
            "manufacturer",
            "model",
            "serial_number",
            "inventory_number",
            "device_type",
            "password",
            "condition_description",
            "accessories",
            "notes",
        ]:
            value = payload.get(key)
            if isinstance(value, str):
                payload[key] = value.strip() or None

        return payload
