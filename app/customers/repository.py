"""
Repository layer for customers.

This module exposes `CustomerRepository`, a thin data-access
abstraction for `Customer` model operations. Methods are declared
with type hints and docstrings but are not implemented yet — each
method raises `NotImplementedError` so callers know the implementation
is pending.

TODO: Implement actual DB queries using the application's SQLAlchemy
session in a later step. Keep repository methods focused on data
access only; do not place business logic here.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


class CustomerRepository:
    """Repository for `Customer` model access.

    All methods are placeholders and must be implemented to perform
    real database operations. Each method raises `NotImplementedError`.
    """

    def get_by_id(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Return a customer by its integer primary key.

        :param customer_id: Primary key of the customer.
        :return: A mapping representing the customer or None if not found.
        :raises NotImplementedError: method not implemented yet.
        """
        raise NotImplementedError()

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Return a customer by its UUID string.

        :param uuid: UUID of the customer.
        :return: Mapping for the customer or None.
        """
        raise NotImplementedError()

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all customers (careful with large result sets).

        :return: List of customer mappings.
        """
        raise NotImplementedError()

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search customers by a free-text query.

        :param query: Search string.
        :return: List of matching customers.
        """
        raise NotImplementedError()

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new customer from provided data.

        :param data: Mapping of customer attributes.
        :return: Created customer mapping (with id/uuid fields).
        """
        raise NotImplementedError()

    def update(self, customer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing customer.

        :param customer_id: Primary key of the customer to update.
        :param data: Fields to update.
        :return: Updated customer mapping.
        """
        raise NotImplementedError()

    def delete(self, customer_id: int) -> None:
        """Delete (or soft-delete) a customer by id.

        :param customer_id: Primary key of the customer to delete.
        :return: None
        """
        raise NotImplementedError()

    def exists_by_nip(self, nip: str) -> bool:
        """Return True if a customer exists with the given NIP.

        :param nip: NIP identifier to check.
        :return: Boolean existence flag.
        """
        raise NotImplementedError()

    def exists_by_email(self, email: str) -> bool:
        """Return True if a customer exists with the given email.

        :param email: Email to check.
        :return: Boolean existence flag.
        """
        raise NotImplementedError()

    def exists_by_phone(self, phone: str) -> bool:
        """Return True if a customer exists with the given phone number.

        :param phone: Phone number to check.
        :return: Boolean existence flag.
        """
        raise NotImplementedError()

    def paginate(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """Return a pagination page of customers.

        :param page: Page number (1-based).
        :param per_page: Items per page.
        :return: Mapping with keys like `items`, `total`, `page`, `per_page`.
        """
        raise NotImplementedError()

    def count(self) -> int:
        """Return total number of customers.

        :return: Integer count.
        """
        raise NotImplementedError()

