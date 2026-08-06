class ServiceOrderPhotoError(Exception):
    """Base exception for service-order photo module."""


class ServiceOrderPhotoNotFoundError(ServiceOrderPhotoError):
    """Raised when photo/order is missing in scope."""


class ServiceOrderPhotoValidationError(ServiceOrderPhotoError):
    """Raised when upload or data validation fails."""


class ServiceOrderPhotoPermissionError(ServiceOrderPhotoError):
    """Raised when current actor has no permission for operation."""
