"""Customer validation layer.

Provides normalization and field validation for customer payloads.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from .exceptions import CustomerValidationError


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


_TEXT_FIELDS = (
    "customer_type",
    "full_name",
    "first_name",
    "last_name",
    "short_name",
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
)

_DIGIT_FIELDS = ("nip", "regon", "pesel")


def _collapse_spaces(value: str) -> str:
    return " ".join(value.split())


class CustomerValidator:
    """Validator for customer payloads and fields."""

    def validate(self, data: Dict[str, Any]) -> None:
        """Validate normalized customer payload.

        :param data: Normalized customer payload.
        :raises CustomerValidationError: when validation fails.
        """

        required_fields = {
            "customer_type": "Typ klienta jest wymagany.",
        }

        for field_name, message in required_fields.items():
            if data.get(field_name) is None:
                raise CustomerValidationError(message)

        email = data.get("email")
        if email is not None:
            self.validate_email(email)

        nip = data.get("nip")
        if nip is not None:
            self.validate_nip(nip)

        regon = data.get("regon")
        if regon is not None:
            self._validate_regon(regon)

        pesel = data.get("pesel")
        if pesel is not None:
            self.validate_pesel(pesel)

        phone = data.get("phone")
        if phone is not None:
            self.validate_phone(phone)

        phone2 = data.get("phone2")
        if phone2 is not None:
            self.validate_phone(phone2)

    def validate_create(self, data: Dict[str, Any]) -> None:
        """Validate input data for creating a customer.

        :param data: Customer fields for creation.
        :raises CustomerValidationError: validation failed.
        """

        self.validate(data)

    def validate_update(self, customer_id: int, data: Dict[str, Any]) -> None:
        """Validate input data for updating a customer.

        :param customer_id: Customer identifier.
        :param data: Fields to update.
        :raises CustomerValidationError: validation failed.
        """

        _ = customer_id
        self.validate(data)

    def validate_nip(self, nip: str) -> None:
        """Validate a NIP (tax identification number)."""

        if not nip.isdigit() or len(nip) != 10:
            raise CustomerValidationError("NIP musi zawierać dokładnie 10 cyfr.")

    def validate_email(self, email: str) -> None:
        """Validate an email address."""

        if not _EMAIL_RE.match(email):
            raise CustomerValidationError("Podaj poprawny adres email.")

    def _validate_regon(self, regon: str) -> None:
        """Validate a REGON number."""

        if len(regon) not in {9, 14} or not regon.isdigit():
            raise CustomerValidationError("REGON musi zawierać 9 lub 14 cyfr.")

    def validate_phone(self, phone: str) -> None:
        """Validate a phone number."""

        digits = phone.replace(" ", "").replace("+", "")
        if not digits.isdigit() or not (9 <= len(digits) <= 15):
            raise CustomerValidationError("Podaj poprawny numer telefonu.")

    def validate_pesel(self, pesel: str) -> None:
        """Validate a PESEL number."""

        if not pesel.isdigit() or len(pesel) != 11:
            raise CustomerValidationError("PESEL musi zawierać dokładnie 11 cyfr.")

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize customer data before storage or validation.

        :param data: Raw customer data.
        :return: Normalized customer data.
        """

        normalized: Dict[str, Any] = dict(data)

        for field_name in _TEXT_FIELDS:
            value = normalized.get(field_name)
            if isinstance(value, str):
                value = _collapse_spaces(value.strip())
                if field_name == "email":
                    value = value.lower()
                normalized[field_name] = value or None

        for field_name in _DIGIT_FIELDS:
            value = normalized.get(field_name)
            if isinstance(value, str):
                digits_only = "".join(character for character in value if character.isdigit())
                normalized[field_name] = digits_only or None

        for key, value in list(normalized.items()):
            if isinstance(value, str) and not value.strip():
                normalized[key] = None

        return normalized