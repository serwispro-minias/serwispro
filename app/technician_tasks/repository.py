from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.service_task import ServiceTask, ServiceTaskStatusEnum
from app.models.service_task_attachment import ServiceTaskAttachment
from app.models.service_task_comment import ServiceTaskComment
from app.models.service_task_status_history import ServiceTaskStatusHistory
from app.models.service_task_time_entry import ServiceTaskTimeEntry
from app.models.user import User


class ServiceTaskRepository:
    def list_for_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .options(
                selectinload(ServiceTask.assignee),
                selectinload(ServiceTask.comments),
                selectinload(ServiceTask.attachments),
                selectinload(ServiceTask.time_entries),
            )
            .where(ServiceTask.service_order_id == order_id)
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.is_active.is_(True))
            .order_by(ServiceTask.priority.desc(), ServiceTask.planned_finish.asc(), ServiceTask.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def get_by_id(self, *, task_id: int, company_id: int, branch_id: int | None) -> ServiceTask | None:
        query = (
            select(ServiceTask)
            .options(
                selectinload(ServiceTask.assignee),
                selectinload(ServiceTask.comments).selectinload(ServiceTaskComment.author),
                selectinload(ServiceTask.attachments),
                selectinload(ServiceTask.time_entries).selectinload(ServiceTaskTimeEntry.user),
                selectinload(ServiceTask.status_history).selectinload(ServiceTaskStatusHistory.changed_by_user),
            )
            .where(ServiceTask.id == task_id)
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_task(self, payload: dict[str, object]) -> ServiceTask:
        task = ServiceTask(**payload)
        db.session.add(task)
        db.session.flush()
        return task

    def update_task(self, task: ServiceTask, payload: dict[str, object]) -> ServiceTask:
        for key, value in payload.items():
            if hasattr(task, key) and key != "id":
                setattr(task, key, value)
        db.session.add(task)
        db.session.flush()
        return task

    def delete_task(self, task: ServiceTask) -> None:
        db.session.delete(task)
        db.session.flush()

    def list_parent_choices(self, *, order_id: int, company_id: int, branch_id: int | None, exclude_task_id: int | None = None) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .where(ServiceTask.service_order_id == order_id)
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.is_active.is_(True))
            .order_by(ServiceTask.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        if exclude_task_id is not None:
            query = query.where(ServiceTask.id != exclude_task_id)
        return list(db.session.scalars(query).all())

    def list_technicians(self, *, company_id: int, branch_id: int | None) -> list[User]:
        query = (
            select(User)
            .where(User.company_id == company_id)
            .where(User.is_active.is_(True))
            .order_by(User.login.asc(), User.id.asc())
        )
        if branch_id is not None:
            query = query.where(User.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def create_comment(self, payload: dict[str, object]) -> ServiceTaskComment:
        row = ServiceTaskComment(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def create_attachment(self, payload: dict[str, object]) -> ServiceTaskAttachment:
        row = ServiceTaskAttachment(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def get_attachment(self, *, attachment_id: int, company_id: int, branch_id: int | None) -> ServiceTaskAttachment | None:
        query = (
            select(ServiceTaskAttachment)
            .options(selectinload(ServiceTaskAttachment.task))
            .where(ServiceTaskAttachment.id == attachment_id)
            .where(ServiceTaskAttachment.company_id == company_id)
            .where(ServiceTaskAttachment.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceTaskAttachment.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_time_entry(self, payload: dict[str, object]) -> ServiceTaskTimeEntry:
        row = ServiceTaskTimeEntry(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def update_time_entry(self, row: ServiceTaskTimeEntry, payload: dict[str, object]) -> ServiceTaskTimeEntry:
        for key, value in payload.items():
            if hasattr(row, key) and key != "id":
                setattr(row, key, value)
        db.session.add(row)
        db.session.flush()
        return row

    def get_open_time_entry(self, *, task_id: int, user_id: int | None) -> ServiceTaskTimeEntry | None:
        query = (
            select(ServiceTaskTimeEntry)
            .where(ServiceTaskTimeEntry.service_task_id == task_id)
            .where(ServiceTaskTimeEntry.ended_at.is_(None))
            .where(ServiceTaskTimeEntry.is_active.is_(True))
            .order_by(ServiceTaskTimeEntry.started_at.desc(), ServiceTaskTimeEntry.id.desc())
        )
        if user_id is not None:
            query = query.where(ServiceTaskTimeEntry.user_id == user_id)
        return db.session.scalars(query).one_or_none()

    def list_time_entries(self, *, task_id: int) -> list[ServiceTaskTimeEntry]:
        query = (
            select(ServiceTaskTimeEntry)
            .options(selectinload(ServiceTaskTimeEntry.user))
            .where(ServiceTaskTimeEntry.service_task_id == task_id)
            .where(ServiceTaskTimeEntry.is_active.is_(True))
            .order_by(ServiceTaskTimeEntry.started_at.asc(), ServiceTaskTimeEntry.id.asc())
        )
        return list(db.session.scalars(query).all())

    def create_status_history(self, payload: dict[str, object]) -> ServiceTaskStatusHistory:
        row = ServiceTaskStatusHistory(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def has_overdue_notification(self, *, task_id: int) -> bool:
        query = (
            select(ServiceTaskStatusHistory.id)
            .where(ServiceTaskStatusHistory.service_task_id == task_id)
            .where(ServiceTaskStatusHistory.note == "OVERDUE_NOTIFIED")
        )
        return db.session.scalar(query) is not None

    def list_my_tasks(self, *, actor_id: int, company_id: int, branch_id: int | None) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .options(selectinload(ServiceTask.assignee))
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.assigned_to == actor_id)
            .where(ServiceTask.is_active.is_(True))
            .where(ServiceTask.status.notin_([ServiceTaskStatusEnum.DONE.value, ServiceTaskStatusEnum.CANCELLED.value]))
            .order_by(ServiceTask.priority.desc(), ServiceTask.planned_finish.asc(), ServiceTask.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_team_tasks(self, *, company_id: int, branch_id: int | None) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .options(selectinload(ServiceTask.assignee))
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.is_active.is_(True))
            .order_by(ServiceTask.priority.desc(), ServiceTask.planned_finish.asc(), ServiceTask.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_tasks_for_status(self, *, company_id: int, branch_id: int | None, status: str) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .options(selectinload(ServiceTask.assignee))
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.status == status)
            .where(ServiceTask.is_active.is_(True))
            .order_by(ServiceTask.priority.desc(), ServiceTask.planned_finish.asc(), ServiceTask.id.asc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def find_open_task_by_title(self, *, order_id: int, company_id: int, branch_id: int | None, title: str) -> ServiceTask | None:
        query = (
            select(ServiceTask)
            .where(ServiceTask.service_order_id == order_id)
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.title == title)
            .where(ServiceTask.status.notin_([ServiceTaskStatusEnum.DONE.value, ServiceTaskStatusEnum.CANCELLED.value]))
            .where(ServiceTask.is_active.is_(True))
            .order_by(ServiceTask.id.desc())
        )
        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        return db.session.scalars(query).first()

    def search_tasks(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        actor_id: int | None,
        only_mine: bool,
        query_text: str | None,
        status: str | None,
        priority: str | None,
        assigned_to: int | None,
    ) -> list[ServiceTask]:
        query = (
            select(ServiceTask)
            .options(selectinload(ServiceTask.assignee))
            .where(ServiceTask.company_id == company_id)
            .where(ServiceTask.is_active.is_(True))
        )

        if branch_id is not None:
            query = query.where(ServiceTask.branch_id == branch_id)
        if only_mine and actor_id is not None:
            query = query.where(ServiceTask.assigned_to == actor_id)
        if status:
            query = query.where(ServiceTask.status == status)
        if priority:
            query = query.where(ServiceTask.priority == priority)
        if assigned_to:
            query = query.where(ServiceTask.assigned_to == assigned_to)
        if query_text:
            like_pattern = f"%{query_text.strip()}%"
            query = query.where(or_(ServiceTask.title.ilike(like_pattern), ServiceTask.description.ilike(like_pattern)))

        return list(db.session.scalars(query.order_by(ServiceTask.priority.desc(), ServiceTask.planned_finish.asc(), ServiceTask.id.asc())).all())
