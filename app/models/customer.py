from __future__ import annotations

from enum import Enum as PyEnum
from typing import TYPE_CHECKING, List

from sqlalchemy import Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.device import Device
    from app.models.service_order import ServiceOrder


class CustomerTypeEnum(str, PyEnum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"


class Customer(BaseTenantModel):

    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_uuid", "uuid"),
        Index("ix_customers_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_type: Mapped[CustomerTypeEnum | None] = mapped_column(
        Enum(CustomerTypeEnum, name="customer_type_enum"), nullable=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nip: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    regon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    krs: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pesel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
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

    # `is_active`, `uuid` and `company_id` are inherited from BaseModel/BaseTenantModel

    company: Mapped["Company"] = relationship("Company", back_populates="customers")
    devices: Mapped[List["Device"]] = relationship("Device", back_populates="customer", lazy="select")
    service_orders: Mapped[List["ServiceOrder"]] = relationship("ServiceOrder", back_populates="customer", lazy="select")

    def __repr__(self) -> str:  # pragma: no cover - simple repr
        return f"<Customer {self.id} {self.full_name}>"
