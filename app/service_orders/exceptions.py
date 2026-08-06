"""Service order related exceptions."""

from __future__ import annotations


class ServiceOrderError(Exception):
    """Base class for service order errors."""


class ServiceOrderNotFoundError(ServiceOrderError):
    """Raised when a service order cannot be found."""


class ServiceOrderValidationError(ServiceOrderError):
    """Raised when service order payload validation fails."""
