from __future__ import annotations


class ServiceOrderActionError(Exception):
    """Base class for service-order-action errors."""


class ServiceOrderActionNotFoundError(ServiceOrderActionError):
    """Raised when action entry cannot be found."""


class ServiceOrderActionValidationError(ServiceOrderActionError):
    """Raised when action payload is invalid."""
