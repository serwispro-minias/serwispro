from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.service_order import ServiceOrder
from app.models.service_order_timeline import (
    SERVICE_ORDER_TIMELINE_TYPE_CHOICES,
    SERVICE_ORDER_TIMELINE_TYPE_LABELS,
    ServiceOrderTimelineAttachment,
    ServiceOrderTimelineEntry,
)

from .timeline_exceptions import OrderTimelineNotFoundError, OrderTimelineValidationError
from .timeline_repository import ServiceOrderTimelineRepository


ALLOWED_TIMELINE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


class ServiceOrderTimelineService:
    """Business layer for service order timeline operations."""

    def __init__(self, repository: ServiceOrderTimelineRepository | None = None) -> None:
        self.repository = repository or ServiceOrderTimelineRepository()

    def get_type_choices(self) -> list[tuple[str, str]]:
        return list(SERVICE_ORDER_TIMELINE_TYPE_CHOICES)

    def get_type_labels(self) -> dict[str, str]:
        return dict(SERVICE_ORDER_TIMELINE_TYPE_LABELS)

    def list_entries(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> list[ServiceOrderTimelineEntry]:
        service_order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        return self.repository.list_entries(
            order_id=service_order.id,
            company_id=company_id,
            branch_id=branch_id,
        )

    def create_entry(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        user_id: int | None,
        entry_type: str,
        description: str,
        parts_cost_raw: str | None,
        labor_minutes_raw: str | None,
        attachments: list[FileStorage],
        upload_root: Path,
    ) -> ServiceOrderTimelineEntry:
        service_order = self._get_scoped_order(order_id=order_id, company_id=company_id, branch_id=branch_id)

        normalized_type = (entry_type or "").strip().upper()
        if normalized_type not in {value for value, _ in SERVICE_ORDER_TIMELINE_TYPE_CHOICES}:
            raise OrderTimelineValidationError("Wybierz poprawny typ wpisu.")

        normalized_description = (description or "").strip()
        if not normalized_description:
            raise OrderTimelineValidationError("Opis wykonanych czynności jest wymagany.")

        parts_cost = self._parse_parts_cost(parts_cost_raw)
        labor_minutes = self._parse_labor_minutes(labor_minutes_raw)
        prepared_files = self._prepare_files(attachments)

        payload: dict[str, object] = {
            "service_order_id": service_order.id,
            "author_user_id": user_id,
            "entry_type": normalized_type,
            "description": normalized_description,
            "parts_cost": parts_cost,
            "labor_minutes": labor_minutes,
            "company_id": company_id,
            "branch_id": service_order.branch_id,
            "created_by": user_id,
            "updated_by": user_id,
        }

        entry = self.repository.create_entry(payload)

        if prepared_files:
            storage_dir = upload_root / "service_order_timeline" / str(entry.id)
            storage_dir.mkdir(parents=True, exist_ok=True)

            for source_file, original_filename, extension in prepared_files:
                stored_filename = f"{uuid4().hex}{extension}"
                full_path = storage_dir / stored_filename
                source_file.save(full_path)
                file_size = None
                try:
                    file_size = full_path.stat().st_size
                except OSError:
                    file_size = None

                relative_path = str(Path("service_order_timeline") / str(entry.id) / stored_filename)
                self.repository.create_attachment(
                    {
                        "entry_id": entry.id,
                        "original_filename": original_filename,
                        "stored_filename": stored_filename,
                        "relative_path": relative_path,
                        "content_type": source_file.content_type,
                        "file_size": file_size,
                        "company_id": company_id,
                        "branch_id": service_order.branch_id,
                        "created_by": user_id,
                        "updated_by": user_id,
                    }
                )

        db.session.commit()
        return self.repository.list_entries(order_id=entry.service_order_id, company_id=company_id, branch_id=branch_id)[-1]

    def get_attachment(
        self,
        *,
        order_id: int,
        attachment_id: int,
        company_id: int,
        branch_id: int | None,
    ) -> ServiceOrderTimelineAttachment:
        attachment = self.repository.get_attachment(
            attachment_id=attachment_id,
            company_id=company_id,
            branch_id=branch_id,
        )
        if attachment is None or attachment.entry.service_order_id != order_id:
            raise OrderTimelineNotFoundError("Załącznik nie istnieje.")

        self._ensure_branch_scope(order_branch_id=attachment.branch_id, branch_id=branch_id)
        return attachment

    def resolve_attachment_path(self, upload_root: Path, attachment: ServiceOrderTimelineAttachment) -> Path:
        full_path = upload_root / attachment.relative_path
        if not full_path.exists() or not full_path.is_file():
            raise OrderTimelineNotFoundError("Plik załącznika nie został odnaleziony na dysku.")
        return full_path

    def _get_scoped_order(self, *, order_id: int, company_id: int, branch_id: int | None) -> ServiceOrder:
        service_order = db.session.scalar(
            select(ServiceOrder)
            .where(ServiceOrder.id == order_id)
            .where(ServiceOrder.company_id == company_id)
            .where(ServiceOrder.is_active.is_(True))
        )
        if service_order is None:
            raise OrderTimelineNotFoundError("Zlecenie nie istnieje.")

        self._ensure_branch_scope(order_branch_id=service_order.branch_id, branch_id=branch_id)
        return service_order

    def _ensure_branch_scope(self, *, order_branch_id: int | None, branch_id: int | None) -> None:
        if branch_id is None and order_branch_id is None:
            return
        if branch_id is None and order_branch_id is not None:
            raise OrderTimelineValidationError("Brak dostępu do wskazanego oddziału.")
        if branch_id is not None and order_branch_id != branch_id:
            raise OrderTimelineValidationError("Brak dostępu do wskazanego oddziału.")

    def _parse_parts_cost(self, value: str | None) -> Decimal | None:
        if value is None:
            return None
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            parsed = Decimal(normalized)
        except InvalidOperation as exc:
            raise OrderTimelineValidationError("Podaj poprawny koszt części.") from exc
        if parsed < 0:
            raise OrderTimelineValidationError("Koszt części nie może być ujemny.")
        return parsed

    def _parse_labor_minutes(self, value: str | None) -> int | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise OrderTimelineValidationError("Czas pracy musi być liczbą całkowitą.") from exc
        if parsed < 0:
            raise OrderTimelineValidationError("Czas pracy nie może być ujemny.")
        return parsed

    def _prepare_files(self, files: list[FileStorage]) -> list[tuple[FileStorage, str, str]]:
        prepared: list[tuple[FileStorage, str, str]] = []

        for item in files:
            if item is None:
                continue
            original_filename = (item.filename or "").strip()
            if not original_filename:
                continue

            safe_name = secure_filename(original_filename)
            if not safe_name:
                raise OrderTimelineValidationError("Nieprawidłowa nazwa pliku załącznika.")

            _, extension = os.path.splitext(safe_name)
            lowered_extension = extension.lower()
            if lowered_extension not in ALLOWED_TIMELINE_EXTENSIONS:
                raise OrderTimelineValidationError("Dozwolone formaty załączników: JPG, PNG, PDF.")

            prepared.append((item, original_filename, lowered_extension))

        return prepared
