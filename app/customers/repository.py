"""Repository layer for customers.

This module exposes `CustomerRepository`, a data-access abstraction
for `Customer` model operations. All methods use SQLAlchemy 2.x select
syntax and return model instances where applicable.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models.company import Company
from app.models.customer import Customer


class CustomerRepository:
    """Repository for `Customer` model access.

    This repository keeps data access separate from business logic and
    exposes methods for queries, pagination, search, and soft deletion.
    """

    def _active_filters(self, company_id: int | None = None) -> list[Any]:
        filters: list[Any] = [Customer.is_active.is_(True)]
        if company_id is not None:
            filters.append(Customer.company_id == company_id)
        return filters

    def get_by_id(self, customer_id: int, company_id: int | None = None) -> Optional[Customer]:
        """Return an active customer by integer primary key."""
        return db.session.scalars(
            select(Customer)
            .where(Customer.id == customer_id)
            .where(*self._active_filters(company_id))
        ).one_or_none()

    def get_by_uuid(self, uuid: str, company_id: int | None = None) -> Optional[Customer]:
        """Return an active customer by UUID."""
        return db.session.scalars(
            select(Customer)
            .where(Customer.uuid == uuid)
            .where(*self._active_filters(company_id))
        ).one_or_none()

    def get_all(self, company_id: int | None = None) -> List[Customer]:
        """Return all active customers."""
        return db.session.scalars(
            select(Customer)
            .where(*self._active_filters(company_id))
            .order_by(Customer.id)
        ).all()

    def paginate(
        self,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> Dict[str, Any]:
        """Return a paginated page of active customers."""
        page = max(page, 1)
        per_page = max(per_page, 1)
        total = self.count(company_id=company_id)
        offset = (page - 1) * per_page
        items = db.session.scalars(
            select(Customer)
            .where(*self._active_filters(company_id))
            .order_by(Customer.id)
            .offset(offset)
            .limit(per_page)
        ).all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if total else 0,
        }

    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> Dict[str, Any]:
        """Search active customers by company name, full name, first name, last name, short name, city, NIP, phone, or email."""
        page = max(page, 1)
        per_page = max(per_page, 1)
        term = f"%{query.strip()}%"
        filters = self._active_filters(company_id)
        count_query = (
            select(func.count())
            .select_from(Customer)
            .join(Customer.company)
            .where(*filters)
            .where(
                or_(
                    Company.name.ilike(term),
                    Customer.full_name.ilike(term),
                    Customer.short_name.ilike(term),
                    Customer.first_name.ilike(term),
                    Customer.last_name.ilike(term),
                    Customer.city.ilike(term),
                    Customer.nip.ilike(term),
                    Customer.phone.ilike(term),
                    Customer.email.ilike(term),
                )
            )
        )
        total = db.session.scalar(count_query) or 0
        offset = (page - 1) * per_page
        items = db.session.scalars(
            select(Customer)
            .join(Customer.company)
            .where(*filters)
            .where(
                or_(
                    Company.name.ilike(term),
                    Customer.full_name.ilike(term),
                    Customer.short_name.ilike(term),
                    Customer.first_name.ilike(term),
                    Customer.last_name.ilike(term),
                    Customer.city.ilike(term),
                    Customer.nip.ilike(term),
                    Customer.phone.ilike(term),
                    Customer.email.ilike(term),
                )
            )
            .order_by(Customer.id)
            .offset(offset)
            .limit(per_page)
        ).all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": math.ceil(total / per_page) if total else 0,
        }

    def create(self, data: Dict[str, Any]) -> Customer:
        """Create a new customer and persist it to the current transaction."""
        customer = Customer(**data)
        db.session.add(customer)
        db.session.flush()
        return customer

    def update(
        self,
        customer_id: int,
        data: Dict[str, Any],
        company_id: int | None = None,
    ) -> Optional[Customer]:
        """Update an existing active customer with provided data."""
        customer = self.get_by_id(customer_id, company_id=company_id)
        if customer is None:
            return None

        for key, value in data.items():
            if hasattr(customer, key) and key != "id":
                setattr(customer, key, value)

        db.session.add(customer)
        db.session.flush()
        return customer

    def delete(self, customer_id: int, company_id: int | None = None) -> None:
        """Soft delete a customer by marking it inactive."""
        customer = self.get_by_id(customer_id, company_id=company_id)
        if customer is None:
            return

        customer.is_active = False
        db.session.add(customer)
        db.session.flush()

    def exists_by_nip(self, nip: str, company_id: int | None = None) -> bool:
        """Return True if an active customer exists with the given NIP."""
        query = select(func.count()).select_from(Customer).where(Customer.nip == nip).where(*self._active_filters(company_id))
        return db.session.scalar(query) > 0

    def exists_by_email(self, email: str, company_id: int | None = None) -> bool:
        """Return True if an active customer exists with the given email."""
        query = select(func.count()).select_from(Customer).where(Customer.email == email).where(*self._active_filters(company_id))
        return db.session.scalar(query) > 0

    def exists_by_phone(self, phone: str, company_id: int | None = None) -> bool:
        """Return True if an active customer exists with the given phone."""
        query = select(func.count()).select_from(Customer).where(Customer.phone == phone).where(*self._active_filters(company_id))
        return db.session.scalar(query) > 0

    def exists_by_nip_except_id(
        self,
        nip: str,
        exclude_id: int,
        company_id: int | None = None,
    ) -> bool:
        """Return True if another active customer uses the same NIP."""
        return db.session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.nip == nip)
            .where(Customer.id != exclude_id)
            .where(*self._active_filters(company_id))
        ) > 0

    def exists_by_email_except_id(
        self,
        email: str,
        exclude_id: int,
        company_id: int | None = None,
    ) -> bool:
        """Return True if another active customer uses the same email."""
        return db.session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.email == email)
            .where(Customer.id != exclude_id)
            .where(*self._active_filters(company_id))
        ) > 0

    def exists_by_phone_except_id(
        self,
        phone: str,
        exclude_id: int,
        company_id: int | None = None,
    ) -> bool:
        """Return True if another active customer uses the same phone."""
        return db.session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.phone == phone)
            .where(Customer.id != exclude_id)
            .where(*self._active_filters(company_id))
        ) > 0

    def count(self, company_id: int | None = None) -> int:
        """Return the total count of active customers."""
        return db.session.scalar(
            select(func.count())
            .select_from(Customer).where(*self._active_filters(company_id))
        ) or 0

