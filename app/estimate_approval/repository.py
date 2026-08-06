from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.company import Company
from app.models.estimate_approval_token import EstimateApprovalToken
from app.models.service_estimate import ServiceEstimate
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.setting import Setting


class EstimateApprovalRepository:
    def get_estimate(self, *, estimate_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimate | None:
        query = (
            select(ServiceEstimate)
            .options(
                selectinload(ServiceEstimate.items),
                selectinload(ServiceEstimate.service_order).selectinload(ServiceOrder.customer),
                selectinload(ServiceEstimate.service_order).selectinload(ServiceOrder.device),
            )
            .where(ServiceEstimate.id == estimate_id)
            .where(ServiceEstimate.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(ServiceEstimate.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceEstimate.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def get_token(self, *, token_value: str) -> EstimateApprovalToken | None:
        query = (
            select(EstimateApprovalToken)
            .options(
                selectinload(EstimateApprovalToken.estimate).selectinload(ServiceEstimate.items),
                selectinload(EstimateApprovalToken.estimate)
                .selectinload(ServiceEstimate.service_order)
                .selectinload(ServiceOrder.customer),
                selectinload(EstimateApprovalToken.estimate)
                .selectinload(ServiceEstimate.service_order)
                .selectinload(ServiceOrder.device),
            )
            .where(EstimateApprovalToken.token == token_value)
            .where(EstimateApprovalToken.is_active.is_(True))
        )
        try:
            return db.session.scalars(query).one_or_none()
        except OperationalError:
            return None

    def get_active_token_for_estimate(self, *, estimate_id: int) -> EstimateApprovalToken | None:
        query = (
            select(EstimateApprovalToken)
            .where(EstimateApprovalToken.estimate_id == estimate_id)
            .where(EstimateApprovalToken.is_active.is_(True))
            .where(EstimateApprovalToken.status == "PENDING")
            .order_by(EstimateApprovalToken.created_at.desc(), EstimateApprovalToken.id.desc())
        )
        try:
            return db.session.scalars(query).first()
        except OperationalError:
            return None

    def expire_pending_tokens(self, *, estimate_id: int, now: datetime) -> int:
        query = (
            select(EstimateApprovalToken)
            .where(EstimateApprovalToken.estimate_id == estimate_id)
            .where(EstimateApprovalToken.is_active.is_(True))
            .where(EstimateApprovalToken.status == "PENDING")
        )
        changed = 0
        try:
            tokens = db.session.scalars(query).all()
        except OperationalError:
            return 0

        for token in tokens:
            token.status = "EXPIRED"
            if token.used_at is None:
                token.used_at = now
            db.session.add(token)
            changed += 1
        if changed:
            db.session.flush()
        return changed

    def create_token(self, payload: dict[str, Any]) -> EstimateApprovalToken:
        token = EstimateApprovalToken(**payload)
        db.session.add(token)
        db.session.flush()
        return token

    def create_order_history_entry(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        description: str,
    ) -> ServiceOrderAction:
        action = ServiceOrderAction(
            service_order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            action_date=datetime.now(timezone.utc).date(),
            technician_id=user_id,
            action_type="CUSTOMER_CONTACT",
            description=description,
            is_visible_for_customer=True,
            created_by=user_id,
            updated_by=user_id,
        )
        db.session.add(action)
        db.session.flush()
        return action

    def create_status_history_entry(
        self,
        *,
        order_id: int,
        old_status: str | None,
        new_status: str,
        changed_by: int | None,
        note: str | None = None,
    ) -> ServiceOrderStatusHistory:
        entry = ServiceOrderStatusHistory(
            service_order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            note=note,
        )
        db.session.add(entry)
        db.session.flush()
        return entry

    def get_company(self, *, company_id: int) -> Company | None:
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

    def save(self, obj: Any) -> Any:
        db.session.add(obj)
        db.session.flush()
        return obj
