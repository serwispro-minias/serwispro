from __future__ import annotations

from typing import List

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel


class Permission(BaseTenantModel):

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company: Mapped["Company | None"] = relationship("Company", back_populates="permissions")
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="select",
    )
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="permission",
        lazy="select",
    )

    def __repr__(self) -> str:
        return self.name
