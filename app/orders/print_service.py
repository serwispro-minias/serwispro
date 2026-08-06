from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.exc import OperationalError

from app.order_photos.service import ServiceOrderPhotoService
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_photo import ServiceOrderPhoto
from app.models.service_order_timeline import ServiceOrderTimelineEntry

from .pdf_generator import ProtocolRenderContext, ServiceOrderPdfGenerator
from .print_repository import ServiceOrderPrintRepository


@dataclass(slots=True)
class ProtocolDocument:
    filename: str
    content: bytes


class ServiceOrderPrintService:
    """Builds intake and release protocol PDF documents for service orders."""

    def __init__(
        self,
        repository: ServiceOrderPrintRepository | None = None,
        generator: ServiceOrderPdfGenerator | None = None,
        photo_service: ServiceOrderPhotoService | None = None,
    ) -> None:
        self.repository = repository or ServiceOrderPrintRepository()
        self.generator = generator or ServiceOrderPdfGenerator()
        self.photo_service = photo_service or ServiceOrderPhotoService()

    def build_intake_protocol(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        upload_root: Path,
        selected_photo_ids: list[int] | None = None,
        photo_render_mode: str = "original",
    ) -> ProtocolDocument | None:
        context = self._build_context(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            upload_root=upload_root,
            title="Protokół przyjęcia sprzętu do serwisu",
            selected_photo_ids=selected_photo_ids,
            default_photo_types={"RECEPTION", "DAMAGE"},
            photo_render_mode=photo_render_mode,
        )
        if context is None:
            return None

        content = self.generator.render_intake_protocol(context)
        return ProtocolDocument(filename=f"protokol_przyjecia_{context.order_number}.pdf", content=content)

    def build_release_protocol(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        upload_root: Path,
        selected_photo_ids: list[int] | None = None,
        photo_render_mode: str = "original",
    ) -> ProtocolDocument | None:
        context = self._build_context(
            order_id=order_id,
            company_id=company_id,
            branch_id=branch_id,
            upload_root=upload_root,
            title="Protokół wydania sprzętu z serwisu",
            selected_photo_ids=selected_photo_ids,
            default_photo_types={"FINAL", "HANDOVER", "REPAIR", "PART"},
            photo_render_mode=photo_render_mode,
        )
        if context is None:
            return None

        content = self.generator.render_release_protocol(context)
        return ProtocolDocument(filename=f"protokol_wydania_{context.order_number}.pdf", content=content)

    def _build_context(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        upload_root: Path,
        title: str,
        selected_photo_ids: list[int] | None,
        default_photo_types: set[str],
        photo_render_mode: str,
    ) -> ProtocolRenderContext | None:
        order = self.repository.get_service_order(order_id=order_id, company_id=company_id, branch_id=branch_id)
        if order is None:
            return None

        company = self.repository.get_company(company_id=company_id)
        if company is None:
            return None

        branch = self.repository.get_branch(branch_id=order.branch_id, company_id=company_id)
        settings_map = self.repository.get_settings_map(company_id=company_id, branch_id=order.branch_id)
        timeline_entries = self.repository.list_timeline_entries(
            order_id=order.id,
            company_id=company_id,
            branch_id=order.branch_id,
        )
        actions = self.repository.list_actions_for_order(order_id=order.id)

        company_name = self._get_setting(
            settings_map,
            ["company_name", "service_name", "serwis_name", "nazwa_firmy", "nazwa_serwisu"],
            default=company.name,
        )
        company_lines = [company_name]

        address_line = self._get_setting(
            settings_map,
            ["company_address", "service_address", "adres", "adres_serwisu"],
            default=(branch.address if branch and branch.address else ""),
        )
        if address_line:
            company_lines.append(address_line)

        nip_line = self._get_setting(
            settings_map,
            ["company_nip", "nip", "service_nip"],
            default=(company.nip or ""),
        )
        if nip_line:
            company_lines.append(f"NIP: {nip_line}")

        phone_line = self._get_setting(
            settings_map,
            ["company_phone", "service_phone", "telefon", "telefon_serwisu"],
            default=(branch.phone if branch and branch.phone else (company.phone or "")),
        )
        if phone_line:
            company_lines.append(f"Tel: {phone_line}")

        email_line = self._get_setting(
            settings_map,
            ["company_email", "service_email", "email", "e_mail"],
            default=(branch.email if branch and branch.email else (company.email or "")),
        )
        if email_line:
            company_lines.append(f"E-mail: {email_line}")

        website_line = self._get_setting(
            settings_map,
            ["company_website", "service_website", "www", "strona_www"],
            default="",
        )
        if website_line:
            company_lines.append(f"WWW: {website_line}")

        logo_setting = self._get_setting(
            settings_map,
            ["company_logo", "service_logo", "logo", "logo_path"],
            default=(company.logo or ""),
        )
        logo_path = self._resolve_logo_path(logo_setting, upload_root)

        customer_name = (
            order.customer.full_name
            or order.customer.short_name
            or f"{(order.customer.first_name or '').strip()} {(order.customer.last_name or '').strip()}".strip()
            or f"Klient #{order.customer.id}"
        )

        customer_lines = [
            f"Nazwa / Imię i nazwisko: {customer_name}",
            f"Email: {order.customer.email or '-'}",
            f"Telefon: {order.customer.phone or order.customer.phone2 or '-'}",
            f"Adres: {self._format_customer_address(order.customer.city, order.customer.street, order.customer.building_no, order.customer.apartment_no, order.customer.postal_code)}",
        ]

        device_rows = [
            ("Producent", order.device.manufacturer or "-"),
            ("Model", order.device.model or "-"),
            ("Numer seryjny", order.device.serial_number or "-"),
            ("Numer inwentarzowy", order.device.inventory_number or "-"),
        ]

        performed_actions = self._collect_timeline_by_types(timeline_entries, {"DIAGNOSIS", "REPAIR", "TESTS"})
        used_parts = self._collect_timeline_by_types(timeline_entries, {"PARTS_ORDER"})

        parts_cost_total = sum((entry.parts_cost or Decimal("0")) for entry in timeline_entries)
        service_cost = order.final_cost if order.final_cost is not None else (order.estimated_cost or Decimal("0"))
        total_to_pay = service_cost + parts_cost_total

        warranty_text = self._get_setting(
            settings_map,
            ["repair_warranty_info", "service_warranty_info", "warranty_info"],
            default="Gwarancja zgodnie z warunkami serwisu.",
        )

        intake_dt = datetime.combine(order.intake_date, datetime.min.time())
        issue_dt = order.finished_at or datetime.now(timezone.utc)
        protocol_photos = self._collect_protocol_photos(
            order_id=order.id,
            company_id=company_id,
            branch_id=order.branch_id,
            upload_root=upload_root,
            selected_photo_ids=selected_photo_ids,
            default_photo_types=default_photo_types,
            photo_render_mode=photo_render_mode,
        )

        return ProtocolRenderContext(
            title=title,
            order_number=order.order_number,
            generated_at=datetime.now(timezone.utc),
            company_name=company_name,
            company_lines=company_lines,
            logo_path=logo_path,
            intake_datetime_text=intake_dt.strftime("%Y-%m-%d %H:%M"),
            issue_datetime_text=issue_dt.strftime("%Y-%m-%d %H:%M"),
            customer_lines=customer_lines,
            device_rows=device_rows,
            issue_description=order.issue_description or "-",
            visual_state=order.repair_description or "-",
            accessories=order.customer_notes or "-",
            planned_finish_text=(order.planned_finish_date.strftime("%Y-%m-%d") if order.planned_finish_date else "-"),
            notes=order.technician_notes or "-",
            performed_actions=performed_actions,
            used_parts=used_parts,
            action_history=self._collect_action_history(actions),
            service_cost_text=f"{service_cost:.2f} PLN",
            parts_cost_text=f"{parts_cost_total:.2f} PLN",
            total_cost_text=f"{total_to_pay:.2f} PLN",
            warranty_text=warranty_text,
            protocol_photos=protocol_photos,
        )

    def _collect_protocol_photos(
        self,
        *,
        order_id: int,
        company_id: int,
        branch_id: int | None,
        upload_root: Path,
        selected_photo_ids: list[int] | None,
        default_photo_types: set[str],
        photo_render_mode: str,
    ) -> list[tuple[bytes | Path, str]]:
        try:
            rows = self.repository.list_order_photos(order_id=order_id, company_id=company_id, branch_id=branch_id)
        except OperationalError:
            return []

        if selected_photo_ids:
            allowed_ids = set(selected_photo_ids)
            rows = [row for row in rows if row.id in allowed_ids]
        else:
            rows = [row for row in rows if row.photo_type in default_photo_types]

        return [
            entry
            for entry in (
                self._to_photo_entry(
                    upload_root=upload_root,
                    row=row,
                    company_id=company_id,
                    branch_id=branch_id,
                    photo_render_mode=photo_render_mode,
                )
                for row in rows
            )
            if entry is not None
        ]

    def _to_photo_entry(
        self,
        *,
        upload_root: Path,
        row: ServiceOrderPhoto,
        company_id: int,
        branch_id: int | None,
        photo_render_mode: str,
    ) -> tuple[bytes | Path, str] | None:
        photos_dir = upload_root / "service_orders" / str(row.service_order_id) / "photos"
        candidate_paths = [
            photos_dir / "thumbnails" / f"{Path(row.file_name).stem}_thumb.webp",
            photos_dir / row.file_name,
        ]
        selected_path = next((path for path in candidate_paths if path.exists() and path.is_file()), None)
        if selected_path is None:
            return None

        source: bytes | Path = selected_path
        if photo_render_mode == "annotated":
            rendered = self.photo_service.render_annotated_photo_bytes(
                photo=row,
                upload_root=upload_root,
                company_id=company_id,
                branch_id=branch_id,
                customer_only=False,
            )
            if rendered:
                source = rendered

        caption = row.title or row.description or row.original_file_name
        if photo_render_mode == "annotated":
            caption = f"{caption} (z oznaczeniami)"
        return source, caption

    def _collect_timeline_by_types(self, entries: list[ServiceOrderTimelineEntry], accepted: set[str]) -> str:
        filtered: list[str] = []
        for entry in entries:
            if (entry.entry_type or "").upper() not in accepted:
                continue
            timestamp = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "-"
            filtered.append(f"{timestamp}: {entry.description}")

        if not filtered:
            return "-"

        return "\n".join(filtered)

    def _collect_action_history(self, actions: list[ServiceOrderAction]) -> str:
        if not actions:
            return "-"

        lines: list[str] = []
        for action in actions:
            date_text = action.action_date.strftime("%Y-%m-%d") if action.action_date else "-"
            technician_label = "-"
            if action.technician:
                name = f"{(action.technician.first_name or '').strip()} {(action.technician.last_name or '').strip()}".strip()
                technician_label = name or action.technician.login or f"Użytkownik #{action.technician.id}"
            cost_text = f"{action.cost:.2f} PLN" if action.cost is not None else "-"
            time_text = f"{action.work_time_minutes} min" if action.work_time_minutes is not None else "-"
            lines.append(
                f"{date_text} | {technician_label} | {action.action_type} | {action.description} | Czas: {time_text} | Koszt: {cost_text}"
            )
        return "\n".join(lines)

    def _resolve_logo_path(self, value: str, upload_root: Path) -> Path | None:
        raw = (value or "").strip()
        if not raw:
            return None

        candidate = Path(raw)
        if candidate.is_absolute() and candidate.exists() and candidate.is_file():
            return candidate

        candidate_upload = upload_root / raw
        if candidate_upload.exists() and candidate_upload.is_file():
            return candidate_upload

        candidate_project = Path.cwd() / raw
        if candidate_project.exists() and candidate_project.is_file():
            return candidate_project

        return None

    def _get_setting(self, settings_map: dict[str, str], keys: list[str], *, default: str) -> str:
        normalized_map = {key.lower(): value for key, value in settings_map.items()}
        for key in keys:
            value = normalized_map.get(key.lower())
            if value:
                return value
        return default

    def _format_customer_address(
        self,
        city: str | None,
        street: str | None,
        building_no: str | None,
        apartment_no: str | None,
        postal_code: str | None,
    ) -> str:
        street_line = " ".join(part for part in [street, building_no] if part)
        if apartment_no:
            street_line = f"{street_line}/{apartment_no}" if street_line else apartment_no

        city_line = " ".join(part for part in [postal_code, city] if part)
        merged = ", ".join(part for part in [street_line, city_line] if part)
        return merged or "-"
