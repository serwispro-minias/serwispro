from __future__ import annotations


class InventoryError(Exception):
    """Base inventory exception."""


class InventoryNotFoundError(InventoryError):
    """Raised when requested inventory resource was not found."""


class InventoryValidationError(InventoryError):
    """Raised when inventory data fails validation."""
