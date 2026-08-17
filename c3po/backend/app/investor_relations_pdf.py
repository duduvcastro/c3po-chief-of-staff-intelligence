from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .schemas import InvestorRelationsResponse


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class InvestorRelationsPdf:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def render(self, report: InvestorRelationsResponse) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(SAO_PAULO)
        filename = f"investor-relations-{now:%Y-%m-%d-%H%M}.pdf"
        path = self.output_dir / filename
        doc = SimpleDocTemplate(
            str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
            topMargin=17 * mm, bottomMargin=15 * mm, title="C3PO Investor Relations Briefing",
        )
        styles = getSampleStyleSheet()
        title = ParagraphStyle("ir-title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=colors.HexColor("#17191e"), spaceAfter=2 * mm)
        subtitle = ParagraphStyle("ir-subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#69717d"))
        section = ParagraphStyle("ir-section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, textColor=colors.HexColor("#6f520b"), spaceBefore=5 * mm, spaceAfter=2 * mm)
        body = ParagraphStyle("ir-body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10.5, textColor=colors.HexColor("#343942"))
        small = ParagraphStyle("ir-small", parent=body, fontSize=7, leading=9, textColor=colors.HexColor("#737b86"))
        right = ParagraphStyle("ir-right", parent=small, alignment=TA_RIGHT)

        story = [
            Paragraph("C3PO | INVESTOR RELATIONS", title),
            Paragraph(f"CVM First + SEC EDGAR + issuer RI | Generated {now:%d/%m/%Y at %H:%M %Z}", subtitle),
            Spacer(1, 5 * mm),
        ]
        metrics = [
            ("EVENTS", report.total_events),
            ("TODAY", report.today_events),
            ("PENDING REVIEW", report.pending_reviews),
            ("HIGH MATERIALITY", report.high_materiality),
        ]
        metric_table = Table([[Paragraph(label, small), Paragraph(f"<b>{value}</b>", body)] for label, value in metrics], colWidths=[42 * mm, 20 * mm], hAlign="LEFT")
        metric_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#faf8f1")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d7c486")),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e6dfc9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([metric_table, Paragraph("OFFICIAL DISCLOSURE FEED", section)])

        for index, event in enumerate(report.items, 1):
            local = event.published_at.astimezone(SAO_PAULO)
            event_time = (
                f"{local:%d/%m/%Y} | time not published"
                if event.published_time_precision == "date"
                else f"{local:%d/%m/%Y} | {local:%H:%M} BRT"
            )
            status_color = "#b52b23" if event.valuation_status == "pending_review" else "#187a55" if event.valuation_status == "incorporated" else "#69717d"
            source = event.source.upper()
            company = f"{event.symbol} | {event.company_name}" if event.symbol else event.company_name
            header = Table([
                [Paragraph(f"<b>{index:02d} · {company}</b>", body), Paragraph(f"<b>{event_time}</b>", right)],
                [Paragraph(f"{source} · {event.event_type} · {event.form or 'Official filing'}", small), Paragraph(f"<font color='{status_color}'><b>{event.valuation_status.replace('_', ' ').upper()}</b></font>", right)],
            ], colWidths=[132 * mm, 44 * mm])
            header.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f7f5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdfe3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            official_url = event.document_url or event.official_url
            document_link = (
                f"<link href='{escape(official_url, quote=True)}' color='#6f520b'><b>Open official document</b></link>"
                if official_url
                else "Official document unavailable"
            )
            detail = Table([
                [Paragraph(f"<b>{event.title}</b><br/>{event.summary}", body)],
                [Paragraph(document_link, small)],
            ], colWidths=[176 * mm])
            detail.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dcdfe3")),
                ("LINEABOVE", (0, 0), (-1, 0), 0, colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.extend([KeepTogether([header, detail]), Spacer(1, 2.5 * mm)])
            if index % 7 == 0 and index < len(report.items):
                story.append(PageBreak())

        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return path

    @staticmethod
    def _footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7c486"))
        canvas.line(16 * mm, 11 * mm, A4[0] - 16 * mm, 11 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#7c838d"))
        canvas.drawString(16 * mm, 7.5 * mm, "C3PO Chief of Staff Intelligence | Official-source monitoring, not investment advice")
        canvas.drawRightString(A4[0] - 16 * mm, 7.5 * mm, f"Page {doc.page}")
        canvas.restoreState()
