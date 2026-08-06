from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.branch import Branch
from app.models.company import Company
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.service_order_timeline import ServiceOrderTimelineEntry
from app.models.setting import Setting


class ServiceOrderPrintRepository:
    """Read-only repository for service order protocol data."""

    def get_service_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .options(
                selectinload(ServiceOrder.customer),
                selectinload(ServiceOrder.device),
            )
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalar(query)

    def get_company(self, *, company_id: int) -> Company | None:
        return db.session.scalar(
            select(Company)
            .where(Company.id == company_id)
            .where(Company.is_active.is_(True))
        )

    def get_branch(self, *, branch_id: int | None, company_id: int) -> Branch | None:
        if branch_id is None:
            return None

        return db.session.scalar(
            select(Branch)
            .where(Branch.id == branch_id)
            .where(Branch.company_id == company_id)
            .where(Branch.is_active.is_(True))
        )

    def get_settings_map(self, *, company_id: int, branch_id: int | None) -> dict[str, str]:
        query = (
            select(Setting)
            .where(Setting.company_id == company_id)
            .where(Setting.is_active.is_(True))
        )

        settings = list(db.session.scalars(query).all())
        grouped: dict[str, list[Setting]] = defaultdict(list)
        for setting in settings:
            grouped[(setting.key or "").strip()].append(setting)

        resolved: dict[str, str] = {}
        for key, items in grouped.items():
            if not key:
                continue

            selected: Setting | None = None
            if branch_id is not None:
                branch_scoped = [item for item in items if item.branch_id == branch_id]
                if branch_scoped:
                    selected = sorted(branch_scoped, key=lambda item: item.id, reverse=True)[0]

            if selected is None:
                global_scoped = [item for item in items if item.branch_id is None]
                if global_scoped:
                    selected = sorted(global_scoped, key=lambda item: item.id, reverse=True)[0]

            if selected is None:
                selected = sorted(items, key=lambda item: item.id, reverse=True)[0]

            resolved[key] = (selected.value or "").strip()

        return resolved

    def list_timeline_entries(
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

    def list_actions_for_order(
        self,
        *,
        order_id: int,
    ) -> list[ServiceOrderAction]:
        query = (
            select(ServiceOrderAction)
            .options(selectinload(ServiceOrderAction.technician))
            .where(ServiceOrderAction.service_order_id == order_id)
            .order_by(ServiceOrderAction.action_date.asc(), ServiceOrderAction.id.asc())
        )
        return list(db.session.scalars(query).all())

    def list_order_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> list[ServiceOrderPhoto]:
        query = (
            select(ServiceOrderPhoto)
            .where(ServiceOrderPhoto.service_order_id == order_id)
            .where(ServiceOrderPhoto.company_id == company_id)
            .where(ServiceOrderPhoto.is_active.is_(True))
            .order_by(ServiceOrderPhoto.sort_order.asc(), ServiceOrderPhoto.taken_at.desc(), ServiceOrderPhoto.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceOrderPhoto.branch_id == branch_id)
        return list(db.session.scalars(query).all())
