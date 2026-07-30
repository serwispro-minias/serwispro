from __future__ import annotations

from datetime import datetime
from typing import List

from flask_login import UserMixin
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel


class User(BaseTenantModel, UserMixin):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    login: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    company: Mapped["Company | None"] = relationship("Company", back_populates="users")
    roles: Mapped[List["Role"]] = relationship("Role", secondary="user_roles", back_populates="users", lazy="select")
    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="user", lazy="select")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user", lazy="select")

    def __repr__(self) -> str:
        return self.login
