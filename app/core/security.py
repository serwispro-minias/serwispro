"""Security-related abstractions for SerwisPRO."""


class SecurityPolicy:
    """Placeholder for core security policy behavior."""

    def authorize(self, user, action: str) -> bool:
        return False
