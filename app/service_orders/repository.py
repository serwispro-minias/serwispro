"""Repository layer for service orders."""

from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.sql import Select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrder
from app.models.service_order_status_history import ServiceOrderStatusHistory


logger = logging.getLogger(__name__)


class ServiceOrderRepository:
    """SQLAlchemy 2.x repository for service orders."""

    _ALLOWED_SORT_FIELDS = {"number", "date", "customer", "status"}
    _ALLOWED_SORT_DIRECTIONS = {"asc", "desc"}

    def _base_query(self):
        return select(ServiceOrder).options(
            selectinload(ServiceOrder.customer),
            selectinload(ServiceOrder.device),
        )

    def _filters(
        self,
        *,
        company_id: int | None = None,
        status: str | None = None,
        customer_id: int | None = None,
        order_number: str | None = None,
        device_serial_number: str | None = None,
        query: str | None = None,
    ) -> list[Any]:
        normalized_status = (status or "").strip() or None
        normalized_order_number = (order_number or "").strip() or None
        normalized_device_serial_number = (device_serial_number or "").strip() or None
        normalized_query = (query or "").strip() or None

        filters: list[Any] = [ServiceOrder.is_active.is_(True)]
        if company_id is not None:
            filters.append(ServiceOrder.company_id == company_id)
        if normalized_status:
            filters.append(ServiceOrder.status == normalized_status)
        if customer_id is not None:
            filters.append(ServiceOrder.customer_id == customer_id)
        if normalized_order_number:
            filters.append(ServiceOrder.order_number.ilike(f"%{normalized_order_number}%"))
        if normalized_device_serial_number:
            filters.append(Device.serial_number.ilike(f"%{normalized_device_serial_number}%"))
        if normalized_query:
            term = f"%{normalized_query}%"
            filters.append(
                or_(
                    ServiceOrder.order_number.ilike(term),
                    ServiceOrder.external_reference.ilike(term),
                    ServiceOrder.issue_description.ilike(term),
                    ServiceOrder.diagnosis.ilike(term),
                    ServiceOrder.repair_description.ilike(term),
                    ServiceOrder.technician_notes.ilike(term),
                    ServiceOrder.customer_notes.ilike(term),
                    Customer.full_name.ilike(term),
                    Customer.short_name.ilike(term),
                    Customer.first_name.ilike(term),
                    Customer.last_name.ilike(term),
                    Device.manufacturer.ilike(term),
                    Device.model.ilike(term),
                    Device.serial_number.ilike(term),
                    Device.inventory_number.ilike(term),
                )
            )
        return filters

    def _apply_sorting(self, query: Select[Any], *, sort_by: str, sort_dir: str) -> Select[Any]:
        normalized_sort_by = (sort_by or "date").strip().lower()
        if normalized_sort_by not in self._ALLOWED_SORT_FIELDS:
            normalized_sort_by = "date"

        direction = (sort_dir or "desc").strip().lower()
        if direction not in self._ALLOWED_SORT_DIRECTIONS:
            direction = "desc"
        descending = direction == "desc"

        if normalized_sort_by == "number":
            column = ServiceOrder.order_number
            return query.order_by(column.desc() if descending else column.asc(), ServiceOrder.id.desc() if descending else ServiceOrder.id.asc())

        if normalized_sort_by == "customer":
            customer_name = func.coalesce(Customer.full_name, "")
            if descending:
                return query.order_by(customer_name.desc(), Customer.id.desc(), ServiceOrder.id.desc())
            return query.order_by(customer_name.asc(), Customer.id.asc(), ServiceOrder.id.asc())

        if normalized_sort_by == "status":
            column = ServiceOrder.status
            return query.order_by(column.desc() if descending else column.asc(), ServiceOrder.id.desc() if descending else ServiceOrder.id.asc())

        date_column = ServiceOrder.intake_date
        return query.order_by(date_column.desc() if descending else date_column.asc(), ServiceOrder.id.desc() if descending else ServiceOrder.id.asc())

    def get_by_id(self, order_id: int, company_id: int | None = None) -> ServiceOrder | None:
        """Return a single active service order by id."""

        return db.session.scalars(
            self._base_query()
            .where(ServiceOrder.id == order_id)
            .where(*self._filters(company_id=company_id))
        ).one_or_none()

    def paginate(
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
        """Return paginated active service orders."""

        page = max(page, 1)
        per_page = max(per_page, 1)
        filters = self._filters(
            company_id=company_id,
            status=status,
            customer_id=customer_id,
            order_number=order_number,
            device_serial_number=device_serial_number,
            query=query,
        )

        logger.debug(
            "ServiceOrderRepository.paginate params: page=%s per_page=%s company_id=%s status=%r "
            "customer_id=%s order_number=%r device_serial_number=%r query=%r sort_by=%s sort_dir=%s",
            page,
            per_page,
            company_id,
            status,
            customer_id,
            order_number,
            device_serial_number,
            query,
            sort_by,
            sort_dir,
        )

        logger.debug("ServiceOrderRepository.paginate WHERE conditions: %s", [str(condition) for condition in filters])

        total = self.count(
            company_id=company_id,
            status=status,
            customer_id=customer_id,
            order_number=order_number,
            device_serial_number=device_serial_number,
            query=query,
        )
        offset = (page - 1) * per_page

        orders_query = (
            self._base_query()
            .join(ServiceOrder.customer)
            .join(ServiceOrder.device)
            .where(*filters)
        )
        orders_query = self._apply_sorting(orders_query, sort_by=sort_by, sort_dir=sort_dir)

        compiled_query = orders_query.compile(
            bind=db.session.get_bind(),
            compile_kwargs={"literal_binds": True},
        )
        logger.debug("ServiceOrderRepository.paginate SQL: %s", compiled_query)
        logger.debug("ServiceOrderRepository.paginate filtered_count=%s", total)

        items = list(
            db.session.scalars(
                orders_query
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

    def create(self, data: dict[str, Any]) -> ServiceOrder:
        """Create and flush a service order."""

        service_order = ServiceOrder(**data)
        db.session.add(service_order)
        db.session.flush()
        return service_order

    def create_status_history(
        self,
        *,
        service_order_id: int,
        old_status: str | None,
        new_status: str,
        changed_by: int | None,
        ip_address: str | None,
        note: str | None,
    ) -> ServiceOrderStatusHistory:
        """Persist one status transition record for a service order."""

        history = ServiceOrderStatusHistory(
            service_order_id=service_order_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            ip_address=ip_address,
            note=note,
        )
        db.session.add(history)
        db.session.flush()
        return history

    def get_status_history(self, order_id: int, company_id: int | None = None) -> list[ServiceOrderStatusHistory]:
        """Return status history records for one active service order."""

        return list(
            db.session.scalars(
                select(ServiceOrderStatusHistory)
                .join(ServiceOrderStatusHistory.service_order)
                .where(ServiceOrderStatusHistory.service_order_id == order_id)
                .where(*self._filters(company_id=company_id))
                .order_by(ServiceOrderStatusHistory.changed_at.asc(), ServiceOrderStatusHistory.id.asc())
            ).all()
        )

    def update(self, order_id: int, data: dict[str, Any], company_id: int | None = None) -> ServiceOrder | None:
        """Update an existing active service order."""

        service_order = self.get_by_id(order_id, company_id=company_id)
        if service_order is None:
            return None

        for key, value in data.items():
            if hasattr(service_order, key) and key != "id":
                setattr(service_order, key, value)

        db.session.add(service_order)
        db.session.flush()
        return service_order

    def soft_delete(self, order_id: int, company_id: int | None = None) -> None:
        """Soft delete a service order."""

        service_order = self.get_by_id(order_id, company_id=company_id)
        if service_order is None:
            return

        service_order.is_active = False
        db.session.add(service_order)
        db.session.flush()

    def count(
        self,
        company_id: int | None = None,
        status: str | None = None,
        customer_id: int | None = None,
        order_number: str | None = None,
        device_serial_number: str | None = None,
        query: str | None = None,
    ) -> int:
        """Count active service orders with optional filters."""

        filters = self._filters(
            company_id=company_id,
            status=status,
            customer_id=customer_id,
            order_number=order_number,
            device_serial_number=device_serial_number,
            query=query,
        )
        count_query = select(func.count()).select_from(ServiceOrder).join(ServiceOrder.customer).join(ServiceOrder.device)
        total = int(
            db.session.scalar(
                count_query.where(
                    *filters
                )
            )
            or 0
        )

        logger.debug("ServiceOrderRepository.count WHERE conditions: %s", [str(condition) for condition in filters])
        logger.debug("ServiceOrderRepository.count filtered_count=%s", total)
        return total
