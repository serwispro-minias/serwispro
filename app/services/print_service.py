from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.orders.print_repository import ServiceOrderPrintRepository

from .pdf_generator import EstimatePdfGenerator, EstimateRenderContext
from .repository import EstimateRepository


@dataclass(slots=True)
class EstimateDocument:
    filename: str
    content: bytes


class EstimatePrintService:
    def __init__(self, repository: EstimateRepository | None = None, print_repository: ServiceOrderPrintRepository | None = None, generator: EstimatePdfGenerator | None = None) -> None:
        self.repository = repository or EstimateRepository()
        self.print_repository = print_repository or ServiceOrderPrintRepository()
        self.generator = generator or EstimatePdfGenerator()

    def build_pdf(self, *, estimate_id: int, company_id: int, branch_id: int | None, upload_root: Path) -> EstimateDocument | None:
        estimate = self.repository.get_estimate(estimate_id=estimate_id, company_id=company_id, branch_id=branch_id)
        if estimate is None:
            return None

        order = estimate.service_order
        company = self.print_repository.get_company(company_id=company_id)
        if order is None or company is None:
            return None

        branch = self.print_repository.get_branch(branch_id=order.branch_id, company_id=company_id)
        settings_map = self.print_repository.get_settings_map(company_id=company_id, branch_id=order.branch_id)

        company_name = self._get_setting(settings_map, ["company_name", "service_name", "serwis_name", "nazwa_firmy", "nazwa_serwisu"], default=company.name)
        company_lines = [company_name]
        address_line = self._get_setting(settings_map, ["company_address", "service_address", "adres", "adres_serwisu"], default=(branch.address if branch and branch.address else ""))
        if address_line:
            company_lines.append(address_line)
        phone_line = self._get_setting(settings_map, ["company_phone", "service_phone", "telefon", "telefon_serwisu"], default=(branch.phone if branch and branch.phone else (company.phone or "")))
        if phone_line:
            company_lines.append(f"Tel: {phone_line}")
        email_line = self._get_setting(settings_map, ["company_email", "service_email", "email", "e_mail"], default=(branch.email if branch and branch.email else (company.email or "")))
        if email_line:
            company_lines.append(f"E-mail: {email_line}")
        logo_setting = self._get_setting(settings_map, ["company_logo", "service_logo", "logo", "logo_path"], default=(company.logo or ""))
        logo_path = self._resolve_logo_path(logo_setting, upload_root)

        customer = order.customer
        device = order.device
        customer_name = customer.full_name or customer.short_name or f"Klient #{customer.id}"
        customer_lines = [
            f"Nazwa / Imię i nazwisko: {customer_name}",
            f"Email: {customer.email or '-'}",
            f"Telefon: {customer.phone or customer.phone2 or '-'}",
        ]
        device_rows = [
            ("Producent", device.manufacturer or "-"),
            ("Model", device.model or "-"),
            ("Numer seryjny", device.serial_number or "-"),
            ("Numer inwentarzowy", device.inventory_number or "-"),
        ]

        items = [self._serialize_item(item) for item in estimate.items]
        context = EstimateRenderContext(
            title=estimate.title,
            estimate_number=f"{order.order_number}/{estimate.version_number:02d}",
            generated_at=datetime.now(timezone.utc),
            company_lines=company_lines,
            logo_path=logo_path,
            customer_lines=customer_lines,
            device_rows=device_rows,
            issue_description=order.issue_description or "-",
            items=items,
            parts_net_text=f"{estimate.parts_net:.2f} PLN",
            materials_net_text=f"{estimate.materials_net:.2f} PLN",
            services_net_text=f"{estimate.services_net:.2f} PLN",
            discount_text=f"{estimate.discount_total:.2f} PLN",
            net_text=f"{estimate.net_total:.2f} PLN",
            vat_text=f"{estimate.vat_total:.2f} PLN",
            gross_text=f"{estimate.gross_total:.2f} PLN",
            valid_until_text=(estimate.valid_until.strftime("%Y-%m-%d") if estimate.valid_until else "-"),
            notes=estimate.notes or "-",
        )
        content = self.generator.render(context)
        return EstimateDocument(filename=f"kosztorys_{order.order_number}_v{estimate.version_number:02d}.pdf", content=content)

    def _serialize_item(self, item) -> dict[str, str]:
        return {
            "sort_order": str(item.sort_order),
            "source_type": item.source_type,
            "name": item.name,
            "quantity": f"{item.quantity:.3f}",
            "unit": item.unit,
            "unit_net_price": f"{item.unit_net_price:.2f}",
            "discount_percent": f"{item.discount_percent:.2f}",
            "vat_rate": f"{item.vat_rate:.2f}",
            "net_value": f"{item.net_value:.2f}",
            "vat_value": f"{item.vat_value:.2f}",
            "gross_value": f"{item.gross_value:.2f}",
        }

    def _get_setting(self, settings_map: dict[str, str], keys: list[str], default: str) -> str:
        for key in keys:
            value = (settings_map.get(key) or "").strip()
            if value:
                return value
        return default

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