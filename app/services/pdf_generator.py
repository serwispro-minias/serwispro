from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass(slots=True)
class EstimateRenderContext:
    title: str
    estimate_number: str
    generated_at: datetime
    company_lines: list[str]
    logo_path: Path | None
    customer_lines: list[str]
    device_rows: list[tuple[str, str]]
    issue_description: str
    items: list[dict[str, str]]
    parts_net_text: str
    materials_net_text: str
    services_net_text: str
    discount_text: str
    net_text: str
    vat_text: str
    gross_text: str
    valid_until_text: str
    notes: str


class EstimatePdfGenerator:
    def __init__(self) -> None:
        self.font_name = self._register_font()
        self.styles = self._build_styles(self.font_name)

    def render(self, context: EstimateRenderContext) -> bytes:
        story: list[Any] = []
        story.extend(self._build_header(context))
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(context.title, self.styles["title"]))
        story.append(Spacer(1, 3 * mm))
        story.append(self._label_value_table([
            ("Numer kosztorysu", context.estimate_number),
            ("Data wygenerowania", context.generated_at.strftime("%Y-%m-%d %H:%M")),
            ("Ważny do", context.valid_until_text),
        ]))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Dane klienta", self.styles["section"]))
        story.append(self._single_column_table(["<br/>".join(context.customer_lines)]))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Dane urządzenia", self.styles["section"]))
        story.append(self._label_value_table(context.device_rows))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._text_block("Opis zgłoszenia", context.issue_description))
        story.append(Paragraph("Pozycje kosztorysu", self.styles["section"]))
        story.append(self._items_table(context.items))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Podsumowanie", self.styles["section"]))
        story.append(self._label_value_table([
            ("Części netto", context.parts_net_text),
            ("Materiały netto", context.materials_net_text),
            ("Usługi netto", context.services_net_text),
            ("Rabat łącznie", context.discount_text),
            ("Razem netto", context.net_text),
            ("VAT", context.vat_text),
            ("Razem brutto", context.gross_text),
        ]))
        story.append(Spacer(1, 4 * mm))
        story.extend(self._text_block("Uwagi", context.notes))
        story.append(Spacer(1, 8 * mm))
        story.append(self._signature_table("Podpis klienta", "Podpis serwisu"))
        return self._render(story)

    def _build_header(self, context: EstimateRenderContext) -> list[Any]:
        left = self._build_logo_cell(context.logo_path)
        right = Paragraph("<br/>".join(context.company_lines), self.styles["normal"])
        table = Table([[left, right]], colWidths=[55 * mm, 125 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return [table]

    def _build_logo_cell(self, logo_path: Path | None) -> Any:
        if logo_path is not None and logo_path.exists() and logo_path.is_file():
            try:
                image = Image(str(logo_path))
                image.drawWidth = 45 * mm
                image.drawHeight = 20 * mm
                image.hAlign = "LEFT"
                return image
            except Exception:
                pass
        return Paragraph("LOGO", self.styles["muted"])

    def _single_column_table(self, values: list[str]) -> Table:
        rows = [[Paragraph(value, self.styles["normal"])] for value in values]
        table = Table(rows, colWidths=[180 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _label_value_table(self, rows: list[tuple[str, str]]) -> Table:
        rendered_rows = [[Paragraph(label, self.styles["label"]), Paragraph(self._safe_text(value), self.styles["normal"])] for label, value in rows]
        table = Table(rendered_rows, colWidths=[52 * mm, 128 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ]))
        return table

    def _items_table(self, items: list[dict[str, str]]) -> Table:
        rows = [[
            Paragraph("Lp", self.styles["label"]),
            Paragraph("Rodzaj", self.styles["label"]),
            Paragraph("Pozycja", self.styles["label"]),
            Paragraph("Ilość", self.styles["label"]),
            Paragraph("Jm", self.styles["label"]),
            Paragraph("Cena netto", self.styles["label"]),
            Paragraph("Rabat", self.styles["label"]),
            Paragraph("VAT", self.styles["label"]),
            Paragraph("Netto", self.styles["label"]),
            Paragraph("VAT", self.styles["label"]),
            Paragraph("Brutto", self.styles["label"]),
        ]]
        for item in items:
            rows.append([
                Paragraph(item["sort_order"], self.styles["normal"]),
                Paragraph(item["source_type"], self.styles["normal"]),
                Paragraph(item["name"], self.styles["normal"]),
                Paragraph(item["quantity"], self.styles["normal"]),
                Paragraph(item["unit"], self.styles["normal"]),
                Paragraph(item["unit_net_price"], self.styles["normal"]),
                Paragraph(item["discount_percent"], self.styles["normal"]),
                Paragraph(item["vat_rate"], self.styles["normal"]),
                Paragraph(item["net_value"], self.styles["normal"]),
                Paragraph(item["vat_value"], self.styles["normal"]),
                Paragraph(item["gross_value"], self.styles["normal"]),
            ])
        table = Table(rows, colWidths=[9 * mm, 18 * mm, 42 * mm, 14 * mm, 10 * mm, 17 * mm, 13 * mm, 13 * mm, 18 * mm, 18 * mm, 18 * mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ]))
        return table

    def _signature_table(self, left_title: str, right_title: str) -> Table:
        table = Table(
            [
                [Paragraph(left_title, self.styles["label"]), Paragraph(right_title, self.styles["label"])],
                [Paragraph("<br/><br/><br/>", self.styles["normal"]), Paragraph("<br/><br/><br/>", self.styles["normal"])],
            ],
            colWidths=[90 * mm, 90 * mm],
        )
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def _text_block(self, label: str, value: str) -> list[Any]:
        return [Paragraph(f"<b>{label}</b>", self.styles["label"]), Paragraph(self._safe_text(value), self.styles["normal"]), Spacer(1, 2 * mm)]

    def _render(self, story: list[Any]) -> bytes:
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="SerwisPRO Kosztorys",
            author="SerwisPRO",
            pageCompression=0,
        )
        document.build(story)
        return output.getvalue()

    def _build_styles(self, font_name: str) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        normal = ParagraphStyle("EstimateNormal", parent=base["BodyText"], fontName=font_name, fontSize=8.5, leading=11)
        label = ParagraphStyle("EstimateLabel", parent=normal, fontName=font_name, fontSize=8.5, leading=11, spaceAfter=0)
        section = ParagraphStyle("EstimateSection", parent=normal, fontName=font_name, fontSize=10, leading=12, spaceBefore=2, spaceAfter=4)
        title = ParagraphStyle("EstimateTitle", parent=base["Title"], fontName=font_name, fontSize=16, leading=19, spaceAfter=4)
        muted = ParagraphStyle("EstimateMuted", parent=normal, textColor=colors.grey)
        return {"normal": normal, "label": label, "section": section, "title": title, "muted": muted}

    def _register_font(self) -> str:
        font_candidates = [
            ("DejaVuSans", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")),
            ("DejaVuSans", Path("C:/Windows/Fonts/DejaVuSans.ttf")),
            ("Arial", Path("C:/Windows/Fonts/arial.ttf")),
        ]
        for font_name, font_path in font_candidates:
            if font_path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                    return font_name
                except Exception:
                    continue
        return "Helvetica"

    def _safe_text(self, value: str) -> str:
        return value or "-"