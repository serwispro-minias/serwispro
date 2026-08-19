from __future__ import annotations

from decimal import Decimal
from typing import Any, Generic, TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_category import CatalogCategory
from app.models.catalog_manufacturer import CatalogManufacturer
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_service_item import CatalogServiceItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.service_order import ServiceOrder
from app.models.service_order_material_usage import ServiceOrderMaterialUsage
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.service_order_service_line import ServiceOrderServiceLine

TModel = TypeVar("TModel")


class _BaseCatalogRepository(Generic[TModel]):
    model: type[TModel]
    code_field: str = "code"
    name_field: str = "name"

    def get(self, entity_id: int, *, company_id: int | None) -> TModel | None:
        query = select(self.model).where(getattr(self.model, "id") == entity_id).where(getattr(self.model, "is_active").is_(True))
        if company_id is not None:
            query = query.where(getattr(self.model, "company_id") == company_id)
        return db.session.scalar(query)

    def get_by_code(self, code: str, *, company_id: int | None) -> TModel | None:
        query = (
            select(self.model)
            .where(getattr(self.model, self.code_field) == code)
            .where(getattr(self.model, "is_active").is_(True))
        )
        if company_id is not None:
            query = query.where(getattr(self.model, "company_id") == company_id)
        return db.session.scalar(query)

    def list_paginated(self, *, page: int, per_page: int, company_id: int | None, query_text: str | None) -> dict[str, Any]:
        filters = [getattr(self.model, "is_active").is_(True)]
        if company_id is not None:
            filters.append(getattr(self.model, "company_id") == company_id)
        if query_text:
            term = f"%{query_text}%"
            fields = [
                getattr(self.model, self.code_field).ilike(term),
                getattr(self.model, self.name_field).ilike(term),
            ]
            filters.append(or_(*fields))

        total = int(db.session.scalar(select(func.count()).select_from(self.model).where(*filters)) or 0)
        items = list(
            db.session.scalars(
                select(self.model)
                .where(*filters)
                .order_by(getattr(self.model, self.name_field).asc(), getattr(self.model, "id").asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).all()
        )
        pages = (total + per_page - 1) // per_page if total else 0
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

    def create(self, payload: dict[str, Any]) -> TModel:
        entity = self.model(**payload)
        db.session.add(entity)
        db.session.flush()
        return entity

    def update(self, entity: TModel, payload: dict[str, Any]) -> TModel:
        for key, value in payload.items():
            if hasattr(entity, key) and key != "id":
                setattr(entity, key, value)
        db.session.add(entity)
        db.session.flush()
        return entity

    def soft_delete(self, entity: TModel) -> None:
        setattr(entity, "is_active", False)
        db.session.add(entity)
        db.session.flush()

    def list_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(self.model)
            .where(getattr(self.model, "is_active").is_(True))
            .order_by(getattr(self.model, self.name_field).asc(), getattr(self.model, "id").asc())
        )
        if company_id is not None:
            query = query.where(getattr(self.model, "company_id") == company_id)
        items = list(db.session.scalars(query).all())
        return [(item.id, f"{getattr(item, self.code_field)} | {getattr(item, self.name_field)}") for item in items]


class CategoriesRepository(_BaseCatalogRepository[CatalogCategory]):
    model = CatalogCategory


class SuppliersRepository(_BaseCatalogRepository[CatalogSupplier]):
    model = CatalogSupplier


class ManufacturersRepository(_BaseCatalogRepository[CatalogManufacturer]):
    model = CatalogManufacturer


class PartsRepository(_BaseCatalogRepository[CatalogPart]):
    model = CatalogPart

    def list_paginated(self, *, page: int, per_page: int, company_id: int | None, query_text: str | None, supplier_id: int | None = None, sort_by: str = "name", sort_dir: str = "asc") -> dict[str, Any]:
        filters = [CatalogPart.is_active.is_(True)]
        if company_id is not None:
            filters.append(CatalogPart.company_id == company_id)
        if supplier_id is not None:
            filters.append(CatalogPart.preferred_supplier_id == supplier_id)
        if query_text:
            term = f"%{query_text}%"
            filters.append(or_(CatalogPart.code.ilike(term), CatalogPart.name.ilike(term)))
        sort_columns = {
            "code": CatalogPart.code,
            "name": CatalogPart.name,
            "current_stock": CatalogPart.current_stock,
            "minimum_stock": CatalogPart.minimum_stock,
            "sale_price_net": CatalogPart.sale_price_net,
        }
        sort_column = sort_columns.get(sort_by, CatalogPart.name)
        if sort_dir.lower() == "desc":
            sort_column = sort_column.desc()
        else:
            sort_column = sort_column.asc()
        total = int(db.session.scalar(select(func.count()).select_from(CatalogPart).where(*filters)) or 0)
        items = list(db.session.scalars(select(CatalogPart).options(selectinload(CatalogPart.preferred_supplier)).where(*filters).order_by(sort_column, CatalogPart.id.asc()).offset((page - 1) * per_page).limit(per_page)).all())
        pages = (total + per_page - 1) // per_page if total else 0
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

    def get(self, entity_id: int, *, company_id: int | None) -> CatalogPart | None:
        query = (
            select(CatalogPart)
            .where(CatalogPart.id == entity_id)
            .where(CatalogPart.is_active.is_(True))
            .options(
                selectinload(CatalogPart.category),
                selectinload(CatalogPart.supplier),
                selectinload(CatalogPart.manufacturer),
                selectinload(CatalogPart.movements).selectinload(CatalogStockMovement.user),
                selectinload(CatalogPart.reservations),
            )
        )
        if company_id is not None:
            query = query.where(CatalogPart.company_id == company_id)
        return db.session.scalar(query)

    def list_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(CatalogPart)
            .where(CatalogPart.is_active.is_(True))
            .where(CatalogPart.is_reservable.is_(True))
            .order_by(CatalogPart.name.asc(), CatalogPart.id.asc())
        )
        if company_id is not None:
            query = query.where(CatalogPart.company_id == company_id)
        items = db.session.scalars(query).all()
        return [(item.id, f"{item.code} | {item.name}") for item in items]


class MaterialsRepository(_BaseCatalogRepository[CatalogMaterial]):
    model = CatalogMaterial

    def get(self, entity_id: int, *, company_id: int | None) -> CatalogMaterial | None:
        query = (
            select(CatalogMaterial)
            .where(CatalogMaterial.id == entity_id)
            .where(CatalogMaterial.is_active.is_(True))
            .options(
                selectinload(CatalogMaterial.category),
                selectinload(CatalogMaterial.supplier),
                selectinload(CatalogMaterial.manufacturer),
                selectinload(CatalogMaterial.movements).selectinload(CatalogStockMovement.user),
                selectinload(CatalogMaterial.usages),
            )
        )
        if company_id is not None:
            query = query.where(CatalogMaterial.company_id == company_id)
        return db.session.scalar(query)

    def list_auto_issue(self, *, company_id: int | None) -> list[CatalogMaterial]:
        query = (
            select(CatalogMaterial)
            .where(CatalogMaterial.is_active.is_(True))
            .where(CatalogMaterial.auto_issue_on_order.is_(True))
            .order_by(CatalogMaterial.name.asc(), CatalogMaterial.id.asc())
        )
        if company_id is not None:
            query = query.where(CatalogMaterial.company_id == company_id)
        return list(db.session.scalars(query).all())

    def list_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(CatalogMaterial)
            .where(CatalogMaterial.is_active.is_(True))
            .order_by(CatalogMaterial.name.asc(), CatalogMaterial.id.asc())
        )
        if company_id is not None:
            query = query.where(CatalogMaterial.company_id == company_id)
        items = db.session.scalars(query).all()
        return [(item.id, f"{item.code} | {item.name}") for item in items]


class ServicesRepository(_BaseCatalogRepository[CatalogServiceItem]):
    model = CatalogServiceItem

    def list_choices(self, *, company_id: int | None) -> list[tuple[int, str]]:
        query = (
            select(CatalogServiceItem)
            .where(CatalogServiceItem.is_active.is_(True))
            .where(CatalogServiceItem.is_sellable.is_(True))
            .order_by(CatalogServiceItem.name.asc(), CatalogServiceItem.id.asc())
        )
        if company_id is not None:
            query = query.where(CatalogServiceItem.company_id == company_id)
        items = db.session.scalars(query).all()
        return [(item.id, f"{item.code} | {item.name}") for item in items]


class StockRepository:
    def create_movement(self, payload: dict[str, Any]) -> CatalogStockMovement:
        movement = CatalogStockMovement(**payload)
        db.session.add(movement)
        db.session.flush()
        return movement

    def reserve_part(self, payload: dict[str, Any]) -> ServiceOrderPartReservation:
        reservation = ServiceOrderPartReservation(**payload)
        db.session.add(reservation)
        db.session.flush()
        return reservation

    def create_material_usage(self, payload: dict[str, Any]) -> ServiceOrderMaterialUsage:
        usage = ServiceOrderMaterialUsage(**payload)
        db.session.add(usage)
        db.session.flush()
        return usage

    def create_service_line(self, payload: dict[str, Any]) -> ServiceOrderServiceLine:
        line = ServiceOrderServiceLine(**payload)
        db.session.add(line)
        db.session.flush()
        return line

    def get_service_order(self, order_id: int, *, company_id: int | None, branch_id: int | None) -> ServiceOrder | None:
        query = select(ServiceOrder).where(ServiceOrder.id == order_id).where(ServiceOrder.is_active.is_(True))
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalar(query)

    def list_part_reservations(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceOrderPartReservation]:
        query = (
            select(ServiceOrderPartReservation)
            .options(selectinload(ServiceOrderPartReservation.part))
            .where(ServiceOrderPartReservation.service_order_id == order_id)
            .where(ServiceOrderPartReservation.is_active.is_(True))
            .order_by(ServiceOrderPartReservation.created_at.asc(), ServiceOrderPartReservation.id.asc())
        )
        if company_id is not None:
            query = query.where(ServiceOrderPartReservation.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderPartReservation.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_material_usages(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceOrderMaterialUsage]:
        query = (
            select(ServiceOrderMaterialUsage)
            .options(selectinload(ServiceOrderMaterialUsage.material))
            .where(ServiceOrderMaterialUsage.service_order_id == order_id)
            .where(ServiceOrderMaterialUsage.is_active.is_(True))
            .order_by(ServiceOrderMaterialUsage.created_at.asc(), ServiceOrderMaterialUsage.id.asc())
        )
        if company_id is not None:
            query = query.where(ServiceOrderMaterialUsage.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderMaterialUsage.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_service_lines(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceOrderServiceLine]:
        query = (
            select(ServiceOrderServiceLine)
            .options(selectinload(ServiceOrderServiceLine.service_item))
            .where(ServiceOrderServiceLine.service_order_id == order_id)
            .where(ServiceOrderServiceLine.is_active.is_(True))
            .order_by(ServiceOrderServiceLine.created_at.asc(), ServiceOrderServiceLine.id.asc())
        )
        if company_id is not None:
            query = query.where(ServiceOrderServiceLine.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderServiceLine.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def update_part_stock(self, part: CatalogPart, *, quantity: Decimal, movement_type: str) -> tuple[Decimal, Decimal]:
        stock_before = Decimal(part.current_stock)
        if movement_type in {"ISSUE", "RESERVATION", "SALE", "AUTO_ISSUE"}:
            stock_after = stock_before - quantity
        elif movement_type == "RELEASE":
            stock_after = stock_before + quantity
        elif movement_type == "ADJUSTMENT":
            stock_after = quantity
        else:
            stock_after = stock_before + quantity

        part.current_stock = stock_after
        db.session.add(part)
        db.session.flush()
        return stock_before, stock_after

    def update_material_stock(self, material: CatalogMaterial, *, quantity: Decimal, movement_type: str) -> tuple[Decimal, Decimal]:
        stock_before = Decimal(material.current_stock)
        if movement_type in {"ISSUE", "AUTO_ISSUE"}:
            stock_after = stock_before - quantity
        elif movement_type == "ADJUSTMENT":
            stock_after = quantity
        else:
            stock_after = stock_before + quantity

        material.current_stock = stock_after
        db.session.add(material)
        db.session.flush()
        return stock_before, stock_after
