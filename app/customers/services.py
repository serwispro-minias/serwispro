from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models.customer import Customer

from .exceptions import (
    CustomerAlreadyExistsError,
    CustomerNotFoundError,
    CustomerValidationError,
)
from .repository import CustomerRepository
from .validators import CustomerValidator


class CustomerService:
    """Service API for customer operations.

    This class orchestrates repository access and business validation
    for the customer module.
    """

    def __init__(
        self,
        repository: CustomerRepository,
        validator: CustomerValidator | None = None,
    ) -> None:
        self.repository = repository
        self.validator = validator or CustomerValidator()

    def get_customer(
        self,
        customer_id: int,
        company_id: int | None = None,
    ) -> Optional[Customer]:
        return self.repository.get_by_id(customer_id, company_id=company_id)

    def list_customers(
        self,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> Dict[str, Any]:
        return self.repository.paginate(page=page, per_page=per_page, company_id=company_id)

    def create_customer(
        self,
        data: Dict[str, Any],
        company_id: int | None,
    ) -> Customer:
        if company_id is None:
            raise CustomerValidationError("Brak identyfikatora firmy."
            )

        normalized = self.validator.normalize(data)
        payload = self._filter_payload(normalized)
        payload["company_id"] = company_id
        self.validator.validate_create(payload)

        self._validate_unique(payload, company_id=company_id)

        customer = self.repository.create(payload)
        db.session.commit()
        return customer

    def update_customer(
        self,
        customer_id: int,
        data: Dict[str, Any],
        company_id: int | None,
    ) -> Customer:
        normalized = self.validator.normalize(data)
        payload = self._filter_payload(normalized)
        self.validator.validate_update(customer_id, payload)

        self._validate_unique(payload, exclude_id=customer_id, company_id=company_id)

        customer = self.repository.update(customer_id, payload, company_id=company_id)
        if customer is None:
            raise CustomerNotFoundError(f"Klient o id {customer_id} nie istnieje.")

        db.session.commit()
        return customer

    def delete_customer(
        self,
        customer_id: int,
        company_id: int | None,
    ) -> None:
        customer = self.repository.get_by_id(customer_id, company_id=company_id)
        if customer is None:
            raise CustomerNotFoundError(f"Klient o id {customer_id} nie istnieje.")

        self.repository.delete(customer_id, company_id=company_id)
        db.session.commit()

    def search_customers(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        company_id: int | None = None,
    ) -> Dict[str, Any]:
        if not query or not query.strip():
            return self.list_customers(page=page, per_page=per_page, company_id=company_id)
        return self.repository.search(
            query=query,
            page=page,
            per_page=per_page,
            company_id=company_id,
        )

    def _filter_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {
            "customer_type",
            "full_name",
            "first_name",
            "last_name",
            "short_name",
            "nip",
            "regon",
            "krs",
            "pesel",
            "email",
            "phone",
            "phone2",
            "website",
            "country",
            "state",
            "postal_code",
            "city",
            "street",
            "building_no",
            "apartment_no",
            "notes",
            "company_id",
        }
        return {key: value for key, value in data.items() if key in allowed_keys}

    def _validate_unique(
        self,
        payload: Dict[str, Any],
        exclude_id: int | None = None,
        company_id: int | None = None,
    ) -> None:
        if payload.get("nip"):
            if exclude_id is None:
                if self.repository.exists_by_nip(payload["nip"], company_id=company_id):
                    raise CustomerAlreadyExistsError("Klient z takim NIP już istnieje.")
            elif self.repository.exists_by_nip_except_id(payload["nip"], exclude_id, company_id=company_id):
                raise CustomerAlreadyExistsError("Klient z takim NIP już istnieje.")

        if payload.get("email"):
            if exclude_id is None:
                if self.repository.exists_by_email(payload["email"], company_id=company_id):
                    raise CustomerAlreadyExistsError("Klient z takim adresem email już istnieje.")
            elif self.repository.exists_by_email_except_id(payload["email"], exclude_id, company_id=company_id):
                raise CustomerAlreadyExistsError("Klient z takim adresem email już istnieje.")

        if payload.get("phone"):
            if exclude_id is None:
                if self.repository.exists_by_phone(payload["phone"], company_id=company_id):
                    raise CustomerAlreadyExistsError("Klient z takim numerem telefonu już istnieje.")
            elif self.repository.exists_by_phone_except_id(payload["phone"], exclude_id, company_id=company_id):
                raise CustomerAlreadyExistsError("Klient z takim numerem telefonu już istnieje.")

