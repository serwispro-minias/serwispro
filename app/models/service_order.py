from __future__ import annotations

from datetime import date, datetime
from enum import Enum as PyEnum
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseTenantModel

if TYPE_CHECKING:
    from app.models.part_demand import PartDemand
    from app.models.customer import Customer
    from app.models.device import Device
    from app.models.notification_message import NotificationMessage
    from app.models.service_order_photo import ServiceOrderPhoto
    from app.models.service_order_action import ServiceOrderAction
    from app.models.service_estimate import ServiceEstimate
    from app.models.service_order_item import ServiceOrderItem
    from app.models.service_order_part_usage import ServiceOrderPartUsage
    from app.models.service_order_part_reservation import ServiceOrderPartReservation
    from app.models.service_order_status_history import ServiceOrderStatusHistory
    from app.models.service_task import ServiceTask
    from app.models.service_order_timeline import ServiceOrderTimelineEntry


class ServiceOrderStatusEnum(str, PyEnum):
    """Supported service order statuses."""

    RECEIVED = "RECEIVED"
    DIAGNOSIS = "DIAGNOSIS"
    WAITING_PARTS = "WAITING_PARTS"
    WAITING_CUSTOMER_DECISION = "WAITING_CUSTOMER_DECISION"
    READY_FOR_REPAIR = "READY_FOR_REPAIR"
    IN_REPAIR = "IN_REPAIR"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    ISSUED = "ISSUED"
    CANCELLED = "CANCELLED"


class ServiceOrderPriorityEnum(str, PyEnum):
    """Supported service order priorities."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


SERVICE_ORDER_STATUS_CHOICES: list[tuple[str, str]] = [
    (ServiceOrderStatusEnum.RECEIVED.value, "Przyjęte"),
    (ServiceOrderStatusEnum.DIAGNOSIS.value, "Diagnoza"),
    (ServiceOrderStatusEnum.WAITING_PARTS.value, "Oczekuje na części"),
    (ServiceOrderStatusEnum.WAITING_CUSTOMER_DECISION.value, "Oczekiwanie na decyzję klienta"),
    (ServiceOrderStatusEnum.READY_FOR_REPAIR.value, "Gotowe do naprawy"),
    (ServiceOrderStatusEnum.IN_REPAIR.value, "W naprawie"),
    (ServiceOrderStatusEnum.READY_FOR_PICKUP.value, "Gotowe do odbioru"),
    (ServiceOrderStatusEnum.ISSUED.value, "Wydane"),
    (ServiceOrderStatusEnum.CANCELLED.value, "Anulowane"),
]

SERVICE_ORDER_PRIORITY_CHOICES: list[tuple[str, str]] = [
    (ServiceOrderPriorityEnum.LOW.value, "Niski"),
    (ServiceOrderPriorityEnum.NORMAL.value, "Normalny"),
    (ServiceOrderPriorityEnum.HIGH.value, "Wysoki"),
    (ServiceOrderPriorityEnum.URGENT.value, "Pilny"),
]

SERVICE_ORDER_STATUS_LABELS = dict(SERVICE_ORDER_STATUS_CHOICES)
SERVICE_ORDER_PRIORITY_LABELS = dict(SERVICE_ORDER_PRIORITY_CHOICES)
SERVICE_ORDER_STATUS_BADGE_CLASSES: dict[str, str] = {
    ServiceOrderStatusEnum.RECEIVED.value: "bg-secondary",
    ServiceOrderStatusEnum.DIAGNOSIS.value: "bg-info text-dark",
    ServiceOrderStatusEnum.WAITING_PARTS.value: "bg-warning text-dark",
    ServiceOrderStatusEnum.WAITING_CUSTOMER_DECISION.value: "bg-warning text-dark",
    ServiceOrderStatusEnum.READY_FOR_REPAIR.value: "bg-primary-subtle text-dark",
    ServiceOrderStatusEnum.IN_REPAIR.value: "bg-primary",
    ServiceOrderStatusEnum.READY_FOR_PICKUP.value: "bg-success",
    ServiceOrderStatusEnum.ISSUED.value: "bg-dark",
    ServiceOrderStatusEnum.CANCELLED.value: "bg-danger",
}


class ServiceOrder(BaseTenantModel):
    """Service order representing a repair ticket in SerwisPRO."""

    __tablename__ = "service_orders"
    __table_args__ = (
        Index("ix_service_orders_company_id", "company_id"),
        Index("ix_service_orders_branch_id", "branch_id"),
        Index("ix_service_orders_customer_id", "customer_id"),
        Index("ix_service_orders_device_id", "device_id"),
        Index("ix_service_orders_order_number", "order_number"),
        Index("ix_service_orders_status", "status"),
        Index("ix_service_orders_priority", "priority"),
        Index("ix_service_orders_external_reference", "external_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=ServiceOrderStatusEnum.RECEIVED.value,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ServiceOrderPriorityEnum.NORMAL.value,
    )
    intake_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    planned_finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    warranty_repair: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    repair_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    technician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    final_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="service_orders")
    device: Mapped["Device"] = relationship("Device", back_populates="service_orders")
    status_history: Mapped[list["ServiceOrderStatusHistory"]] = relationship(
        "ServiceOrderStatusHistory",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
    )
    timeline_entries: Mapped[list["ServiceOrderTimelineEntry"]] = relationship(
        "ServiceOrderTimelineEntry",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderTimelineEntry.created_at.asc()",
    )
    part_usages: Mapped[list["ServiceOrderPartUsage"]] = relationship(
        "ServiceOrderPartUsage",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderPartUsage.created_at.asc()",
    )
    part_reservations: Mapped[list["ServiceOrderPartReservation"]] = relationship(
        "ServiceOrderPartReservation",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderPartReservation.created_at.asc()",
    )
    items: Mapped[list["ServiceOrderItem"]] = relationship(
        "ServiceOrderItem",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderItem.created_at.asc()",
    )
    estimates: Mapped[list["ServiceEstimate"]] = relationship(
        "ServiceEstimate",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceEstimate.version_number.asc(), ServiceEstimate.id.asc()",
    )
    notification_messages: Mapped[list["NotificationMessage"]] = relationship(
        "NotificationMessage",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="NotificationMessage.created_at.asc()",
    )
    actions: Mapped[list["ServiceOrderAction"]] = relationship(
        "ServiceOrderAction",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderAction.action_date.asc(), ServiceOrderAction.id.asc()",
    )
    tasks: Mapped[list["ServiceTask"]] = relationship(
        "ServiceTask",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceTask.created_at.asc(), ServiceTask.id.asc()",
    )
    part_demands: Mapped[list["PartDemand"]] = relationship(
        "PartDemand",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="PartDemand.created_at.asc(), PartDemand.id.asc()",
    )
    photos: Mapped[list["ServiceOrderPhoto"]] = relationship(
        "ServiceOrderPhoto",
        back_populates="service_order",
        lazy="select",
        cascade="all, delete-orphan",
        order_by="ServiceOrderPhoto.sort_order.asc(), ServiceOrderPhoto.created_at.asc(), ServiceOrderPhoto.id.asc()",
    )

    def __repr__(self) -> str:
        return f"<ServiceOrder id={self.id} order_number={self.order_number}>"
