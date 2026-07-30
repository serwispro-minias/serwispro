"""Core exception definitions for SerwisPRO."""


class CoreError(Exception):
    """Base exception for core application errors."""
    pass


class SecurityError(CoreError):
    """Raised for security-related failures."""
    pass
