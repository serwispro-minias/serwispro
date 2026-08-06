from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.company import Company
from app.models.device import Device
from app.models.notification_message import NotificationMessage
from app.models.notification_template import NotificationTemplate
from app.models.service_order import ServiceOrder
from app.models.setting import Setting


class NotificationRepository:
    def get_order(self, order_id: int, *, company_id: int | None, branch_id: int | None) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.is_active.is_(True))
            .options(
                selectinload(ServiceOrder.customer),
                selectinload(ServiceOrder.device),
            )
        )
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def get_company(self, company_id: int) -> Company | None:
        return db.session.get(Company, company_id)

    def get_settings_map(self, *, company_id: int, branch_id: int | None) -> dict[str, str]:
        query = select(Setting).where(Setting.company_id == company_id).where(Setting.is_active.is_(True))
        if branch_id is not None:
            query = query.where(or_(Setting.branch_id.is_(None), Setting.branch_id == branch_id))
        settings = db.session.scalars(query).all()

        ordered = sorted(settings, key=lambda item: (item.key, item.branch_id is None))
        result: dict[str, str] = {}
        for item in ordered:
            result[item.key] = item.value or ""
        return result

    def upsert_setting(self, *, company_id: int, branch_id: int | None, key: str, value: str, user_id: int | None) -> Setting:
        setting = db.session.scalar(
            select(Setting)
            .where(Setting.company_id == company_id)
            .where(Setting.branch_id.is_(branch_id) if branch_id is None else Setting.branch_id == branch_id)
            .where(Setting.key == key)
        )
        if setting is None:
            setting = Setting(
                company_id=company_id,
                branch_id=branch_id,
                key=key,
                value=value,
                created_by=user_id,
                updated_by=user_id,
            )
            db.session.add(setting)
        else:
            setting.value = value
            setting.updated_by = user_id
            setting.is_active = True
            db.session.add(setting)
        db.session.flush()
        return setting

    def list_templates(self, *, company_id: int) -> list[NotificationTemplate]:
        return list(
            db.session.scalars(
                select(NotificationTemplate)
                .where(NotificationTemplate.company_id == company_id)
                .where(NotificationTemplate.is_active.is_(True))
                .order_by(NotificationTemplate.event_key.asc(), NotificationTemplate.channel.asc(), NotificationTemplate.id.asc())
            ).all()
        )

    def get_template_by_id(self, template_id: int, *, company_id: int) -> NotificationTemplate | None:
        return db.session.scalars(
            select(NotificationTemplate)
            .where(NotificationTemplate.id == template_id)
            .where(NotificationTemplate.company_id == company_id)
            .where(NotificationTemplate.is_active.is_(True))
        ).one_or_none()

    def get_template_by_event_channel(self, *, company_id: int, event_key: str, channel: str) -> NotificationTemplate | None:
        return db.session.scalars(
            select(NotificationTemplate)
            .where(NotificationTemplate.company_id == company_id)
            .where(NotificationTemplate.event_key == event_key)
            .where(NotificationTemplate.channel == channel)
            .where(NotificationTemplate.is_active.is_(True))
            .where(NotificationTemplate.is_enabled.is_(True))
            .order_by(NotificationTemplate.id.desc())
        ).first()

    def save_template(self, template: NotificationTemplate) -> NotificationTemplate:
        db.session.add(template)
        db.session.flush()
        return template

    def create_message(self, payload: dict[str, object]) -> NotificationMessage:
        message = NotificationMessage(**payload)
        db.session.add(message)
        db.session.flush()
        return message

    def list_messages_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[NotificationMessage]:
        query = (
            select(NotificationMessage)
            .where(NotificationMessage.service_order_id == order_id)
            .where(NotificationMessage.is_active.is_(True))
            .options(
                selectinload(NotificationMessage.user),
                selectinload(NotificationMessage.template),
            )
            .order_by(NotificationMessage.created_at.desc(), NotificationMessage.id.desc())
        )
        if company_id is not None:
            query = query.where(NotificationMessage.company_id == company_id)
        if branch_id is not None:
            query = query.where(NotificationMessage.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def get_message(self, message_id: int, *, company_id: int | None, branch_id: int | None) -> NotificationMessage | None:
        query = (
            select(NotificationMessage)
            .where(NotificationMessage.id == message_id)
            .where(NotificationMessage.is_active.is_(True))
            .options(selectinload(NotificationMessage.template))
        )
        if company_id is not None:
            query = query.where(NotificationMessage.company_id == company_id)
        if branch_id is not None:
            query = query.where(NotificationMessage.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def count_templates(self, *, company_id: int) -> int:
        return int(
            db.session.scalar(
                select(func.count())
                .select_from(NotificationTemplate)
                .where(NotificationTemplate.company_id == company_id)
                .where(NotificationTemplate.is_active.is_(True))
            )
            or 0
        )
