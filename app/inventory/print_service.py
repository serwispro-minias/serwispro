from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import inspect

from app.extensions import db
from app.models.setting import Setting

from .pdf_generator import InventoryPdfContext, InventoryPdfGenerator
from .service import InventoryService


@dataclass(slots=True)
class InventoryPdfDocument:
    filename: str
    content: bytes


class InventoryPrintService:
    def __init__(self, service: InventoryService | None = None, generator: InventoryPdfGenerator | None = None) -> None:
        self.service = service or InventoryService()
        self.generator = generator or InventoryPdfGenerator()

    def build_part_card(self, *, part_id: int, company_id: int | None) -> InventoryPdfDocument | None:
        part = self.service.get_part(part_id, company_id=company_id)
        if part is None:
            return None

        context = InventoryPdfContext(
            title="Karta części / materiału",
            generated_at=datetime.now(timezone.utc),
            company_lines=self._company_lines(company_id),
            rows=[
                ("Kod części", part.part_code),
                ("Nazwa", part.name),
                ("Producent", part.manufacturer or "-"),
                ("Numer katalogowy", part.catalog_number or "-"),
                ("Stan", f"{Decimal(part.current_stock):.3f} {part.unit}"),
                ("Stan minimalny", f"{Decimal(part.minimum_stock):.3f} {part.unit}"),
                ("Cena netto", f"{Decimal(part.sale_price_net):.2f} PLN"),
                ("VAT", f"{Decimal(part.vat_rate):.2f}%"),
                ("Lokalizacja", part.location or "-"),
                ("Dostawca", part.supplier or "-"),
            ],
        )
        return InventoryPdfDocument(
            filename=f"karta_czesci_{part.part_code}.pdf",
            content=self.generator.render(context),
        )

    def build_part_history(self, *, part_id: int, company_id: int | None) -> InventoryPdfDocument | None:
        part = self.service.get_part(part_id, company_id=company_id)
        if part is None:
            return None

        operations = self.service.list_part_operations(part.id, company_id=company_id)
        rows: list[tuple[str, ...]] = []
        for op in operations:
            rows.append(
                (
                    op.operation_at.strftime("%Y-%m-%d %H:%M") if op.operation_at else "-",
                    op.operation_type,
                    f"{Decimal(op.quantity):.3f}",
                    f"{Decimal(op.stock_before):.3f}",
                    f"{Decimal(op.stock_after):.3f}",
                    op.document_number or "-",
                )
            )

        context = InventoryPdfContext(
            title=f"Historia operacji: {part.part_code}",
            generated_at=datetime.now(timezone.utc),
            company_lines=self._company_lines(company_id),
            rows=[("Część", f"{part.part_code} | {part.name}")],
            table_headers=("Data", "Typ", "Ilość", "Przed", "Po", "Dokument"),
            table_rows=rows,
        )
        return InventoryPdfDocument(
            filename=f"historia_czesci_{part.part_code}.pdf",
            content=self.generator.render(context),
        )

    def build_stock_state(self, *, company_id: int | None) -> InventoryPdfDocument:
        parts_page = self.service.list_parts(page=1, per_page=1000, company_id=company_id, query_text=None)
        rows: list[tuple[str, ...]] = []
        for part in parts_page["items"]:
            state = f"{Decimal(part.current_stock):.3f} {part.unit}"
            minimum = f"{Decimal(part.minimum_stock):.3f} {part.unit}"
            warning = "Stan poniżej minimum" if Decimal(part.current_stock) < Decimal(part.minimum_stock) else "-"
            rows.append((part.part_code, part.name, state, minimum, warning))

        context = InventoryPdfContext(
            title="Stany magazynowe",
            generated_at=datetime.now(timezone.utc),
            company_lines=self._company_lines(company_id),
            rows=[],
            table_headers=("Kod", "Nazwa", "Stan", "Minimum", "Uwagi"),
            table_rows=rows,
        )
        return InventoryPdfDocument(
            filename="stany_magazynowe.pdf",
            content=self.generator.render(context),
        )

    def _company_lines(self, company_id: int | None) -> list[str]:
        if company_id is None:
            return ["SerwisPRO"]

        inspector = inspect(db.engine)
        if not inspector.has_table("settings"):
            return ["SerwisPRO"]

        settings = {
            setting.key.lower(): setting.value
            for setting in Setting.query.filter_by(company_id=company_id, is_active=True).all()
        }
        name = settings.get("company_name") or "SerwisPRO"
        address = settings.get("company_address") or ""
        nip = settings.get("company_nip") or ""

        lines = [name]
        if address:
            lines.append(address)
        if nip:
            lines.append(f"NIP: {nip}")
        return lines
