"""Customer validation layer skeleton.

This module defines `CustomerValidator` with placeholder methods for
business validation and normalization rules. Each method is a stub that
raises `NotImplementedError` until validation logic is implemented.
"""

from __future__ import annotations

from typing import Any, Dict


class CustomerValidator:
    """Validator for customer payloads and fields."""

    def validate_create(self, data: Dict[str, Any]) -> None:
        """Validate input data for creating a customer.

        :param data: Customer fields for creation.
        :raises NotImplementedError: validation not implemented yet.
        """
        raise NotImplementedError()

    def validate_update(self, customer_id: int, data: Dict[str, Any]) -> None:
        """Validate input data for updating a customer.

        :param customer_id: Customer identifier.
        :param data: Fields to update.
        :raises NotImplementedError: validation not implemented yet.
        """
        raise NotImplementedError()

    def validate_nip(self, nip: str) -> None:
        """Validate a NIP (tax identification number)."""
        raise NotImplementedError()

    def validate_email(self, email: str) -> None:
        """Validate an email address."""
        raise NotImplementedError()

    def validate_phone(self, phone: str) -> None:
        """Validate a phone number."""
        raise NotImplementedError()

    def validate_pesel(self, pesel: str) -> None:
        """Validate a PESEL number."""
        raise NotImplementedError()

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize customer data before storage or validation.

        :param data: Raw customer data.
        :return: Normalized customer data.
        """
        raise NotImplementedError()