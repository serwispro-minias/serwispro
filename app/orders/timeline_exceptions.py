from __future__ import annotations


class OrderTimelineError(Exception):
    """Base class for service order timeline errors."""


class OrderTimelineNotFoundError(OrderTimelineError):
    """Raised when timeline entry or attachment cannot be found."""


class OrderTimelineValidationError(OrderTimelineError):
    """Raised when timeline payload or file validation fails."""
