from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.inventory_item import InventoryItem
from app.models.inventory_stock_operation import InventoryStockOperation
from app.models.service_order import ServiceOrder
from app.models.service_order_part_usage import ServiceOrderPartUsage


class InventoryRepository:
    def get_part(self, part_id: int, *, company_id: int | None) -> InventoryItem | None:
        query = (
            select(InventoryItem)
            .where(InventoryItem.id == part_id)
            .where(InventoryItem.is_active.is_(True))
            .options(selectinload(InventoryItem.stock_operations), selectinload(InventoryItem.vat))
        )
        if company_id is not None:
            query = query.where(InventoryItem.company_id == company_id)
        return db.session.scalars(query).one_or_none()

    def list_parts(
        self,
        *,
        page: int,
        per_page: int,
        company_id: int | None,
        query_text: str | None,
    ) -> dict[str, Any]:
        filters: list[Any] = [InventoryItem.is_active.is_(True)]
        if company_id is not None:
            filters.append(InventoryItem.company_id == company_id)
        if query_text:
            term = f"%{query_text}%"
            filters.append(
                or_(
                    InventoryItem.code.ilike(term),
                    InventoryItem.name.ilike(term),
                    InventoryItem.barcode.ilike(term),
                )
            )

        total = int(db.session.scalar(select(func.count()).select_from(InventoryItem).where(*filters)) or 0)
        items = list(
            db.session.scalars(
                select(InventoryItem)
                .where(*filters)
                .order_by(InventoryItem.name.asc(), InventoryItem.id.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).all()
        )
        pages = (total + per_page - 1) // per_page if total else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def create_part(self, payload: dict[str, Any]) -> InventoryItem:
        part = InventoryItem(**payload)
        db.session.add(part)
        db.session.flush()
        return part

    def update_part(self, part: InventoryItem, payload: dict[str, Any]) -> InventoryItem:
        for key, value in payload.items():
            if hasattr(part, key) and key != "id":
                setattr(part, key, value)
        db.session.add(part)
        db.session.flush()
        return part

    def get_by_code(self, code: str, *, company_id: int | None) -> InventoryItem | None:
        query = (
            select(InventoryItem)
            .where(InventoryItem.code == code)
            .where(InventoryItem.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(InventoryItem.company_id == company_id)
        return db.session.scalars(query).one_or_none()

    def create_stock_operation(self, payload: dict[str, Any]) -> InventoryStockOperation:
        operation = InventoryStockOperation(**payload)
        db.session.add(operation)
        db.session.flush()
        return operation

    def create_order_usage(self, payload: dict[str, Any]) -> ServiceOrderPartUsage:
        usage = ServiceOrderPartUsage(**payload)
        db.session.add(usage)
        db.session.flush()
        return usage

    def list_part_operations(self, part_id: int, *, company_id: int | None) -> list[InventoryStockOperation]:
        query = (
            select(InventoryStockOperation)
            .where(InventoryStockOperation.part_id == part_id)
            .where(InventoryStockOperation.is_active.is_(True))
            .order_by(InventoryStockOperation.operation_at.desc(), InventoryStockOperation.id.desc())
            .options(selectinload(InventoryStockOperation.user))
        )
        if company_id is not None:
            query = query.where(InventoryStockOperation.company_id == company_id)
        return list(db.session.scalars(query).all())

    def list_order_usages(self, order_id: int, *, company_id: int | None, branch_id: int | None) -> list[ServiceOrderPartUsage]:
        query = (
            select(ServiceOrderPartUsage)
            .where(ServiceOrderPartUsage.service_order_id == order_id)
            .where(ServiceOrderPartUsage.is_active.is_(True))
            .order_by(ServiceOrderPartUsage.created_at.asc(), ServiceOrderPartUsage.id.asc())
            .options(selectinload(ServiceOrderPartUsage.part))
        )
        if company_id is not None:
            query = query.where(ServiceOrderPartUsage.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderPartUsage.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_part_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(InventoryItem)
            .where(InventoryItem.is_active.is_(True))
            .order_by(InventoryItem.name.asc(), InventoryItem.id.asc())
        )
        if company_id is not None:
            query = query.where(InventoryItem.company_id == company_id)

        parts = db.session.scalars(query).all()
        return [(part.id, f"{part.code} | {part.name}") for part in parts]

    def get_service_order(self, order_id: int, *, company_id: int | None, branch_id: int | None) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def low_stock_count(self, *, company_id: int | None) -> int:
        query = select(func.count()).select_from(InventoryItem).where(InventoryItem.is_active.is_(True))
        query = query.where(InventoryItem.current_stock == 0)
        if company_id is not None:
            query = query.where(InventoryItem.company_id == company_id)
        return int(db.session.scalar(query) or 0)

    def low_stock_list(self, *, company_id: int | None) -> list[InventoryItem]:
        query = (
            select(InventoryItem)
            .where(InventoryItem.is_active.is_(True))
            .where(InventoryItem.current_stock == 0)
            .order_by(InventoryItem.name.asc())
        )
        if company_id is not None:
            query = query.where(InventoryItem.company_id == company_id)
        return list(db.session.scalars(query).all())

    def stock_summary(self, *, company_id: int | None) -> dict[str, Decimal]:
        filters: list[Any] = [InventoryItem.is_active.is_(True)]
        if company_id is not None:
            filters.append(InventoryItem.company_id == company_id)
        total_count = int(db.session.scalar(select(func.count()).select_from(InventoryItem).where(*filters)) or 0)
        low_count = int(
            db.session.scalar(
                select(func.count())
                .select_from(InventoryItem)
                .where(*filters)
                .where(InventoryItem.current_stock == 0)
            )
            or 0
        )
        total_net_value = db.session.scalar(
            select(func.coalesce(func.sum(InventoryItem.current_stock * InventoryItem.purchase_price_net), 0)).where(*filters)
        )
        return {
            "parts_count": Decimal(total_count),
            "low_stock_count": Decimal(low_count),
            "total_net_value": Decimal(total_net_value or 0),
        }
