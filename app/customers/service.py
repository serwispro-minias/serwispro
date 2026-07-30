"""
Service layer for customers.

TODO: Implement business logic here (validation, orchestration,
and use of repository functions). Services should not access the
Flask request or session directly; keep them pure and testable.
"""

from typing import Any


def get_customers_context() -> dict[str, Any]:
    """Return context data for customer views (placeholder).

    Replace with real implementations that call `repository`.
    """
    return {'message': 'TODO: implement customers service layer'}
