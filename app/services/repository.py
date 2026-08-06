from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_service_item import CatalogServiceItem
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_material_usage import ServiceOrderMaterialUsage
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.service_order_service_line import ServiceOrderServiceLine


class EstimateRepository:
    def get_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> ServiceOrder | None:
        query = (
            select(ServiceOrder)
            .options(selectinload(ServiceOrder.customer), selectinload(ServiceOrder.device))
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def list_orders(self, *, company_id: int | None, branch_id: int | None) -> list[ServiceOrder]:
        query = select(ServiceOrder).where(ServiceOrder.is_active.is_(True)).order_by(ServiceOrder.id.desc())
        if company_id is not None:
            query = query.where(ServiceOrder.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceOrder.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_estimates(self, *, company_id: int | None, branch_id: int | None) -> list[ServiceEstimate]:
        query = select(ServiceEstimate).options(selectinload(ServiceEstimate.service_order)).order_by(ServiceEstimate.created_at.desc(), ServiceEstimate.id.desc())
        if company_id is not None:
            query = query.where(ServiceEstimate.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceEstimate.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def list_estimates_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> list[ServiceEstimate]:
        query = (
            select(ServiceEstimate)
            .options(selectinload(ServiceEstimate.items), selectinload(ServiceEstimate.service_order))
            .where(ServiceEstimate.service_order_id == order_id)
            .where(ServiceEstimate.is_active.is_(True))
            .order_by(ServiceEstimate.version_number.desc(), ServiceEstimate.id.desc())
        )
        if company_id is not None:
            query = query.where(ServiceEstimate.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceEstimate.branch_id == branch_id)
        return list(db.session.scalars(query).all())

    def get_estimate(self, *, estimate_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimate | None:
        query = (
            select(ServiceEstimate)
            .options(
                selectinload(ServiceEstimate.items),
                selectinload(ServiceEstimate.service_order).selectinload(ServiceOrder.customer),
                selectinload(ServiceEstimate.service_order).selectinload(ServiceOrder.device),
                selectinload(ServiceEstimate.parent_estimate),
            )
            .where(ServiceEstimate.id == estimate_id)
            .where(ServiceEstimate.is_active.is_(True))
        )
        if company_id is not None:
            query = query.where(ServiceEstimate.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceEstimate.branch_id == branch_id)
        return db.session.scalars(query).one_or_none()

    def get_latest_for_order(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> ServiceEstimate | None:
        estimates = self.list_estimates_for_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        return estimates[0] if estimates else None

    def get_next_version_number(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> int:
        query = select(func.coalesce(func.max(ServiceEstimate.version_number), 0)).where(ServiceEstimate.service_order_id == order_id)
        query = query.where(ServiceEstimate.is_active.is_(True))
        if company_id is not None:
            query = query.where(ServiceEstimate.company_id == company_id)
        if branch_id is not None:
            query = query.where(ServiceEstimate.branch_id == branch_id)
        current = db.session.scalar(query) or 0
        return int(current) + 1

    def create_estimate(self, payload: dict[str, Any]) -> ServiceEstimate:
        estimate = ServiceEstimate(**payload)
        db.session.add(estimate)
        db.session.flush()
        return estimate

    def create_item(self, payload: dict[str, Any]) -> ServiceEstimateItem:
        item = ServiceEstimateItem(**payload)
        db.session.add(item)
        db.session.flush()
        return item

    def delete_item(self, item: ServiceEstimateItem) -> None:
        db.session.delete(item)
        db.session.flush()

    def save(self, obj: Any) -> Any:
        db.session.add(obj)
        db.session.flush()
        return obj

    def get_order_sources(self, *, order_id: int, company_id: int | None, branch_id: int | None) -> dict[str, list[Any]]:
        part_query = (
            select(ServiceOrderPartReservation)
            .options(selectinload(ServiceOrderPartReservation.part))
            .where(ServiceOrderPartReservation.service_order_id == order_id)
            .where(ServiceOrderPartReservation.is_active.is_(True))
            .order_by(ServiceOrderPartReservation.id.asc())
        )
        material_query = (
            select(ServiceOrderMaterialUsage)
            .options(selectinload(ServiceOrderMaterialUsage.material))
            .where(ServiceOrderMaterialUsage.service_order_id == order_id)
            .where(ServiceOrderMaterialUsage.is_active.is_(True))
            .order_by(ServiceOrderMaterialUsage.id.asc())
        )
        service_query = (
            select(ServiceOrderServiceLine)
            .options(selectinload(ServiceOrderServiceLine.service_item))
            .where(ServiceOrderServiceLine.service_order_id == order_id)
            .where(ServiceOrderServiceLine.is_active.is_(True))
            .order_by(ServiceOrderServiceLine.id.asc())
        )
        if company_id is not None:
            part_query = part_query.where(ServiceOrderPartReservation.company_id == company_id)
            material_query = material_query.where(ServiceOrderMaterialUsage.company_id == company_id)
            service_query = service_query.where(ServiceOrderServiceLine.company_id == company_id)
        if branch_id is not None:
            part_query = part_query.where(ServiceOrderPartReservation.branch_id == branch_id)
            material_query = material_query.where(ServiceOrderMaterialUsage.branch_id == branch_id)
            service_query = service_query.where(ServiceOrderServiceLine.branch_id == branch_id)

        return {
            "parts": list(db.session.scalars(part_query).all()),
            "materials": list(db.session.scalars(material_query).all()),
            "services": list(db.session.scalars(service_query).all()),
        }

    def get_catalog_part(self, *, part_id: int, company_id: int | None) -> CatalogPart | None:
        query = select(CatalogPart).where(CatalogPart.id == part_id).where(CatalogPart.is_active.is_(True))
        if company_id is not None:
            query = query.where(CatalogPart.company_id == company_id)
        return db.session.scalars(query).one_or_none()

    def get_catalog_material(self, *, material_id: int, company_id: int | None) -> CatalogMaterial | None:
        query = select(CatalogMaterial).where(CatalogMaterial.id == material_id).where(CatalogMaterial.is_active.is_(True))
        if company_id is not None:
            query = query.where(CatalogMaterial.company_id == company_id)
        return db.session.scalars(query).one_or_none()

    def get_catalog_service(self, *, service_id: int, company_id: int | None) -> CatalogServiceItem | None:
        query = select(CatalogServiceItem).where(CatalogServiceItem.id == service_id).where(CatalogServiceItem.is_active.is_(True))
        if company_id is not None:
            query = query.where(CatalogServiceItem.company_id == company_id)
        return db.session.scalars(query).one_or_none()