from __future__ import annotations

from typing import List

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel


class Customer(BaseTenantModel):

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nip: Mapped[str | None] = mapped_column(String(32), nullable=True)
    regon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    krs: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pesel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone2: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    building_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    apartment_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # `is_active` is inherited from BaseModel (do not redeclare)

    # Relationship back to company (company_id provided by BaseTenantModel)
    company: Mapped["Company"] = relationship("Company", back_populates="customers", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return f"<Customer {self.id} {self.full_name}>"
