from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_order_photo import ServiceOrderPhoto


PHOTO_ANNOTATION_TYPE_CHOICES: list[tuple[str, str]] = [
    ("PIN", "Pin"),
    ("CIRCLE", "Kolko"),
    ("RECTANGLE", "Prostokat"),
    ("ARROW", "Strzalka"),
    ("LINE", "Linia"),
    ("POLYGON", "Poligon"),
    ("TEXT", "Tekst"),
    ("NUMBER", "Numer"),
]

PHOTO_ANNOTATION_PRIORITY_CHOICES: list[tuple[str, str]] = [
    ("LOW", "Niski"),
    ("NORMAL", "Normalny"),
    ("HIGH", "Wysoki"),
    ("CRITICAL", "Krytyczny"),
]

PHOTO_ANNOTATION_TYPE_LABELS = dict(PHOTO_ANNOTATION_TYPE_CHOICES)
PHOTO_ANNOTATION_PRIORITY_LABELS = dict(PHOTO_ANNOTATION_PRIORITY_CHOICES)


class PhotoAnnotation(BaseTenantModel):
    __tablename__ = "service_order_photo_annotations"
    __table_args__ = (
        Index("ix_photo_annotations_company_id", "company_id"),
        Index("ix_photo_annotations_branch_id", "branch_id"),
        Index("ix_photo_annotations_photo_id", "photo_id"),
        Index("ix_photo_annotations_type", "annotation_type"),
        Index("ix_photo_annotations_priority", "priority"),
        Index("ix_photo_annotations_visible", "is_visible_for_customer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("service_order_photos.id"), nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    x: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    y: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    width: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    height: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    rotation: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#ff3b30")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL")
    is_visible_for_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo: Mapped["ServiceOrderPhoto"] = relationship("ServiceOrderPhoto", back_populates="annotations")
