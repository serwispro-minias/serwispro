from __future__ import annotations

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.role import Role
from app.models.user_role import UserRole

_ADMIN_NAMES = {"administrator", "admin", "owner", "właściciel", "właściciel firmy"}


def has_company_admin_role(actor, company_id: int | None) -> bool:
    """Check a company-owned admin role without trusting a submitted company or display-only UI."""
    user_id = getattr(actor, "id", None)
    if user_id is None or company_id is None:
        return False
    try:
        inspector = inspect(db.engine)
        if not inspector.has_table("roles") or not inspector.has_table("user_roles"):
            return False
        role_id = db.session.scalar(
            select(Role.id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.company_id == company_id)
            .where(Role.company_id == company_id)
            .where(Role.is_active.is_(True))
            .where(func.lower(Role.name).in_(_ADMIN_NAMES))
            .limit(1)
        )
        return role_id is not None
    except SQLAlchemyError:
        db.session.rollback()
        return False
