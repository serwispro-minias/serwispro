"""
Customer service layer skeleton.

This module defines `CustomerService`, a thin orchestration layer that
will call repository functions and apply business rules. At this stage
the methods are intentionally unimplemented and raise
`NotImplementedError` so the service contract is clear.

Do not import Flask, SQLAlchemy, or request objects here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class CustomerService:
    """Service API for customer operations.

    The constructor receives a repository instance (implements data
    access). Methods are declared with type hints and docstrings but
    do not contain business logic yet.
    """

    def __init__(self, repository: "CustomerRepository") -> None:
        """Initialize service with a `CustomerRepository`.

        :param repository: Repository used for data access.
        """
        self.repository = repository

    from app.models import Customer

    def get_customer(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """Return a single customer by id.

        :param customer_id: Primary key of the customer.
        :return: Mapping representing the customer or None.
        :raises NotImplementedError: not implemented yet.
        """
        raise NotImplementedError()

    def list_customers(self) -> List[Dict[str, Any]]:
        """Return a list of customers.

        :return: List of customer mappings.
        """
        raise NotImplementedError()

    def create_customer(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new customer using provided data.

        :param data: Mapping of customer fields.
        :return: Created customer mapping.
        """
        raise NotImplementedError()

    def update_customer(self, customer_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing customer.

        :param customer_id: Primary key of the customer to update.
        :param data: Fields to update.
        :return: Updated customer mapping.
        """
        raise NotImplementedError()

    def delete_customer(self, customer_id: int) -> None:
        """Delete (or soft-delete) a customer.

        :param customer_id: Primary key of the customer to delete.
        :return: None
        """
        raise NotImplementedError()

    def search_customers(self, query: str) -> List[Dict[str, Any]]:
        """Search customers by a query string.

        :param query: Search expression.
        :return: List of matching customers.
        """
        raise NotImplementedError()

