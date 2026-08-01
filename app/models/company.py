from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.branch import Branch
    from app.models.customer import Customer
    from app.models.permission import Permission
    from app.models.role import Role
    from app.models.setting import Setting
    from app.models.user import User


class Company(BaseModel):

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prefix: Mapped[str] = mapped_column(String(10), nullable=False, default="SER")
    nip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)

    users: Mapped[List["User"]] = relationship("User", back_populates="company", lazy="select")
    roles: Mapped[List["Role"]] = relationship("Role", back_populates="company", lazy="select")
    permissions: Mapped[List["Permission"]] = relationship("Permission", back_populates="company", lazy="select")
    settings: Mapped[List["Setting"]] = relationship("Setting", back_populates="company", lazy="select")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="company", lazy="select")
    branches: Mapped[List["Branch"]] = relationship("Branch", back_populates="company", lazy="select")
    customers: Mapped[List["Customer"]] = relationship("Customer", back_populates="company", lazy="select")

    def __repr__(self) -> str:
        return f"<Company {self.name}>"
