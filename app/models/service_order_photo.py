from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_order import ServiceOrder
    from app.models.service_order_photo_annotation import PhotoAnnotation
    from app.models.user import User


SERVICE_ORDER_PHOTO_TYPE_CHOICES: list[tuple[str, str]] = [
    ("RECEPTION", "Przyjęcie sprzętu"),
    ("DAMAGE", "Uszkodzenia"),
    ("REPAIR", "Przebieg naprawy"),
    ("PART", "Wymienione części"),
    ("FINAL", "Stan po naprawie"),
    ("HANDOVER", "Wydanie sprzętu"),
    ("OTHER", "Inne"),
]

SERVICE_ORDER_PHOTO_TYPE_LABELS = dict(SERVICE_ORDER_PHOTO_TYPE_CHOICES)


class ServiceOrderPhoto(BaseTenantModel):
    """Metadata for one service-order photo stored on disk."""

    __tablename__ = "service_order_photos"
    __table_args__ = (
        Index("ix_so_photos_company_id", "company_id"),
        Index("ix_so_photos_branch_id", "branch_id"),
        Index("ix_so_photos_order_id", "service_order_id"),
        Index("ix_so_photos_type", "photo_type"),
        Index("ix_so_photos_taken_at", "taken_at"),
        Index("ix_so_photos_created_by", "created_by"),
        Index("ix_so_photos_sort_order", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    photo_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_visible_for_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="photos")
    annotations: Mapped[list["PhotoAnnotation"]] = relationship(
        "PhotoAnnotation",
        back_populates="photo",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="PhotoAnnotation.created_at.asc(), PhotoAnnotation.id.asc()",
    )
    author_user: Mapped["User | None"] = relationship(
        "User",
        lazy="select",
        primaryjoin="foreign(ServiceOrderPhoto.created_by) == User.id",
        foreign_keys="ServiceOrderPhoto.created_by",
        viewonly=True,
    )
