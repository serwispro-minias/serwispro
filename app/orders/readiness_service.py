from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models.catalog_part import CatalogPart
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation


OPEN_PURCHASE_STATUSES = {
    PurchaseOrderStatusEnum.DRAFT.value,
    PurchaseOrderStatusEnum.SENT.value,
    PurchaseOrderStatusEnum.CONFIRMED.value,
    PurchaseOrderStatusEnum.PARTIAL.value,
}


@dataclass(slots=True)
class ReadinessPart:
    part_id: int
    code: str
    name: str
    required: Decimal
    available: Decimal
    reserved: Decimal
    to_order: Decimal

    @property
    def status(self) -> str:
        if self.to_order > 0 and self.reserved + self.available <= 0:
            return "NONE"
        if self.to_order > 0:
            return "PARTIAL"
        return "READY"


class OrderReadinessService:
    def build(self, *, order_id: int, company_id: int, branch_id: int | None) -> dict[str, object]:
        try:
            return self._build(order_id=order_id, company_id=company_id, branch_id=branch_id)
        except OperationalError:
            db.session.rollback()
            return {
                "status": "NONE",
                "percentage": 0,
                "lines": [],
                "pending_purchases": 0,
                "purchase_statuses": {},
                "expected_delivery": None,
            }

    def _build(self, *, order_id: int, company_id: int, branch_id: int | None) -> dict[str, object]:
        order_scope = [ServiceEstimate.service_order_id == order_id, ServiceEstimate.company_id == company_id]
        if branch_id is not None:
            order_scope.append(ServiceEstimate.branch_id == branch_id)
        estimate_id = db.session.scalar(
            select(ServiceEstimate.id)
            .where(*order_scope)
            .where(ServiceEstimate.is_active.is_(True))
            .order_by(ServiceEstimate.version_number.desc(), ServiceEstimate.id.desc())
            .limit(1)
        )

        required: dict[int, Decimal] = {}
        if estimate_id is not None:
            estimate_rows = db.session.execute(
                select(ServiceEstimateItem.source_id, ServiceEstimateItem.quantity)
                .where(ServiceEstimateItem.estimate_id == estimate_id)
                .where(ServiceEstimateItem.source_type == "PART")
                .where(ServiceEstimateItem.source_id.is_not(None))
            ).all()
            for part_id, quantity in estimate_rows:
                required[int(part_id)] = required.get(int(part_id), Decimal("0")) + Decimal(quantity)

        demand_scope = [PartDemand.service_order_id == order_id, PartDemand.company_id == company_id]
        if branch_id is not None:
            demand_scope.append(PartDemand.branch_id == branch_id)
        demand_rows = db.session.execute(
            select(PartDemand.inventory_item_id, func.sum(PartDemand.requested_quantity))
            .where(*demand_scope)
            .where(PartDemand.is_active.is_(True))
            .where(PartDemand.status.notin_([PartDemandStatusEnum.CANCELLED.value]))
            .group_by(PartDemand.inventory_item_id)
        ).all()
        for part_id, quantity in demand_rows:
            required[int(part_id)] = required.get(int(part_id), Decimal("0")) + Decimal(quantity or 0)

        reservation_scope = [ServiceOrderPartReservation.service_order_id == order_id, ServiceOrderPartReservation.company_id == company_id]
        if branch_id is not None:
            reservation_scope.append(ServiceOrderPartReservation.branch_id == branch_id)
        reservation_rows = db.session.execute(
            select(ServiceOrderPartReservation.part_id, func.sum(ServiceOrderPartReservation.quantity))
            .where(*reservation_scope)
            .where(ServiceOrderPartReservation.is_active.is_(True))
            .where(ServiceOrderPartReservation.status == "RESERVED")
            .group_by(ServiceOrderPartReservation.part_id)
        ).all()
        reserved = {int(part_id): Decimal(quantity or 0) for part_id, quantity in reservation_rows}

        part_ids = list(required)
        parts = {}
        if part_ids:
            part_rows = db.session.scalars(
                select(CatalogPart)
                .where(CatalogPart.id.in_(part_ids))
                .where(CatalogPart.company_id == company_id)
                .where(or_(CatalogPart.branch_id == branch_id, CatalogPart.branch_id.is_(None)) if branch_id is not None else True)
            ).all()
            parts = {part.id: part for part in part_rows}

        lines: list[ReadinessPart] = []
        for part_id, quantity in required.items():
            part = parts.get(part_id)
            if part is None:
                continue
            stock = max(Decimal("0"), Decimal(part.current_stock or 0))
            required_quantity = max(Decimal("0"), quantity)
            reserved_quantity = reserved.get(part_id, Decimal("0"))
            to_order = max(Decimal("0"), required_quantity - reserved_quantity - stock)
            lines.append(ReadinessPart(part_id, part.code, part.name, required_quantity, stock, reserved_quantity, to_order))

        total_required = sum((line.required for line in lines), Decimal("0"))
        total_covered = sum((min(line.required, line.reserved + line.available) for line in lines), Decimal("0"))
        percentage = int((total_covered / total_required * 100).quantize(Decimal("1"))) if total_required else 0
        complete_count = sum(1 for line in lines if line.to_order == 0)
        if not lines or total_required == 0:
            status = "NONE"
        elif complete_count == len(lines):
            status = "READY"
        else:
            status = "PARTIAL"

        purchase_scope = [
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.is_active.is_(True),
            PurchaseOrderItem.purchase_order_id == PurchaseOrder.id,
            PurchaseOrderDemandLink.purchase_order_item_id == PurchaseOrderItem.id,
            PurchaseOrderDemandLink.part_demand_id.in_(select(PartDemand.id).where(*demand_scope)),
        ]
        if branch_id is not None:
            purchase_scope.append(PurchaseOrder.branch_id == branch_id)
        purchase_rows = db.session.execute(
            select(PurchaseOrder.status, func.count(distinct(PurchaseOrder.id)))
            .select_from(PurchaseOrder)
            .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
            .join(PurchaseOrderDemandLink, PurchaseOrderDemandLink.purchase_order_item_id == PurchaseOrderItem.id)
            .where(*purchase_scope)
            .where(PurchaseOrder.status.in_(list(OPEN_PURCHASE_STATUSES)))
            .group_by(PurchaseOrder.status)
        ).all()
        purchase_statuses = {str(status): int(count) for status, count in purchase_rows}

        return {
            "status": status,
            "percentage": min(100, max(0, percentage)),
            "lines": [asdict(line) | {"status": line.status} for line in lines],
            "pending_purchases": sum(purchase_statuses.values()),
            "purchase_statuses": purchase_statuses,
            "expected_delivery": None,
        }
