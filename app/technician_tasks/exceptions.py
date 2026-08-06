class ServiceTaskError(Exception):
    """Base exception for technician task module."""


class ServiceTaskNotFoundError(ServiceTaskError):
    """Raised when task resource cannot be found."""


class ServiceTaskValidationError(ServiceTaskError):
    """Raised when task operation cannot be completed."""


class ServiceTaskPermissionError(ServiceTaskError):
    """Raised when actor has no permission for task operation."""
