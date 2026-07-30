"""Customer-related exceptions for the customers module.

All exceptions inherit from `Exception`. They are defined as simple
marker classes so the service/repository layers can raise and the
application can catch them explicitly.
"""

from __future__ import annotations


class CustomerError(Exception):
    """Base class for all customer-related errors."""


class CustomerNotFoundError(CustomerError):
    """Raised when a requested customer cannot be found."""


class CustomerAlreadyExistsError(CustomerError):
    """Raised when attempting to create a customer that already exists."""


class CustomerValidationError(CustomerError):
    """Raised when provided customer data fails validation."""


class CustomerInactiveError(CustomerError):
    """Raised when an operation is attempted on an inactive customer."""
