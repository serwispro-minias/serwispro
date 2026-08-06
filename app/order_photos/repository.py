from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.service_order_photo_annotation import PhotoAnnotation
from app.models.service_order import ServiceOrder
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.user import User


class ServiceOrderPhotoRepository:
    def get_order(self, *, order_id: int, company_id: int) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        return db.session.scalar(query)

    def list_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        photo_type: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
        author_id: int | None,
    ) -> list[ServiceOrderPhoto]:
        query = (
            select(ServiceOrderPhoto)
            .options(selectinload(ServiceOrderPhoto.author_user))
            .where(ServiceOrderPhoto.service_order_id == order_id)
            .where(ServiceOrderPhoto.company_id == company_id)
            .where(ServiceOrderPhoto.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceOrderPhoto.branch_id == branch_id)
        if photo_type:
            query = query.where(ServiceOrderPhoto.photo_type == photo_type)
        if author_id is not None:
            query = query.where(ServiceOrderPhoto.created_by == author_id)
        if date_from is not None:
            query = query.where(ServiceOrderPhoto.taken_at >= date_from)
        if date_to is not None:
            query = query.where(ServiceOrderPhoto.taken_at <= date_to)

        query = query.order_by(ServiceOrderPhoto.sort_order.asc(), ServiceOrderPhoto.taken_at.desc(), ServiceOrderPhoto.id.desc())
        return list(db.session.scalars(query).all())

    def get_photo(self, *, photo_id: int, company_id: int, branch_id: int | None) -> ServiceOrderPhoto | None:
        query = (
            select(ServiceOrderPhoto)
            .options(selectinload(ServiceOrderPhoto.author_user), selectinload(ServiceOrderPhoto.service_order))
            .where(ServiceOrderPhoto.id == photo_id)
            .where(ServiceOrderPhoto.company_id == company_id)
            .where(ServiceOrderPhoto.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceOrderPhoto.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_photo(self, payload: dict[str, Any]) -> ServiceOrderPhoto:
        row = ServiceOrderPhoto(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def save(self, row: ServiceOrderPhoto) -> ServiceOrderPhoto:
        db.session.add(row)
        db.session.flush()
        return row

    def list_authors(self, *, order_id: int, company_id: int, branch_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(User.id, User.login)
            .join(ServiceOrderPhoto, and_(ServiceOrderPhoto.created_by == User.id, ServiceOrderPhoto.is_active.is_(True)))
            .where(ServiceOrderPhoto.service_order_id == order_id)
            .where(ServiceOrderPhoto.company_id == company_id)
            .where(User.is_active.is_(True))
            .distinct()
            .order_by(User.login.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceOrderPhoto.branch_id == branch_id)
        return [(int(user_id), login) for user_id, login in db.session.execute(query).all()]

    def list_annotations(
        self,
        *,
        photo_id: int,
        company_id: int,
        branch_id: int | None,
        only_customer_visible: bool,
    ) -> list[PhotoAnnotation]:
        query = (
            select(PhotoAnnotation)
            .where(PhotoAnnotation.photo_id == photo_id)
            .where(PhotoAnnotation.company_id == company_id)
            .where(PhotoAnnotation.is_active.is_(True))
            .order_by(PhotoAnnotation.created_at.asc(), PhotoAnnotation.id.asc())
        )
        if branch_id is not None:
            query = query.where(PhotoAnnotation.branch_id == branch_id)
        if only_customer_visible:
            query = query.where(PhotoAnnotation.is_visible_for_customer.is_(True))
        return list(db.session.scalars(query).all())

    def get_annotation(self, *, annotation_id: int, company_id: int, branch_id: int | None) -> PhotoAnnotation | None:
        query = (
            select(PhotoAnnotation)
            .options(selectinload(PhotoAnnotation.photo).selectinload(ServiceOrderPhoto.service_order))
            .where(PhotoAnnotation.id == annotation_id)
            .where(PhotoAnnotation.company_id == company_id)
            .where(PhotoAnnotation.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(PhotoAnnotation.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_annotation(self, payload: dict[str, Any]) -> PhotoAnnotation:
        row = PhotoAnnotation(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def save_annotation(self, row: PhotoAnnotation) -> PhotoAnnotation:
        db.session.add(row)
        db.session.flush()
        return row
