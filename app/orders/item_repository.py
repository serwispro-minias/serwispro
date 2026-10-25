from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_service_item import CatalogServiceItem
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.utils.contextual_search import contextual_search


@dataclass(slots=True)
class ResolvedCatalogItem:
    item_type: str
    item_id: int
    code: str
    name: str
    barcode: str | None
    unit_price_net: Decimal
    vat_rate: Decimal
    current_stock: Decimal | None
    source_label: str


class ServiceOrderItemRepository:
    def get_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> ServiceOrder | None:
        query = select(ServiceOrder).where(ServiceOrder.id == order_id).where(ServiceOrder.is_active.is_(True))
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def list_items(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceOrderItem]:
        query = (
            select(ServiceOrderItem)
            .where(ServiceOrderItem.service_order_id == order_id)
            .where(ServiceOrderItem.is_active.is_(True))
            .order_by(ServiceOrderItem.created_at.asc(), ServiceOrderItem.id.asc())
        )
        if company_id is not None:
            query = query.where(ServiceOrderItem.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderItem.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def get_item(self, *, item_id: int, company_id: int | None, branch_id: int | None) -> ServiceOrderItem | None:
        query = select(ServiceOrderItem).where(ServiceOrderItem.id == item_id).where(ServiceOrderItem.is_active.is_(True))
        if company_id is not None:
            query = query.where(ServiceOrderItem.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderItem.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def find_existing(self, *, order_id: int, item_type: str, item_id: int, company_id: int | None, branch_id: int | None) -> ServiceOrderItem | None:
        query = (
            select(ServiceOrderItem)
            .where(ServiceOrderItem.service_order_id == order_id)
            .where(ServiceOrderItem.item_type == item_type)
            .where(ServiceOrderItem.item_id == item_id)
            .where(ServiceOrderItem.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(ServiceOrderItem.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrderItem.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def create_item(self, payload: dict[str, Any]) -> ServiceOrderItem:
        item = ServiceOrderItem(**payload)
        db.session.add(item)
        db.session.flush()
        return item

    def update_item(self, item: ServiceOrderItem, payload: dict[str, Any]) -> ServiceOrderItem:
        for key, value in payload.items():
            if key != "id" and hasattr(item, key):
                setattr(item, key, value)
        db.session.add(item)
        db.session.flush()
        return item

    def list_stock_operations_for_item(self, *, item_type: str, item_id: int, company_id: int | None, branch_id: int | None) -> list[CatalogStockMovement]:
        if item_type == "PART":
            query = (
                select(CatalogStockMovement)
                .where(CatalogStockMovement.part_id == item_id)
                .where(CatalogStockMovement.is_active.is_(True))
                .order_by(CatalogStockMovement.operation_at.desc(), CatalogStockMovement.id.desc())
            )
            if company_id is not None:
                query = query.where(CatalogStockMovement.company_id == company_id)
            if branch_id is not None:
                query = query.where(CatalogStockMovement.branch_id == branch_id)
            return list(db.session.scalars(query).all())

        if item_type == "MATERIAL":
            query = (
                select(CatalogStockMovement)
                .where(CatalogStockMovement.material_id == item_id)
                .where(CatalogStockMovement.is_active.is_(True))
                .options(selectinload(CatalogStockMovement.user))
                .order_by(CatalogStockMovement.operation_at.desc(), CatalogStockMovement.id.desc())
            )
            if company_id is not None:
                query = query.where(CatalogStockMovement.company_id == company_id)
            if branch_id is not None:
                query = query.where(CatalogStockMovement.branch_id == branch_id)
            return list(db.session.scalars(query).all())

        return []

    def search_catalog_items(self, *, query_text: str | None, company_id: int | None, branch_id: int | None = None) -> list[ResolvedCatalogItem]:
        text = (query_text or "").strip()
        if not text:
            return []

        results: list[ResolvedCatalogItem] = []
        part_search = contextual_search(CatalogPart.code, CatalogPart.name, CatalogPart.barcode, query=text)

        part_query = (
            select(CatalogPart)
            .where(CatalogPart.is_active.is_(True))
            .where(part_search)
            .order_by(CatalogPart.name.asc(), CatalogPart.id.asc())
            .limit(20)
        )
        material_query = (
            select(CatalogMaterial)
            .where(CatalogMaterial.is_active.is_(True))
            .where(contextual_search(CatalogMaterial.code, CatalogMaterial.name, CatalogMaterial.location, query=text))
            .order_by(CatalogMaterial.name.asc(), CatalogMaterial.id.asc())
            .limit(20)
        )
        service_query = (
            select(CatalogServiceItem)
            .where(CatalogServiceItem.is_active.is_(True))
            .where(CatalogServiceItem.is_sellable.is_(True))
            .where(contextual_search(CatalogServiceItem.code, CatalogServiceItem.name, query=text))
            .order_by(CatalogServiceItem.name.asc(), CatalogServiceItem.id.asc())
            .limit(20)
        )

        if company_id is not None:
            part_query = part_query.where(CatalogPart.company_id == company_id)
            material_query = material_query.where(CatalogMaterial.company_id == company_id)
            service_query = service_query.where(CatalogServiceItem.company_id == company_id)
        if branch_id is not None:
            part_query = part_query.where(or_(CatalogPart.branch_id == branch_id, CatalogPart.branch_id.is_(None)))
            material_query = material_query.where(or_(CatalogMaterial.branch_id == branch_id, CatalogMaterial.branch_id.is_(None)))
            service_query = service_query.where(or_(CatalogServiceItem.branch_id == branch_id, CatalogServiceItem.branch_id.is_(None)))

        for part in db.session.scalars(part_query).all():
            results.append(
                ResolvedCatalogItem(
                    item_type="PART",
                    item_id=part.id,
                    code=part.code,
                    name=part.name,
                    barcode=part.barcode,
                    unit_price_net=Decimal(part.sale_price_net),
                    vat_rate=Decimal(part.vat.rate if part.vat else 0),
                    current_stock=Decimal(part.current_stock),
                    source_label="inventory",
                )
            )

        for material in db.session.scalars(material_query).all():
            results.append(
                ResolvedCatalogItem(
                    item_type="MATERIAL",
                    item_id=material.id,
                    code=material.code,
                    name=material.name,
                    barcode=None,
                    unit_price_net=Decimal(material.purchase_price_net),
                    vat_rate=Decimal(material.vat_rate),
                    current_stock=Decimal(material.current_stock),
                    source_label="catalog",
                )
            )

        for service_item in db.session.scalars(service_query).all():
            results.append(
                ResolvedCatalogItem(
                    item_type="SERVICE",
                    item_id=service_item.id,
                    code=service_item.code,
                    name=service_item.name,
                    barcode=None,
                    unit_price_net=Decimal(service_item.default_price_net),
                    vat_rate=Decimal(service_item.vat_rate),
                    current_stock=None,
                    source_label="catalog",
                )
            )

        return results

    def resolve_catalog_item(self, *, item_type: str, item_id: int, company_id: int | None) -> ResolvedCatalogItem | None:
        if item_type == "PART":
            query = select(CatalogPart).where(CatalogPart.id == item_id).where(CatalogPart.is_active.is_(True))
            if company_id is not None:
                query = query.where(CatalogPart.company_id == company_id)
            part = db.session.scalars(query).one_or_none()
            if part is None:
                return None
            return ResolvedCatalogItem(
                item_type="PART",
                item_id=part.id,
                code=part.code,
                name=part.name,
                barcode=part.barcode,
                unit_price_net=Decimal(part.sale_price_net),
                vat_rate=Decimal(part.vat.rate if part.vat else 0),
                current_stock=Decimal(part.current_stock),
                source_label="inventory",
            )

        if item_type == "MATERIAL":
            query = select(CatalogMaterial).where(CatalogMaterial.id == item_id).where(CatalogMaterial.is_active.is_(True))
            if company_id is not None:
                query = query.where(CatalogMaterial.company_id == company_id)
            material = db.session.scalars(query).one_or_none()
            if material is None:
                return None
            return ResolvedCatalogItem(
                item_type="MATERIAL",
                item_id=material.id,
                code=material.code,
                name=material.name,
                barcode=None,
                unit_price_net=Decimal(material.purchase_price_net),
                vat_rate=Decimal(material.vat_rate),
                current_stock=Decimal(material.current_stock),
                source_label="catalog",
            )

        if item_type == "SERVICE":
            query = select(CatalogServiceItem).where(CatalogServiceItem.id == item_id).where(CatalogServiceItem.is_active.is_(True))
            if company_id is not None:
                query = query.where(CatalogServiceItem.company_id == company_id)
            service_item = db.session.scalars(query).one_or_none()
            if service_item is None:
                return None
            return ResolvedCatalogItem(
                item_type="SERVICE",
                item_id=service_item.id,
                code=service_item.code,
                name=service_item.name,
                barcode=None,
                unit_price_net=Decimal(service_item.default_price_net),
                vat_rate=Decimal(service_item.vat_rate),
                current_stock=None,
                source_label="catalog",
            )

        return None

    def save(self, entity: Any) -> Any:
        db.session.add(entity)
        db.session.flush()
        return entity
