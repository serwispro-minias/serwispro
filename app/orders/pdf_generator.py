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
class ProtocolRenderContext:
    title: str
    order_number: str
    generated_at: datetime
    company_name: str
    company_lines: list[str]
    logo_path: Path | None
    intake_datetime_text: str
    issue_datetime_text: str
    customer_lines: list[str]
    device_rows: list[tuple[str, str]]
    issue_description: str
    visual_state: str
    accessories: str
    planned_finish_text: str
    notes: str
    performed_actions: str
    used_parts: str
    action_history: str
    service_cost_text: str
    parts_cost_text: str
    total_cost_text: str
    warranty_text: str
    protocol_photos: list[tuple[bytes | Path, str]]


class ServiceOrderPdfGenerator:
    """Builds printable service order protocol PDFs with ReportLab."""

    def __init__(self) -> None:
        self.font_name = self._register_font()
        self.styles = self._build_styles(self.font_name)

    def render_intake_protocol(self, context: ProtocolRenderContext) -> bytes:
        doc = self._build_document(context=context, is_release=False)
        return self._render(doc)

    def render_release_protocol(self, context: ProtocolRenderContext) -> bytes:
        doc = self._build_document(context=context, is_release=True)
        return self._render(doc)

    def _build_document(self, *, context: ProtocolRenderContext, is_release: bool) -> list[Any]:
        story: list[Any] = []

        story.extend(self._build_header(context))
        story.append(Spacer(1, 6 * mm))

        story.append(Paragraph(context.title, self.styles["title"]))
        story.append(Spacer(1, 3 * mm))

        protocol_meta_rows = [
            ("Numer zlecenia", context.order_number),
            ("Data i godzina wygenerowania", context.generated_at.strftime("%Y-%m-%d %H:%M")),
            ("Data i godzina przyjęcia", context.intake_datetime_text),
        ]
        if is_release:
            protocol_meta_rows.append(("Data i godzina wydania", context.issue_datetime_text))

        story.append(self._label_value_table(protocol_meta_rows))
        story.append(Spacer(1, 4 * mm))

        story.append(Paragraph("Dane klienta", self.styles["section"]))
        story.append(self._single_column_table(["<br/>".join(context.customer_lines)]))
        story.append(Spacer(1, 4 * mm))

        story.append(Paragraph("Dane urządzenia", self.styles["section"]))
        story.append(self._label_value_table(context.device_rows))
        story.append(Spacer(1, 4 * mm))

        story.append(Paragraph("Opis zgłoszenia i stan sprzętu", self.styles["section"]))
        story.extend(self._text_block("Opis zgłoszonej usterki", context.issue_description))
        story.extend(self._text_block("Opis stanu wizualnego", context.visual_state))
        story.extend(self._text_block("Pozostawione akcesoria", context.accessories))
        story.append(self._label_value_table([("Przewidywany termin wykonania", context.planned_finish_text)]))
        story.append(Spacer(1, 2 * mm))
        story.extend(self._text_block("Uwagi", context.notes))

        if is_release:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("Podsumowanie wykonania usługi", self.styles["section"]))
            story.extend(self._text_block("Wykonane czynności", context.performed_actions))
            story.extend(self._text_block("Wykorzystane części", context.used_parts))
            story.extend(self._text_block("Historia napraw", context.action_history))
            release_rows = [
                ("Koszt usługi", context.service_cost_text),
                ("Koszt części", context.parts_cost_text),
                ("Kwota do zapłaty", context.total_cost_text),
                ("Gwarancja na naprawę", context.warranty_text),
            ]
            story.append(self._label_value_table(release_rows))

        if context.protocol_photos:
            story.append(Spacer(1, 5 * mm))
            story.append(Paragraph("Dokumentacja fotograficzna", self.styles["section"]))
            story.extend(self._build_photos_section(context.protocol_photos))

        story.append(Spacer(1, 8 * mm))
        if is_release:
            story.append(self._signature_table("Podpis odbierającego", "Podpis wydającego"))
        else:
            story.append(self._signature_table("Podpis klienta", "Podpis pracownika"))

        return story

    def _build_photos_section(self, photos: list[tuple[bytes | Path, str]]) -> list[Any]:
        story: list[Any] = []
        max_width = 82 * mm
        max_height = 60 * mm

        for index, (image_source, caption) in enumerate(photos, start=1):
            if isinstance(image_source, Path):
                if not image_source.exists() or not image_source.is_file():
                    continue
                source: str | BytesIO = str(image_source)
            else:
                source = BytesIO(image_source)

            try:
                image = Image(source)
                width = float(image.imageWidth or 1)
                height = float(image.imageHeight or 1)
                scale = min(float(max_width) / width, float(max_height) / height, 1.0)
                image.drawWidth = width * scale
                image.drawHeight = height * scale
                image.hAlign = "LEFT"
                story.append(image)
                story.append(Spacer(1, 1.5 * mm))
                story.append(Paragraph(f"Zdjęcie {index}: {self._safe_text(caption)}", self.styles["muted"]))
                story.append(Spacer(1, 3 * mm))
            except Exception:
                continue

        if not story:
            return [Paragraph("Brak dostępnych zdjęć do osadzenia.", self.styles["muted"])]

        return story

    def _build_header(self, context: ProtocolRenderContext) -> list[Any]:
        left = self._build_logo_cell(context.logo_path)
        right = Paragraph("<br/>".join(context.company_lines), self.styles["normal"])

        table = Table(
            [[left, right]],
            colWidths=[55 * mm, 125 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
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
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def _label_value_table(self, rows: list[tuple[str, str]]) -> Table:
        rendered_rows = [
            [Paragraph(label, self.styles["label"]), Paragraph(self._safe_text(value), self.styles["normal"])]
            for label, value in rows
        ]

        table = Table(rendered_rows, colWidths=[52 * mm, 128 * mm])
        table.setStyle(
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
        return table

    def _signature_table(self, left_title: str, right_title: str) -> Table:
        table = Table(
            [
                [Paragraph(left_title, self.styles["label"]), Paragraph(right_title, self.styles["label"])],
                [Paragraph("<br/><br/><br/>", self.styles["normal"]), Paragraph("<br/><br/><br/>", self.styles["normal"])],
            ],
            colWidths=[90 * mm, 90 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.black),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def _text_block(self, label: str, value: str) -> list[Any]:
        safe_value = self._safe_text(value)
        return [
            Paragraph(f"<b>{label}</b>", self.styles["label"]),
            Paragraph(safe_value, self.styles["normal"]),
            Spacer(1, 2 * mm),
        ]

    def _render(self, story: list[Any]) -> bytes:
        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title="SerwisPRO Protokół",
            author="SerwisPRO",
            pageCompression=0,
        )
        document.build(story)
        return output.getvalue()

    def _build_styles(self, font_name: str) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        normal = ParagraphStyle(
            "ProtocolNormal",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=12,
        )
        label = ParagraphStyle(
            "ProtocolLabel",
            parent=normal,
            fontName=font_name,
            fontSize=9,
            leading=12,
            spaceAfter=0,
        )
        section = ParagraphStyle(
            "ProtocolSection",
            parent=normal,
            fontName=font_name,
            fontSize=11,
            leading=14,
            spaceAfter=4,
            spaceBefore=2,
        )
        title = ParagraphStyle(
            "ProtocolTitle",
            parent=normal,
            fontName=font_name,
            fontSize=14,
            leading=18,
            alignment=1,
            spaceAfter=4,
        )
        muted = ParagraphStyle(
            "ProtocolMuted",
            parent=normal,
            fontName=font_name,
            fontSize=9,
            textColor=colors.grey,
            alignment=1,
        )
        return {
            "normal": normal,
            "label": label,
            "section": section,
            "title": title,
            "muted": muted,
        }

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
                    font_name = f"ProtocolFont_{path.stem}"
                    pdfmetrics.registerFont(TTFont(font_name, str(path)))
                    return font_name
                except Exception:
                    continue

        return "Helvetica"

    def _safe_text(self, value: str | None) -> str:
        if value is None:
            return "-"
        normalized = value.strip()
        if not normalized:
            return "-"
        return normalized.replace("\n", "<br/>")
