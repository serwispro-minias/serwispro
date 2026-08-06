class PartDemandError(Exception):
    """Base exception for part demands module."""


class PartDemandNotFoundError(PartDemandError):
    """Raised when part demand is missing in tenant scope."""


class PartDemandValidationError(PartDemandError):
    """Raised when part demand payload is invalid."""


class PartDemandPermissionError(PartDemandError):
    """Raised when actor is not allowed to perform action."""
