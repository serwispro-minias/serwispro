from __future__ import annotations

from typing import List

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel


class Role(BaseTenantModel):

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company: Mapped["Company | None"] = relationship("Company", back_populates="roles")
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="select",
    )
    users: Mapped[List["User"]] = relationship("User", secondary="user_roles", back_populates="roles", lazy="select")
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", lazy="select")
    role_permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        lazy="select",
    )

    def __repr__(self) -> str:
        return self.name
