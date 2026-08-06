class CatalogError(Exception):
    """Base catalog module exception."""


class CatalogValidationError(CatalogError):
    """Validation error in catalog operations."""


class CatalogNotFoundError(CatalogError):
    """Resource does not exist or is not available in tenant scope."""
