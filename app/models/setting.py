from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.company import Company


class Setting(BaseTenantModel):

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    company: Mapped["Company | None"] = relationship("Company", back_populates="settings")

    def __repr__(self) -> str:
        return f"<Setting key={self.key} company_id={self.company_id}>"