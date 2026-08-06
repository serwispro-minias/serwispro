from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.service_order import ServiceOrder
    from app.models.service_task_attachment import ServiceTaskAttachment
    from app.models.service_task_comment import ServiceTaskComment
    from app.models.service_task_status_history import ServiceTaskStatusHistory
    from app.models.service_task_time_entry import ServiceTaskTimeEntry
    from app.models.user import User


class ServiceTaskStatusEnum(str, PyEnum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ServiceTaskPriorityEnum(str, PyEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ServiceTaskTypeEnum(str, PyEnum):
    DIAGNOSIS = "DIAGNOSIS"
    REPAIR = "REPAIR"
    TESTS = "TESTS"
    CUSTOMER_CONTACT = "CUSTOMER_CONTACT"
    PARTS_ORDER = "PARTS_ORDER"
    ASSEMBLY = "ASSEMBLY"
    PICKUP = "PICKUP"
    OTHER = "OTHER"


SERVICE_TASK_STATUS_CHOICES: list[tuple[str, str]] = [
    (ServiceTaskStatusEnum.NEW.value, "Nowe"),
    (ServiceTaskStatusEnum.ASSIGNED.value, "Przypisane"),
    (ServiceTaskStatusEnum.IN_PROGRESS.value, "W trakcie"),
    (ServiceTaskStatusEnum.WAITING.value, "Oczekuje"),
    (ServiceTaskStatusEnum.DONE.value, "Zakończone"),
    (ServiceTaskStatusEnum.CANCELLED.value, "Anulowane"),
]

SERVICE_TASK_PRIORITY_CHOICES: list[tuple[str, str]] = [
    (ServiceTaskPriorityEnum.LOW.value, "Niski"),
    (ServiceTaskPriorityEnum.NORMAL.value, "Normalny"),
    (ServiceTaskPriorityEnum.HIGH.value, "Wysoki"),
    (ServiceTaskPriorityEnum.URGENT.value, "Pilny"),
]

SERVICE_TASK_TYPE_CHOICES: list[tuple[str, str]] = [
    (ServiceTaskTypeEnum.DIAGNOSIS.value, "Diagnoza"),
    (ServiceTaskTypeEnum.REPAIR.value, "Naprawa"),
    (ServiceTaskTypeEnum.TESTS.value, "Testy"),
    (ServiceTaskTypeEnum.CUSTOMER_CONTACT.value, "Kontakt z klientem"),
    (ServiceTaskTypeEnum.PARTS_ORDER.value, "Zamówienie części"),
    (ServiceTaskTypeEnum.ASSEMBLY.value, "Montaż"),
    (ServiceTaskTypeEnum.PICKUP.value, "Odbiór"),
    (ServiceTaskTypeEnum.OTHER.value, "Inne"),
]

SERVICE_TASK_STATUS_LABELS = dict(SERVICE_TASK_STATUS_CHOICES)
SERVICE_TASK_PRIORITY_LABELS = dict(SERVICE_TASK_PRIORITY_CHOICES)
SERVICE_TASK_TYPE_LABELS = dict(SERVICE_TASK_TYPE_CHOICES)


class ServiceTask(BaseTenantModel):
    __tablename__ = "service_tasks"
    __table_args__ = (
        Index("ix_service_tasks_company_id", "company_id"),
        Index("ix_service_tasks_branch_id", "branch_id"),
        Index("ix_service_tasks_service_order_id", "service_order_id"),
        Index("ix_service_tasks_parent_task_id", "parent_task_id"),
        Index("ix_service_tasks_status", "status"),
        Index("ix_service_tasks_priority", "priority"),
        Index("ix_service_tasks_assigned_to", "assigned_to"),
        Index("ix_service_tasks_planned_start", "planned_start"),
        Index("ix_service_tasks_planned_finish", "planned_finish"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    service_order_id: Mapped[int] = mapped_column(ForeignKey("service_orders.id"), nullable=False)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("service_tasks.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    task_type: Mapped[str] = mapped_column(String(40), nullable=False, default=ServiceTaskTypeEnum.OTHER.value)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=ServiceTaskStatusEnum.NEW.value)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=ServiceTaskPriorityEnum.NORMAL.value)

    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    planned_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_finish: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worked_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    service_order: Mapped["ServiceOrder"] = relationship("ServiceOrder", back_populates="tasks")
    assignee: Mapped["User | None"] = relationship("User", lazy="select")

    parent_task: Mapped["ServiceTask | None"] = relationship(
        "ServiceTask",
        remote_side="ServiceTask.id",
        back_populates="child_tasks",
        lazy="select",
    )
    child_tasks: Mapped[list["ServiceTask"]] = relationship(
        "ServiceTask",
        back_populates="parent_task",
        lazy="select",
        cascade="all, delete-orphan",
    )

    comments: Mapped[list["ServiceTaskComment"]] = relationship(
        "ServiceTaskComment",
        back_populates="task",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceTaskComment.created_at.asc()",
    )
    attachments: Mapped[list["ServiceTaskAttachment"]] = relationship(
        "ServiceTaskAttachment",
        back_populates="task",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceTaskAttachment.created_at.asc()",
    )
    time_entries: Mapped[list["ServiceTaskTimeEntry"]] = relationship(
        "ServiceTaskTimeEntry",
        back_populates="task",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceTaskTimeEntry.started_at.asc()",
    )
    status_history: Mapped[list["ServiceTaskStatusHistory"]] = relationship(
        "ServiceTaskStatusHistory",
        back_populates="task",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceTaskStatusHistory.changed_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<ServiceTask id={self.id} status={self.status} title={self.title!r}>"
