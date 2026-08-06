from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.workflow_status import WorkflowStatus
from app.models.workflow_transition import WorkflowTransition


class WorkflowRepository:
    def list_statuses(self, *, company_id: int, branch_id: int | None) -> list[WorkflowStatus]:
        query = (
            select(WorkflowStatus)
            .where(WorkflowStatus.company_id == company_id)
            .where(WorkflowStatus.is_active.is_(True))
            .order_by(WorkflowStatus.sort_order.asc(), WorkflowStatus.id.asc())
        )
        if branch_id is not None:
            query = query.where(WorkflowStatus.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def has_statuses(self, *, company_id: int, branch_id: int | None) -> bool:
        return len(self.list_statuses(company_id=company_id, branch_id=branch_id)) > 0

    def get_status_by_code(self, *, company_id: int, branch_id: int | None, code: str) -> WorkflowStatus | None:
        query = (
            select(WorkflowStatus)
            .where(WorkflowStatus.company_id == company_id)
            .where(WorkflowStatus.code == code)
            .where(WorkflowStatus.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(WorkflowStatus.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_status(self, status: WorkflowStatus) -> WorkflowStatus:
        db.session.add(status)
        db.session.flush()
        return status

    def list_transitions(self, *, company_id: int, branch_id: int | None) -> list[WorkflowTransition]:
        query = (
            select(WorkflowTransition)
            .options(selectinload(WorkflowTransition.from_status), selectinload(WorkflowTransition.to_status))
            .where(WorkflowTransition.company_id == company_id)
            .where(WorkflowTransition.is_active.is_(True))
            .order_by(WorkflowTransition.id.asc())
        )
        if branch_id is not None:
            query = query.where(WorkflowTransition.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_transitions_from_status(self, *, company_id: int, branch_id: int | None, from_status_id: int) -> list[WorkflowTransition]:
        query = (
            select(WorkflowTransition)
            .options(selectinload(WorkflowTransition.to_status), selectinload(WorkflowTransition.from_status))
            .where(WorkflowTransition.company_id == company_id)
            .where(WorkflowTransition.from_status_id == from_status_id)
            .where(WorkflowTransition.is_active.is_(True))
            .order_by(WorkflowTransition.id.asc())
        )
        if branch_id is not None:
            query = query.where(WorkflowTransition.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def get_transition_by_codes(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        from_status_code: str,
        to_status_code: str,
    ) -> WorkflowTransition | None:
        from_status = self.get_status_by_code(company_id=company_id, branch_id=branch_id, code=from_status_code)
        to_status = self.get_status_by_code(company_id=company_id, branch_id=branch_id, code=to_status_code)
        if from_status is None or to_status is None:
            return None

        query = (
            select(WorkflowTransition)
            .options(selectinload(WorkflowTransition.from_status), selectinload(WorkflowTransition.to_status))
            .where(WorkflowTransition.company_id == company_id)
            .where(WorkflowTransition.from_status_id == from_status.id)
            .where(WorkflowTransition.to_status_id == to_status.id)
            .where(WorkflowTransition.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(WorkflowTransition.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_transition(self, transition: WorkflowTransition) -> WorkflowTransition:
        db.session.add(transition)
        db.session.flush()
        return transition
