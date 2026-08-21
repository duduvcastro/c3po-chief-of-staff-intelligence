from __future__ import annotations

import calendar
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


PAGE_W, PAGE_H = landscape(A4)
MARGIN = 8 * mm

INK = colors.HexColor("#111827")
SUB = colors.HexColor("#59636E")
LIGHT = colors.HexColor("#F5F7F9")
BORDER = colors.HexColor("#D9E0E7")
GOLD = colors.HexColor("#D4A72C")
GOLD_LIGHT = colors.HexColor("#FFF8E6")
BLUE = colors.HexColor("#1473E6")
BLUE_LIGHT = colors.HexColor("#EAF3FF")
GREEN = colors.HexColor("#087A55")
GREEN_LIGHT = colors.HexColor("#E9F7F0")
RED = colors.HexColor("#B42318")
RED_LIGHT = colors.HexColor("#FFF1F1")
AMBER = colors.HexColor("#D97706")
PURPLE = colors.HexColor("#6D4AFF")
WHITE = colors.white


class PremiumOnePagerRenderer:
    """Render the web One Pager with the editorial quality of the AMZN template."""

    def __init__(self) -> None:
        self.styles = {
            "body": ParagraphStyle(
                "body",
                fontName="Helvetica",
                fontSize=7.0,
                leading=8.8,
                textColor=INK,
                alignment=TA_JUSTIFY,
                spaceAfter=0,
            ),
            "small": ParagraphStyle(
                "small",
                fontName="Helvetica",
                fontSize=5.65,
                leading=6.75,
                textColor=SUB,
                alignment=TA_JUSTIFY,
                spaceAfter=0,
            ),
            "bullet": ParagraphStyle(
                "bullet",
                fontName="Helvetica",
                fontSize=6.7,
                leading=8.25,
                textColor=INK,
                leftIndent=7,
                firstLineIndent=-7,
                alignment=TA_JUSTIFY,
                spaceAfter=1.3,
            ),
        }

    def render(
        self,
        path: Path,
        data: dict[str, Any],
        history: list[dict[str, Any]],
        generated_at: datetime,
    ) -> None:
        pdf = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
        pdf.setTitle(f"{data['symbol']} One Pager | C3PO")
        self._header(pdf, data)

        left_x = MARGIN
        left_w = 520
        right_x = left_x + left_w + 10
        right_w = PAGE_W - MARGIN - right_x

        self._metric_table(pdf, left_x, 354, left_w, 150, data)
        self._valuation_table(pdf, right_x, 262, right_w, 242, data, history)

        self._bullet_box(
            pdf,
            left_x,
            234,
            252,
            110,
            "Leitura do trimestre",
            data["quarter_read"],
            accent=GREEN,
        )
        self._bullet_box(
            pdf,
            left_x + 262,
            234,
            258,
            110,
            "Qualidade do lucro e caixa",
            data["cash_quality"],
            accent=RED,
            fill=colors.HexColor("#FFFAFA"),
        )
        self._bullet_box(
            pdf,
            left_x,
            91,
            252,
            132,
            "Tese de investimento",
            data["thesis"],
            accent=BLUE,
        )
        self._bullet_box(
            pdf,
            left_x + 262,
            91,
            258,
            132,
            "Riscos e próximos gatilhos",
            data["risks"],
            accent=RED,
            fill=colors.HexColor("#FFFAFA"),
        )
        self._scenario_box(pdf, right_x, 91, right_w, 160, data)
        self._footer(pdf, data, generated_at)
        pdf.showPage()
        pdf.save()

    def _header(self, pdf: canvas.Canvas, data: dict[str, Any]) -> None:
        pdf.setFillColor(INK)
        pdf.rect(0, PAGE_H - 78, PAGE_W, 78, fill=1, stroke=0)
        pdf.setFillColor(GOLD)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(MARGIN, PAGE_H - 21, "C3PO EQUITY RESEARCH | EARNINGS & VALUATION UPDATE")
        pdf.setFillColor(WHITE)
        title = f"{data['symbol']} | {str(data['company_name']).upper()}"
        font_size = self._fit_font(title, "Helvetica-Bold", 26, 18, 420)
        pdf.setFont("Helvetica-Bold", font_size)
        pdf.drawString(MARGIN, PAGE_H - 50, title)
        pdf.setFillColor(colors.HexColor("#CAD1D8"))
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(MARGIN, PAGE_H - 66, str(data["headline"])[:112])

        card_y = PAGE_H - 65
        self._kpi(
            pdf,
            470,
            card_y,
            105,
            "Preço atual",
            self._money(data["price"], data["currency"]),
            f"{data['price_date']} | {self._signed(data.get('change_percent'))}",
            fill=WHITE,
        )
        self._kpi(
            pdf,
            582,
            card_y,
            105,
            "C3PO TP 12m",
            self._money(data["c3po_tp"], data["currency"], decimals=0),
            "média de cinco métodos",
            fill=BLUE_LIGHT,
            value_color=BLUE,
        )
        upside_color = GREEN if data["upside_percent"] >= 0 else RED
        self._kpi(
            pdf,
            694,
            card_y,
            123,
            "Upside",
            f"{data['upside_percent']:+.0f}%",
            f"rating: {data['rating']}",
            fill=GREEN_LIGHT if data["upside_percent"] >= 0 else RED_LIGHT,
            value_color=upside_color,
        )

    def _metric_table(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, data: dict[str, Any]) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, data["results_title"], x + 11, y + h - 20, w - 22)
        columns = [x + 12, x + 224, x + 330, x + 421]
        header_y = y + h - 46
        pdf.setFillColor(LIGHT)
        pdf.rect(x + 9, header_y - 4, w - 18, 16, fill=1, stroke=0)
        headers = ("Métrica", data["latest_period"], data["comparison_period"], "YoY / delta")
        for index, text in enumerate(headers):
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 6.4)
            pdf.drawString(columns[index], header_y + 1, str(text).upper())

        row_y = header_y - 14
        for index, row in enumerate(data["financial_rows"][:6]):
            if index % 2:
                pdf.setFillColor(colors.HexColor("#FAFBFC"))
                pdf.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
            for column, text in enumerate(row):
                value_color = GREEN if column == 3 and str(text).startswith("+") else RED if column == 3 and str(text).startswith("-") else INK
                pdf.setFillColor(value_color)
                pdf.setFont("Helvetica-Bold" if column in (0, 3) else "Helvetica", 6.9)
                pdf.drawString(columns[column], row_y, str(text)[:30])
            row_y -= 17

    def _valuation_table(
        self,
        pdf: canvas.Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        data: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        self._rounded_box(pdf, x, y, w, h, fill=colors.HexColor("#FBFCFE"))
        self._section_title(pdf, "Performance 12m + valuation", x + 11, y + h - 20, w - 22, BLUE)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica-Oblique", 4.6)
        pdf.drawRightString(x + w - 11, y + h - 16.5, f"perfil: {self._profile_label(data.get('profile'))}")
        self._performance_chart(pdf, x + 10, y + 112, w - 20, 91, data, history)

        pdf.setFillColor(LIGHT)
        pdf.rect(x + 9, y + 95, w - 18, 13, fill=1, stroke=0)
        for text, xpos in (("Modelo", x + 12), ("TP", x + 145), ("Upside", x + w - 60)):
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 5.4)
            pdf.drawString(xpos, y + 99.5, text.upper())

        methods = list(data["methods"].items())
        method_values = [value for _, value in methods]
        highest = max(method_values)
        lowest = min(method_values)
        name_col_width = 128
        yy = y + 83
        for index, (name, value) in enumerate(methods):
            if index % 2:
                pdf.setFillColor(WHITE)
                pdf.rect(x + 9, yy - 3.2, w - 18, 9.7, fill=1, stroke=0)
            value_color = GREEN if value == highest else RED if value == lowest else INK
            pdf.setFillColor(INK)
            name_font = self._fit_font(name, "Helvetica-Bold", 5.3, 4.0, name_col_width)
            pdf.setFont("Helvetica-Bold", name_font)
            pdf.drawString(x + 12, yy, name)
            pdf.setFillColor(value_color)
            pdf.setFont("Helvetica-Bold", 5.4)
            pdf.drawRightString(x + 190, yy, self._money(value, data["currency"]))
            method_upside = (value / data["price"] - 1) * 100
            pdf.setFillColor(GREEN if method_upside >= 0 else RED)
            pdf.drawRightString(x + w - 12, yy, f"{method_upside:+.1f}%")
            yy -= 10.2

        pdf.setStrokeColor(BORDER)
        pdf.line(x + 10, y + 34, x + w - 10, y + 34)
        self._valuation_summary_band(pdf, x + 10, y + 5, w - 20, 32, data)

    def _performance_chart(
        self,
        pdf: canvas.Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        data: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> None:
        pdf.setFillColor(WHITE)
        pdf.setStrokeColor(BORDER)
        pdf.setLineWidth(0.5)
        pdf.roundRect(x, y, w, h, 4, fill=1, stroke=1)

        points: list[tuple[datetime, float]] = []
        for item in history:
            try:
                observed_at = datetime.fromisoformat(str(item.get("date") or "")[:10])
                close = float(item.get("close"))
            except (TypeError, ValueError):
                continue
            if close > 0:
                points.append((observed_at, close))
        points.sort(key=lambda item: item[0])

        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica-Bold", 5.4)
        pdf.drawString(x + 7, y + h - 10, "AÇÃO | ÚLTIMOS 12 MESES")
        coverage = self._coverage_label(data)
        coverage_width = min(w - 102, max(84, pdf.stringWidth(coverage, "Helvetica-Bold", 4.7) + 10))
        pdf.setFillColor(GOLD_LIGHT)
        pdf.setStrokeColor(colors.HexColor("#E8CD7C"))
        pdf.roundRect(x + w - coverage_width - 6, y + h - 17, coverage_width, 12, 5, fill=1, stroke=1)
        coverage_font = self._fit_font(coverage, "Helvetica-Bold", 4.7, 3.9, coverage_width - 8)
        self._draw_colored_coverage(
            pdf,
            center_x=x + w - coverage_width / 2 - 6,
            baseline_y=y + h - 13,
            font_size=coverage_font,
            data=data,
        )

        if len(points) < 2:
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.3)
            pdf.drawCentredString(x + w / 2, y + 21, "Histórico de preços indisponível")
            return

        first_date, first_price = points[0]
        last_date, last_price = points[-1]
        prices = [price for _, price in points]
        observed_low = min(prices)
        observed_high = max(prices)
        low = observed_low
        high = observed_high
        median_price = sorted(prices)[len(prices) // 2]
        price_span = high - low
        if price_span <= 0:
            price_span = max(high * 0.08, 1.0)
            low -= price_span / 2
            high += price_span / 2
        else:
            low -= price_span * 0.06
            high += price_span * 0.06
            price_span = high - low

        plot_x = x + 31
        plot_y = y + 13
        plot_w = w - 39
        plot_h = h - 39
        seconds = max((last_date - first_date).total_seconds(), 1.0)

        for level in (observed_low, median_price, observed_high):
            level_y = plot_y + (level - low) / price_span * plot_h
            pdf.setStrokeColor(colors.HexColor("#E5E9EE"))
            pdf.setLineWidth(0.35)
            pdf.line(plot_x, level_y, plot_x + plot_w, level_y)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 4.3)
            pdf.drawRightString(plot_x - 4, level_y - 1.5, self._axis_money(level, data["currency"]))

        for quarter_end, label in self._quarter_markers(first_date, last_date):
            quarter_x = plot_x + (quarter_end - first_date).total_seconds() / seconds * plot_w
            pdf.setStrokeColor(colors.HexColor("#E7E1F7"))
            pdf.setLineWidth(0.35)
            pdf.setDash(1.3, 1.3)
            pdf.line(quarter_x, plot_y, quarter_x, plot_y + plot_h)
            pdf.setDash()
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 4.2)
            pdf.drawCentredString(quarter_x, y + 4, label)

        path = pdf.beginPath()
        for index, (observed_at, price) in enumerate(points):
            px = plot_x + (observed_at - first_date).total_seconds() / seconds * plot_w
            py = plot_y + (price - low) / price_span * plot_h
            path.moveTo(px, py) if index == 0 else path.lineTo(px, py)
        pdf.setStrokeColor(PURPLE)
        pdf.setLineWidth(1.1)
        pdf.drawPath(path, stroke=1, fill=0)
        last_y = plot_y + (last_price - low) / price_span * plot_h
        pdf.setFillColor(PURPLE)
        pdf.circle(plot_x + plot_w, last_y, 2.2, fill=1, stroke=0)

        period_return = (last_price / first_price - 1) * 100
        pdf.setFillColor(GREEN if period_return >= 0 else RED)
        pdf.setFont("Helvetica-Bold", 4.8)
        pdf.drawString(
            x + 7,
            y + h - 21,
            f"12M {period_return:+.1f}%  |  LOW {self._plain_money(observed_low, data['currency'])}  |  HIGH {self._plain_money(observed_high, data['currency'])}",
        )
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica", 4.4)
        pdf.drawRightString(x + w - 7, y + h - 21, f"{first_date:%d/%m/%y} - {last_date:%d/%m/%y}")

    _PROFILE_LABELS = {
        "financial": "Financeiro (bancos/seguradoras)",
        "utilities": "Utilities",
        "real_estate": "Real Estate",
        "technology": "Tecnologia",
        "cyclical": "Cíclico (energia/materiais)",
        "quality": "Qualidade (saúde/consumo)",
        "general": "Geral",
    }

    @classmethod
    def _profile_label(cls, profile: Any) -> str:
        return cls._PROFILE_LABELS.get(str(profile), "Geral")

    @staticmethod
    def _coverage_label(data: dict[str, Any]) -> str:
        total = int(data["analyst_count"]) if data.get("analyst_count") else None
        buy = data.get("analyst_buy")
        hold = data.get("analyst_hold")
        sell = data.get("analyst_sell")
        total_label = f"{total} ANALISTAS" if total else "COBERTURA N/D"
        if all(value is not None for value in (buy, hold, sell)):
            return f"{total_label} | BUY {int(buy)} | HOLD {int(hold)} | SELL {int(sell)}"
        return f"{total_label} | BUY N/D | HOLD N/D | SELL N/D"

    @staticmethod
    def _draw_colored_coverage(
        pdf: canvas.Canvas,
        *,
        center_x: float,
        baseline_y: float,
        font_size: float,
        data: dict[str, Any],
    ) -> None:
        total = int(data["analyst_count"]) if data.get("analyst_count") else None
        total_label = f"{total} ANALISTAS" if total else "COBERTURA N/D"
        values = (
            str(int(data["analyst_buy"])) if data.get("analyst_buy") is not None else "N/D",
            str(int(data["analyst_hold"])) if data.get("analyst_hold") is not None else "N/D",
            str(int(data["analyst_sell"])) if data.get("analyst_sell") is not None else "N/D",
        )
        neutral = colors.HexColor("#73510A")
        segments = [
            (total_label, neutral),
            (" | ", neutral),
            (f"BUY {values[0]}", GREEN),
            (" | ", neutral),
            (f"HOLD {values[1]}", BLUE),
            (" | ", neutral),
            (f"SELL {values[2]}", RED),
        ]
        pdf.setFont("Helvetica-Bold", font_size)
        widths = [pdf.stringWidth(text, "Helvetica-Bold", font_size) for text, _ in segments]
        cursor_x = center_x - sum(widths) / 2
        for (text, color), width in zip(segments, widths):
            pdf.setFillColor(color)
            pdf.drawString(cursor_x, baseline_y, text)
            cursor_x += width

    @staticmethod
    def _quarter_markers(first_date: datetime, last_date: datetime) -> list[tuple[datetime, str]]:
        markers: list[tuple[datetime, str]] = []
        for year in range(first_date.year, last_date.year + 1):
            for month in (3, 6, 9, 12):
                quarter_end = datetime(year, month, calendar.monthrange(year, month)[1])
                if first_date <= quarter_end <= last_date:
                    markers.append((quarter_end, f"{str(year)[2:]}Q{month // 3}"))
        return markers

    @staticmethod
    def _axis_money(value: float, currency: str) -> str:
        decimals = 2 if abs(value) < 20 else 1 if abs(value) < 1000 else 0
        return PremiumOnePagerRenderer._money(value, currency, decimals=decimals)

    def _valuation_summary_band(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, data: dict[str, Any]) -> None:
        pdf.setFillColor(BLUE_LIGHT)
        pdf.setStrokeColor(colors.HexColor("#C9DFF0"))
        pdf.roundRect(x, y, w, h, 5, fill=1, stroke=1)
        slot = w / 3
        pdf.line(x + slot, y + 8, x + slot, y + h - 8)
        pdf.line(x + 2 * slot, y + 8, x + 2 * slot, y + h - 8)
        analyst_text = f"{data['analyst_count']} analistas" if data.get("analyst_count") else "cobertura pública"
        summaries = (
            ("NOSSO TP", self._money(data["c3po_tp"], data["currency"]), f"{data['upside_percent']:+.1f}% upside", BLUE),
            ("CONSENSO", self._money(data.get("consensus_tp"), data["currency"]), analyst_text, INK),
            ("BUY-IN", self._money(data["buy_in"], data["currency"]), "entrada disciplinada", AMBER),
        )
        for index, (label, value, sub, color) in enumerate(summaries):
            center = x + slot * (index + 0.5)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 5.0)
            pdf.drawCentredString(center, y + h - 9, label)
            pdf.setFillColor(color)
            pdf.setFont("Helvetica-Bold", 8.6)
            pdf.drawCentredString(center, y + 13, value)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 4.6)
            pdf.drawCentredString(center, y + 4, sub)

    def _bullet_box(
        self,
        pdf: canvas.Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        bullets: list[str],
        *,
        accent=GOLD,
        fill=WHITE,
    ) -> None:
        self._rounded_box(pdf, x, y, w, h, fill=fill)
        self._section_title(pdf, title, x + 11, y + h - 20, w - 22, accent)
        top = y + h - 31
        floor = y + 7
        for bullet in bullets:
            paragraph = Paragraph(f"- {escape(str(bullet))}", self.styles["bullet"])
            _, used = paragraph.wrap(w - 25, max(top - floor, 1))
            if top - used < floor:
                break
            paragraph.drawOn(pdf, x + 13, top - used)
            top -= used + 0.5

    def _scenario_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, data: dict[str, Any]) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, "Cenários de preço-alvo", x + 11, y + h - 20, w - 22, GOLD)
        scenario_colors = (
            (RED, RED_LIGHT, colors.HexColor("#F2B8B5")),
            (BLUE, BLUE_LIGHT, colors.HexColor("#A9D3EE")),
            (GREEN, GREEN_LIGHT, colors.HexColor("#A9D9C4")),
        )
        cards_x = x + 12
        cards_y = y + 67
        cards_w = w - 24
        gap = 6
        card_w = (cards_w - 2 * gap) / 3
        for index, scenario in enumerate(data["scenarios"]):
            label, value = scenario
            color, fill, stroke = scenario_colors[index]
            card_x = cards_x + index * (card_w + gap)
            pdf.setFillColor(fill)
            pdf.setStrokeColor(stroke)
            pdf.setLineWidth(0.9 if label == "BASE" else 0.6)
            pdf.roundRect(card_x, cards_y, card_w, 54, 4, fill=1, stroke=1)
            center = card_x + card_w / 2
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 5.8)
            pdf.drawCentredString(center, cards_y + 40, label)
            pdf.setFillColor(color)
            pdf.setFont("Helvetica-Bold", 10.5)
            pdf.drawCentredString(center, cards_y + 21, self._money(value, data["currency"], decimals=0))
            pdf.setFont("Helvetica-Bold", 6.4)
            pdf.drawCentredString(center, cards_y + 8, f"{(value / data['price'] - 1) * 100:+.0f}%")
        self._multiples_band(pdf, x + 12, y + 8, w - 24, 49, data)

    def _multiples_band(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, data: dict[str, Any]) -> None:
        label_w = 61
        pdf.setFillColor(LIGHT)
        pdf.setStrokeColor(BORDER)
        pdf.setLineWidth(0.7)
        pdf.roundRect(x, y, w, h, 4, fill=1, stroke=1)
        pdf.setFillColor(INK)
        pdf.roundRect(x, y, label_w, h, 4, fill=1, stroke=0)
        pdf.rect(x + label_w - 4, y, 4, h, fill=1, stroke=0)
        pdf.setFillColor(WHITE)
        pdf.setFont("Helvetica-Bold", 6.2)
        pdf.drawCentredString(x + label_w / 2, y + 30, "MÚLTIPLOS")
        pdf.setFillColor(colors.HexColor("#CAD1D8"))
        pdf.setFont("Helvetica", 5.2)
        pdf.drawCentredString(x + label_w / 2, y + 16, "PREÇO-BASE")
        pdf.setFont("Helvetica-Bold", 5.5)
        pdf.drawCentredString(x + label_w / 2, y + 7, self._money(data["price"], data["currency"]))

        metrics = list(data["multiples"].items())
        slot = (w - label_w) / 4
        for index, (label, value) in enumerate(metrics[:4]):
            xx = x + label_w + index * slot
            if index:
                pdf.setStrokeColor(BORDER)
                pdf.line(xx, y + 7, xx, y + h - 7)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 4.7)
            pdf.drawCentredString(xx + slot / 2, y + 31, label)
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 8.5)
            display = "N/D" if value is None else f"{value:.1f}x".replace(".", ",")
            pdf.drawCentredString(xx + slot / 2, y + 13, display)

    def _footer(self, pdf: canvas.Canvas, data: dict[str, Any], generated_at: datetime) -> None:
        pdf.setStrokeColor(BORDER)
        pdf.line(MARGIN, 72, PAGE_W - MARGIN, 72)
        footer = (
            f"<b>Fontes:</b> {data['source']}; demonstrações financeiras, estimativas de EPS e receita, consenso e cotações disponíveis nos provedores. "
            "<b>Metodologia:</b> média aritmética de cinco abordagens proprietárias inspiradas em valuation relativo, DCF, risco macro, lucros e construção de portfólio; horizonte de 12 meses. "
            f"Confiança {data['confidence']:.0f}/100 e dispersão entre métodos de {data['dispersion']:.1f}%. Material informativo; não constitui recomendação individual de investimento."
        )
        paragraph = Paragraph(footer, self.styles["small"])
        _, used = paragraph.wrap(PAGE_W - 2 * MARGIN, 30)
        paragraph.drawOn(pdf, MARGIN, 66 - used)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica", 5.8)
        pdf.drawRightString(PAGE_W - MARGIN, 13, f"Atualizado em {generated_at:%d/%m/%Y %H:%M} | Horizonte: 12 meses")

    @staticmethod
    def _rounded_box(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fill=WHITE, stroke=BORDER) -> None:
        pdf.setFillColor(fill)
        pdf.setStrokeColor(stroke)
        pdf.setLineWidth(0.7)
        pdf.roundRect(x, y, w, h, 6, fill=1, stroke=1)

    @staticmethod
    def _section_title(pdf: canvas.Canvas, title: str, x: float, y: float, w: float, accent=GOLD) -> None:
        pdf.setFillColor(accent)
        pdf.rect(x, y - 1, 3, 12, fill=1, stroke=0)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawString(x + 8, y + 1, title.upper())
        pdf.setStrokeColor(BORDER)
        pdf.setLineWidth(0.5)
        pdf.line(x + 8, y - 3, x + w, y - 3)

    @staticmethod
    def _kpi(
        pdf: canvas.Canvas,
        x: float,
        y: float,
        w: float,
        label: str,
        value: str,
        sub: str,
        *,
        fill=LIGHT,
        value_color=INK,
    ) -> None:
        PremiumOnePagerRenderer._rounded_box(pdf, x, y, w, 45, fill=fill)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica-Bold", 6.2)
        pdf.drawString(x + 9, y + 32, label.upper())
        pdf.setFillColor(value_color)
        pdf.setFont("Helvetica-Bold", PremiumOnePagerRenderer._fit_font(value, "Helvetica-Bold", 15.5, 10.5, w - 18))
        pdf.drawString(x + 9, y + 14, value)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica", 5.8)
        pdf.drawRightString(x + w - 8, y + 7, sub[:34])

    @staticmethod
    def _fit_font(text: str, font: str, maximum: float, minimum: float, width: float) -> float:
        from reportlab.pdfbase.pdfmetrics import stringWidth

        size = maximum
        while size > minimum and stringWidth(text, font, size) > width:
            size -= 0.5
        return size

    @staticmethod
    def _money(value: float | None, currency: str, *, decimals: int = 2) -> str:
        if value is None:
            return "N/D"
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        formatted = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{prefix} {formatted}"

    @staticmethod
    def _plain_money(value: float, currency: str) -> str:
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{prefix} {formatted}"

    @staticmethod
    def _signed(value: Any) -> str:
        try:
            return f"{float(value):+.2f}%".replace(".", ",")
        except (TypeError, ValueError):
            return "variação N/D"
