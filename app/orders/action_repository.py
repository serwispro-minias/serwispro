from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.service_order_action import ServiceOrderAction
from app.models.user import User


class ServiceOrderActionRepository:
    """Persistence layer for service-order action history."""

    def list_for_order(self, *, order_id: int) -> list[ServiceOrderAction]:
        query = (
            select(ServiceOrderAction)
            .options(selectinload(ServiceOrderAction.technician))
            .where(ServiceOrderAction.service_order_id == order_id)
            .order_by(ServiceOrderAction.action_date.asc(), ServiceOrderAction.id.asc())
        )
        return list(db.session.scalars(query).all())

    def get_for_order(self, *, action_id: int, order_id: int) -> ServiceOrderAction | None:
        query = (
            select(ServiceOrderAction)
            .options(selectinload(ServiceOrderAction.technician))
            .where(ServiceOrderAction.id == action_id)
            .where(ServiceOrderAction.service_order_id == order_id)
        )
        return db.session.scalars(query).one_or_none()

    def create(self, payload: dict[str, object]) -> ServiceOrderAction:
        action = ServiceOrderAction(**payload)
        db.session.add(action)
        db.session.flush()
        return action

    def update(self, action: ServiceOrderAction, payload: dict[str, object]) -> ServiceOrderAction:
        for key, value in payload.items():
            if hasattr(action, key) and key != "id":
                setattr(action, key, value)
        db.session.add(action)
        db.session.flush()
        return action

    def delete(self, action: ServiceOrderAction) -> None:
        db.session.delete(action)
        db.session.flush()

    def list_technicians(self, *, company_id: int) -> list[User]:
        query = (
            select(User)
            .where(User.company_id == company_id)
            .where(User.is_active.is_(True))
            .order_by(User.login.asc(), User.id.asc())
        )
        return list(db.session.scalars(query).all())
