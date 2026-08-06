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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass(slots=True)
class InventoryPdfContext:
    title: str
    generated_at: datetime
    company_lines: list[str]
    rows: list[tuple[str, str]]
    table_headers: tuple[str, ...] | None = None
    table_rows: list[tuple[str, ...]] | None = None


class InventoryPdfGenerator:
    def __init__(self) -> None:
        self.font_name = self._register_font()
        self.styles = self._build_styles(self.font_name)

    def render(self, context: InventoryPdfContext) -> bytes:
        story: list[Any] = []

        story.append(Paragraph(context.title, self.styles["title"]))
        story.append(Paragraph(context.generated_at.strftime("Wygenerowano: %Y-%m-%d %H:%M"), self.styles["muted"]))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("<br/>".join(context.company_lines), self.styles["normal"]))
        story.append(Spacer(1, 4 * mm))

        if context.rows:
            summary = Table(
                [[Paragraph(label, self.styles["label"]), Paragraph(value or "-", self.styles["normal"])] for label, value in context.rows],
                colWidths=[55 * mm, 125 * mm],
            )
            summary.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                    ]
                )
            )
            story.append(summary)
            story.append(Spacer(1, 4 * mm))

        if context.table_headers and context.table_rows:
            table_data: list[list[Any]] = [
                [Paragraph(header, self.styles["label"]) for header in context.table_headers]
            ]
            for row in context.table_rows:
                table_data.append([Paragraph(cell or "-", self.styles["normal"]) for cell in row])

            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.black),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)

        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        document.build(story)
        return output.getvalue()

    def _build_styles(self, font_name: str) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        normal = ParagraphStyle("InventoryNormal", parent=base["BodyText"], fontName=font_name, fontSize=9, leading=12)
        label = ParagraphStyle("InventoryLabel", parent=normal, fontSize=9)
        title = ParagraphStyle("InventoryTitle", parent=normal, fontSize=14, leading=18, alignment=1)
        muted = ParagraphStyle("InventoryMuted", parent=normal, fontSize=8, textColor=colors.grey, alignment=1)
        return {"normal": normal, "label": label, "title": title, "muted": muted}

    def _register_font(self) -> str:
        candidate_paths = [
            Path("app/static/fonts/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/local/share/fonts/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/calibri.ttf"),
        ]
        for path in candidate_paths:
            if path.exists() and path.is_file():
                try:
                    font_name = f"InventoryFont_{path.stem}"
                    pdfmetrics.registerFont(TTFont(font_name, str(path)))
                    return font_name
                except Exception:
                    continue
        return "Helvetica"
