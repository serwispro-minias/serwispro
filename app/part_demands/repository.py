from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.branch import Branch
from app.models.catalog_part import CatalogPart
from app.models.part_demand import PartDemand, PartDemandStatusEnum
from app.models.service_order import ServiceOrder


@dataclass(slots=True)
class PartDemandGroupedRow:
    inventory_item_id: int
    part_code: str
    part_name: str
    total_missing: Decimal
    order_numbers: list[str]
    demand_ids: list[int]


class PartDemandRepository:
    def list_for_scope(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        status: str | None,
        priority: str | None,
        branch_filter_id: int | None,
        order_id: int | None,
        inventory_item_id: int | None,
        expected_date_from: date | None,
        expected_date_to: date | None,
        query_text: str | None,
    ) -> list[PartDemand]:
        query = (
            select(PartDemand)
            .options(
                selectinload(PartDemand.inventory_item),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.customer),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.device),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.actions),
            )
            .where(PartDemand.company_id == company_id)
            .where(PartDemand.is_active.is_(True))
        )

        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        if branch_filter_id is not None:
            query = query.where(PartDemand.branch_id == branch_filter_id)
        if status:
            query = query.where(PartDemand.status == status)
        if priority:
            query = query.where(PartDemand.priority == priority)
        if order_id:
            query = query.where(PartDemand.service_order_id == order_id)
        if inventory_item_id:
            query = query.where(PartDemand.inventory_item_id == inventory_item_id)
        if expected_date_from:
            query = query.where(PartDemand.expected_date >= expected_date_from)
        if expected_date_to:
            query = query.where(PartDemand.expected_date <= expected_date_to)
        if query_text:
            like_pattern = f"%{query_text.strip()}%"
            query = query.join(PartDemand.service_order).join(PartDemand.inventory_item)
            query = query.where(
                or_(
                    ServiceOrder.order_number.ilike(like_pattern),
                    CatalogPart.code.ilike(like_pattern),
                    CatalogPart.name.ilike(like_pattern),
                    PartDemand.notes.ilike(like_pattern),
                )
            )

        return list(db.session.scalars(query.order_by(PartDemand.created_at.desc(), PartDemand.id.desc())).all())

    def list_grouped(
        self,
        *,
        company_id: int,
        branch_id: int | None,
        status: str | None,
        priority: str | None,
        branch_filter_id: int | None,
        expected_date_from: date | None,
        expected_date_to: date | None,
    ) -> list[PartDemandGroupedRow]:
        query = (
            select(
                PartDemand.inventory_item_id,
                CatalogPart.code,
                CatalogPart.name,
                func.coalesce(func.sum(PartDemand.missing_quantity), Decimal("0")).label("total_missing"),
                func.group_concat(ServiceOrder.order_number, ",").label("order_numbers"),
                func.group_concat(func.cast(PartDemand.id, db.String), ",").label("demand_ids"),
            )
            .join(CatalogPart, CatalogPart.id == PartDemand.inventory_item_id)
            .join(ServiceOrder, ServiceOrder.id == PartDemand.service_order_id)
            .where(PartDemand.company_id == company_id)
            .where(PartDemand.is_active.is_(True))
            .where(PartDemand.status.notin_([PartDemandStatusEnum.DELIVERED.value, PartDemandStatusEnum.CANCELLED.value]))
        )

        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        if branch_filter_id is not None:
            query = query.where(PartDemand.branch_id == branch_filter_id)
        if status:
            query = query.where(PartDemand.status == status)
        if priority:
            query = query.where(PartDemand.priority == priority)
        if expected_date_from:
            query = query.where(PartDemand.expected_date >= expected_date_from)
        if expected_date_to:
            query = query.where(PartDemand.expected_date <= expected_date_to)

        query = query.group_by(PartDemand.inventory_item_id, CatalogPart.code, CatalogPart.name).order_by(CatalogPart.name.asc())

        rows: list[PartDemandGroupedRow] = []
        for item in db.session.execute(query).all():
            order_numbers = [value for value in (item.order_numbers or "").split(",") if value]
            demand_ids = [int(value) for value in (item.demand_ids or "").split(",") if value]
            rows.append(
                PartDemandGroupedRow(
                    inventory_item_id=int(item.inventory_item_id),
                    part_code=str(item.code),
                    part_name=str(item.name),
                    total_missing=Decimal(str(item.total_missing or "0")),
                    order_numbers=sorted(set(order_numbers)),
                    demand_ids=demand_ids,
                )
            )
        return rows

    def get_by_id(self, *, demand_id: int, company_id: int, branch_id: int | None) -> PartDemand | None:
        query = (
            select(PartDemand)
            .options(
                selectinload(PartDemand.inventory_item),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.customer),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.device),
                selectinload(PartDemand.service_order).selectinload(ServiceOrder.actions),
            )
            .where(PartDemand.id == demand_id)
            .where(PartDemand.company_id == company_id)
            .where(PartDemand.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create(self, payload: dict[str, object]) -> PartDemand:
        row = PartDemand(**payload)
        db.session.add(row)
        db.session.flush()
        return row

    def update(self, row: PartDemand, payload: dict[str, object]) -> PartDemand:
        for key, value in payload.items():
            if hasattr(row, key) and key != "id":
                setattr(row, key, value)
        db.session.add(row)
        db.session.flush()
        return row

    def soft_delete(self, row: PartDemand, *, actor_id: int | None) -> None:
        row.is_active = False
        row.deleted_by = actor_id
        db.session.add(row)
        db.session.flush()

    def get_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def get_part(self, *, part_id: int, company_id: int, branch_id: int | None) -> CatalogPart | None:
        query = (
            select(CatalogPart)
            .where(CatalogPart.id == part_id)
            .where(CatalogPart.company_id == company_id)
            .where(CatalogPart.is_active.is_(True))
        )
        if branch_id is not None:
            query = query.where(or_(CatalogPart.branch_id == branch_id, CatalogPart.branch_id.is_(None)))
        return db.session.scalars(query).one_or_none()

    def list_part_choices(self, *, company_id: int) -> list[tuple[int, str]]:
        query = (
            select(CatalogPart)
            .where(CatalogPart.company_id == company_id)
            .where(CatalogPart.is_active.is_(True))
            .order_by(CatalogPart.name.asc(), CatalogPart.id.asc())
        )
        rows = db.session.scalars(query).all()
        return [(row.id, f"{row.code} | {row.name}") for row in rows]

    def list_branch_choices(self, *, company_id: int) -> list[tuple[int, str]]:
        query = (
            select(Branch)
            .where(Branch.company_id == company_id)
            .where(Branch.is_active.is_(True))
            .order_by(Branch.name.asc(), Branch.id.asc())
        )
        rows = db.session.scalars(query).all()
        return [(row.id, row.name) for row in rows]

    def find_open_for_order_part(self, *, order_id: int, part_id: int, company_id: int, branch_id: int | None) -> PartDemand | None:
        query = (
            select(PartDemand)
            .where(PartDemand.service_order_id == order_id)
            .where(PartDemand.inventory_item_id == part_id)
            .where(PartDemand.company_id == company_id)
            .where(PartDemand.is_active.is_(True))
            .where(
                and_(
                    PartDemand.status != PartDemandStatusEnum.DELIVERED.value,
                    PartDemand.status != PartDemandStatusEnum.CANCELLED.value,
                )
            )
            .order_by(PartDemand.id.desc())
        )
        if branch_id is not None:
            query = query.where(PartDemand.branch_id == branch_id)
        return db.session.scalars(query).first()
