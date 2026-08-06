from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.service_order_timeline import ServiceOrderTimelineAttachment, ServiceOrderTimelineEntry


class ServiceOrderTimelineRepository:
    """Persistence layer for service order timeline entries and attachments."""

    def list_entries(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> list[ServiceOrderTimelineEntry]:
        query = (
            select(ServiceOrderTimelineEntry)
            .options(
                selectinload(ServiceOrderTimelineEntry.author_user),
                selectinload(ServiceOrderTimelineEntry.attachments),
            )
            .where(ServiceOrderTimelineEntry.service_order_id == order_id)
            .where(ServiceOrderTimelineEntry.company_id == company_id)
            .where(ServiceOrderTimelineEntry.is_active.is_(True))
            .order_by(ServiceOrderTimelineEntry.created_at.asc(), ServiceOrderTimelineEntry.id.asc())
        )

        if branch_id is not None:
            query = query.where(ServiceOrderTimelineEntry.branch_id == branch_id)

        return list(db.session.scalars(query).all())

    def create_entry(self, data: dict[str, Any]) -> ServiceOrderTimelineEntry:
        entry = ServiceOrderTimelineEntry(**data)
        db.session.add(entry)
        db.session.flush()
        return entry

    def create_attachment(self, data: dict[str, Any]) -> ServiceOrderTimelineAttachment:
        attachment = ServiceOrderTimelineAttachment(**data)
        db.session.add(attachment)
        db.session.flush()
        return attachment

    def get_attachment(
        self,
        *,
        attachment_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> ServiceOrderTimelineAttachment | None:
        query = (
            select(ServiceOrderTimelineAttachment)
            .options(
                selectinload(ServiceOrderTimelineAttachment.entry).selectinload(ServiceOrderTimelineEntry.service_order)
            )
            .where(ServiceOrderTimelineAttachment.id == attachment_id)
            .where(ServiceOrderTimelineAttachment.company_id == company_id)
            .where(ServiceOrderTimelineAttachment.is_active.is_(True))
        )

        if branch_id is not None:
            query = query.where(ServiceOrderTimelineAttachment.branch_id == branch_id)

        return db.session.scalars(query).one_or_none()
