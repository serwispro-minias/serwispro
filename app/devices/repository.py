"""Repository layer for devices.

Provides SQLAlchemy 2.x data access methods for `Device`.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.device import Device
from app.models.service_order import ServiceOrder


class DeviceRepository:
    """Repository handling persistence and querying for devices."""

    def _active_filters(
        self,
        *,
        company_id: int | None = None,
        customer_id: int | None = None,
    ) -> list[Any]:
        filters: list[Any] = [Device.is_active.is_(True)]
        if company_id is not None:
            filters.append(Device.company_id == company_id)
        if customer_id is not None:
            filters.append(Device.customer_id == customer_id)
        return filters

    def get_by_id(self, device_id: int, company_id: int | None = None) -> Device | None:
        """Return one active device by id."""

        return db.session.scalars(
            select(Device)
            .where(Device.id == device_id)
            .where(*self._active_filters(company_id=company_id))
        ).one_or_none()

    def get_recent_by_customer(
        self,
        customer_id: int,
        company_id: int | None = None,
        limit: int = 10,
    ) -> list[Device]:
        """Return latest active devices for a customer."""

        return list(
            db.session.scalars(
                select(Device)
                .where(*self._active_filters(company_id=company_id, customer_id=customer_id))
                .order_by(Device.created_at.desc(), Device.id.desc())
                .limit(limit)
            ).all()
        )

    def paginate(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
        customer_id: int | None = None,
    ) -> dict[str, Any]:
        """Return paginated active devices."""

        page = max(page, 1)
        per_page = max(per_page, 1)
        total = self.count(company_id=company_id, customer_id=customer_id)
        offset = (page - 1) * per_page

        items = list(
            db.session.scalars(
                select(Device)
                .where(*self._active_filters(company_id=company_id, customer_id=customer_id))
                .order_by(Device.id.desc())
                .offset(offset)
                .limit(per_page)
            ).all()
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if total else 0,
        }

    def search(
        self,
        *,
        query: str,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
        customer_id: int | None = None,
    ) -> dict[str, Any]:
        """Search active devices by selected text columns."""

        page = max(page, 1)
        per_page = max(per_page, 1)
        term = f"%{query.strip()}%"
        filters = self._active_filters(company_id=company_id, customer_id=customer_id)

        search_clause = or_(
            Device.manufacturer.ilike(term),
            Device.model.ilike(term),
            Device.serial_number.ilike(term),
            Device.inventory_number.ilike(term),
            Device.device_type.ilike(term),
            Device.condition_description.ilike(term),
            Device.accessories.ilike(term),
            Device.notes.ilike(term),
        )

        total = int(
            db.session.scalar(
                select(func.count())
                .select_from(Device)
                .where(*filters)
                .where(search_clause)
            )
            or 0
        )
        offset = (page - 1) * per_page

        items = list(
            db.session.scalars(
                select(Device)
                .where(*filters)
                .where(search_clause)
                .order_by(Device.id.desc())
                .offset(offset)
                .limit(per_page)
            ).all()
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if total else 0,
        }

    def create(self, data: dict[str, Any]) -> Device:
        """Create a new device and flush session."""

        device = Device(**data)
        db.session.add(device)
        db.session.flush()
        return device

    def update(self, device_id: int, data: dict[str, Any], company_id: int | None = None) -> Device | None:
        """Update an active device by id."""

        device = self.get_by_id(device_id, company_id=company_id)
        if device is None:
            return None

        for key, value in data.items():
            if hasattr(device, key) and key != "id":
                setattr(device, key, value)

        db.session.add(device)
        db.session.flush()
        return device

    def soft_delete(self, device_id: int, company_id: int | None = None) -> None:
        """Soft delete device by marking it inactive."""

        device = self.get_by_id(device_id, company_id=company_id)
        if device is None:
            return

        device.is_active = False
        db.session.add(device)
        db.session.flush()

    def count(self, company_id: int | None = None, customer_id: int | None = None) -> int:
        """Count active devices with optional scoping."""

        return int(
            db.session.scalar(
                select(func.count())
                .select_from(Device)
                .where(*self._active_filters(company_id=company_id, customer_id=customer_id))
            )
            or 0
        )

    def list_device_service_orders(
        self,
        *,
        device_id: int,
        company_id: int,
        branch_id: int | None,
        query_text: str | None,
    ) -> list[ServiceOrder]:
        """Return service orders history for one device sorted by intake date desc."""

        filters: list[Any] = [
            ServiceOrder.device_id == device_id,
            ServiceOrder.company_id == company_id,
            ServiceOrder.is_active.is_(True),
        ]
        if branch_id is not None:
            filters.append(ServiceOrder.branch_id == branch_id)

        if query_text:
            term = f"%{query_text.strip()}%"
            filters.append(
                or_(
                    ServiceOrder.order_number.ilike(term),
                    ServiceOrder.issue_description.ilike(term),
                    ServiceOrder.repair_description.ilike(term),
                )
            )

        query = (
            select(ServiceOrder)
            .where(*filters)
            .options(selectinload(ServiceOrder.customer))
            .order_by(ServiceOrder.intake_date.desc(), ServiceOrder.id.desc())
        )
        return list(db.session.scalars(query).all())
