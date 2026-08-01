"""Device-related exceptions for devices module."""

from __future__ import annotations


class DeviceError(Exception):
    """Base class for all device module errors."""


class DeviceNotFoundError(DeviceError):
    """Raised when requested device does not exist."""


class DeviceValidationError(DeviceError):
    """Raised when input payload for a device is invalid."""
