from __future__ import annotations

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
BROWN = colors.HexColor("#6B4A2B")
WHITE = colors.white


class ChewieFundamentalsPdfRenderer:
    """Company fundamentals sheet in the same editorial standard as the
    premium One Pager: dark masthead, KPI cards, metric boxes and sourcing."""

    def __init__(self) -> None:
        self.styles = {
            "body": ParagraphStyle(
                "body", fontName="Helvetica", fontSize=6.8, leading=8.6,
                textColor=INK, alignment=TA_JUSTIFY, spaceAfter=0,
            ),
            "small": ParagraphStyle(
                "small", fontName="Helvetica", fontSize=5.65, leading=6.75,
                textColor=SUB, alignment=TA_JUSTIFY, spaceAfter=0,
            ),
        }

    # ------------------------------------------------------------------ render

    def render(self, path: Path, payload: dict[str, Any], generated_at: datetime) -> None:
        fundamentals = payload["fundamentals"]
        item = payload["item"]
        pdf = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
        pdf.setTitle(f"{payload['symbol']} Fundamentals | Chewie | C3PO")

        self._header(pdf, payload)

        col_w = 258.0
        left_x = MARGIN
        mid_x = left_x + col_w + 10
        right_x = mid_x + col_w + 10
        right_w = PAGE_W - MARGIN - right_x

        self._metric_box(pdf, left_x, 350, col_w, 154, "Múltiplos", [
            ("P/L (trailing)", self._multiple(item["multiples"]["pe"])),
            ("P/L (forward)", self._multiple(item["multiples"]["forward_pe"])),
            ("EV/EBITDA", self._multiple(item["multiples"]["ev_ebitda"])),
            ("PEG", self._multiple(item["multiples"]["peg"])),
            ("P/VP", self._multiple(item["multiples"]["price_to_book"])),
            ("Dividend yield", self._percent(item["multiples"]["dividend_yield_percent"])),
        ], accent=GOLD)

        self._metric_box(pdf, left_x, 212, col_w, 128, "Rentabilidade", [
            ("ROE", self._percent(item["profitability"]["roe_percent"])),
            ("ROA", self._percent(item["profitability"]["roa_percent"])),
            ("Margem líquida", self._percent(item["profitability"]["profit_margin_percent"])),
            ("Margem operacional", self._percent(item["profitability"]["operating_margin_percent"])),
            ("Margem EBITDA", self._percent(item["profitability"]["ebitda_margin_percent"])),
        ], accent=GREEN)

        self._metric_box(pdf, left_x, 91, col_w, 111, "Endividamento & liquidez", [
            ("Dívida / patrimônio", self._multiple(item["leverage"]["debt_to_equity"])),
            ("Dívida líq. / EBITDA", self._multiple(item["leverage"]["net_debt_to_ebitda"])),
            ("Caixa total", self._compact_money(item["leverage"]["total_cash"], payload["currency"])),
            ("Dívida total", self._compact_money(item["leverage"]["total_debt"], payload["currency"])),
        ], accent=RED)

        self._metric_box(pdf, mid_x, 404, col_w, 100, "Crescimento", [
            ("Receita (YoY)", self._signed_percent(item["growth"]["revenue_growth_percent"])),
            ("Lucro (YoY)", self._signed_percent(item["growth"]["earnings_growth_percent"])),
            ("EPS trailing → forward", self._eps_pair(fundamentals, payload["currency"])),
        ], accent=BLUE)

        self._consensus_box(pdf, mid_x, 224, col_w, 170, payload)
        self._description_box(pdf, mid_x, 91, col_w, 123, fundamentals)

        self._quarters_box(pdf, right_x, 344, right_w, 160, fundamentals, payload["currency"])
        self._range_box(pdf, right_x, 224, right_w, 110, fundamentals, payload)
        self._sources_box(pdf, right_x, 91, right_w, 123, payload)

        self._footer(pdf, payload, generated_at)
        pdf.showPage()
        pdf.save()

    # ------------------------------------------------------------------ blocks

    def _header(self, pdf: canvas.Canvas, payload: dict[str, Any]) -> None:
        fundamentals = payload["fundamentals"]
        item = payload["item"]
        pdf.setFillColor(INK)
        pdf.rect(0, PAGE_H - 78, PAGE_W, 78, fill=1, stroke=0)
        pdf.setFillColor(GOLD)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(MARGIN, PAGE_H - 21, "C3PO EQUITY INTELLIGENCE | CHEWIE FUNDAMENTALS")
        pdf.setFillColor(WHITE)
        title = f"{payload['symbol']} | {str(item['name']).upper()}"
        pdf.setFont("Helvetica-Bold", self._fit_font(title, "Helvetica-Bold", 26, 15, 420))
        pdf.drawString(MARGIN, PAGE_H - 50, title)
        pdf.setFillColor(colors.HexColor("#CAD1D8"))
        pdf.setFont("Helvetica", 7.5)
        subtitle = " · ".join(filter(None, [
            str(item.get("sector") or ""),
            str(fundamentals.get("industry") or ""),
            str(payload["market"]),
            f"dados de {item.get('fundamentals_as_of')}" if item.get("fundamentals_as_of") else "",
        ]))
        pdf.drawString(MARGIN, PAGE_H - 66, subtitle[:120])

        card_y = PAGE_H - 65
        price = (payload.get("price") or {}).get("price")
        change = (payload.get("price") or {}).get("change_percent")
        self._kpi(
            pdf, 470, card_y, 105, "Preço",
            self._money(price, payload["currency"]) if price is not None else "N/D",
            self._signed_percent(change) if change is not None else "cotação recente",
            fill=WHITE,
        )
        self._kpi(
            pdf, 582, card_y, 105, "Market cap",
            self._compact_money(item.get("market_cap"), payload["currency"]),
            "valor de mercado", fill=GOLD_LIGHT,
        )
        roe = item["profitability"]["roe_percent"]
        self._kpi(
            pdf, 694, card_y, 123, "ROE",
            self._percent(roe),
            f"P/L {self._multiple(item['multiples']['pe'])}",
            fill=GREEN_LIGHT if (roe or 0) >= 0 else RED_LIGHT,
            value_color=GREEN if (roe or 0) >= 0 else RED,
        )

    def _metric_box(
        self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float,
        title: str, rows: list[tuple[str, str]], *, accent=GOLD,
    ) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, title, x + 11, y + h - 20, w - 22, accent=accent)
        row_y = y + h - 40
        for index, (label, value) in enumerate(rows):
            if index % 2:
                pdf.setFillColor(colors.HexColor("#FAFBFC"))
                pdf.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.9)
            pdf.drawString(x + 12, row_y, label)
            pdf.setFillColor(RED if value.startswith("-") else INK)
            pdf.setFont("Helvetica-Bold", 7.2)
            pdf.drawRightString(x + w - 12, row_y, value)
            row_y -= 18

    def _consensus_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, payload: dict[str, Any]) -> None:
        fundamentals = payload["fundamentals"]
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, "Consenso de mercado", x + 11, y + h - 20, w - 22, accent=BLUE)
        rows: list[tuple[str, str]] = []
        consensus = payload.get("fmp_consensus")
        if consensus:
            rows.append(("TP consenso (FMP)", self._money(consensus.get("consensus"), payload["currency"])))
            band_low, band_high = consensus.get("low"), consensus.get("high")
            if band_low is not None and band_high is not None:
                rows.append(("Banda analistas", f"{self._money(band_low, payload['currency'])} – {self._money(band_high, payload['currency'])}"))
        target = fundamentals.get("targetMeanPrice")
        if target:
            rows.append(("TP médio (EODHD)", self._money(target, payload["currency"])))
        ratings = fundamentals.get("analystRatings") or {}
        buy = int(ratings.get("strongBuy") or 0) + int(ratings.get("buy") or 0)
        hold = int(ratings.get("hold") or 0)
        sell = int(ratings.get("sell") or 0) + int(ratings.get("strongSell") or 0)
        if buy + hold + sell:
            rows.append(("Recomendações", f"{buy} compra · {hold} manter · {sell} venda"))
        analysts = fundamentals.get("numberOfAnalystOpinions")
        if analysts:
            rows.append(("Analistas cobrindo", str(int(analysts))))
        sentiment = payload.get("news_sentiment")
        if sentiment:
            rows.append((
                "Sentimento de notícias",
                f"{sentiment['bullish_percent']:.0f}% bullish · {sentiment['articles_last_week']} artigos/7d",
            ))
        if not rows:
            rows = [("Cobertura", "sem consenso público disponível")]
        row_y = y + h - 40
        for index, (label, value) in enumerate(rows[:7]):
            if index % 2:
                pdf.setFillColor(colors.HexColor("#FAFBFC"))
                pdf.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.7)
            pdf.drawString(x + 12, row_y, label)
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 6.9)
            pdf.drawRightString(x + w - 12, row_y, value[:40])
            row_y -= 18

    def _description_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fundamentals: dict[str, Any]) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, "Sobre a empresa", x + 11, y + h - 20, w - 22, accent=BROWN)
        description = str(fundamentals.get("description") or "Descrição indisponível na fonte.")
        if len(description) > 620:
            description = description[:617].rsplit(" ", 1)[0] + "…"
        paragraph = Paragraph(escape(description), self.styles["body"])
        _, used = paragraph.wrap(w - 24, h - 34)
        paragraph.drawOn(pdf, x + 12, y + h - 32 - used)

    def _quarters_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fundamentals: dict[str, Any], currency: str) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, "Resultados trimestrais", x + 11, y + h - 20, w - 22)
        columns = [x + 12, x + 96, x + 158, x + 214]
        header_y = y + h - 42
        pdf.setFillColor(LIGHT)
        pdf.rect(x + 9, header_y - 4, w - 18, 15, fill=1, stroke=0)
        for column, text in zip(columns, ("Trimestre", "Receita", "Lucro líq.", "EBITDA")):
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica-Bold", 6.2)
            pdf.drawString(column, header_y, text.upper())
        rows = [row for row in (fundamentals.get("quarterlyIncome") or []) if isinstance(row, dict)][:5]
        row_y = header_y - 16
        for index, row in enumerate(rows):
            if index % 2:
                pdf.setFillColor(colors.HexColor("#FAFBFC"))
                pdf.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
            values = (
                str(row.get("date") or "")[:10],
                self._compact_money(self._num(row.get("totalRevenue")), currency),
                self._compact_money(self._num(row.get("netIncome")), currency),
                self._compact_money(self._num(row.get("ebitda")), currency),
            )
            for column, text in zip(columns, values):
                pdf.setFillColor(INK)
                pdf.setFont("Helvetica" if column == columns[0] else "Helvetica-Bold", 6.6)
                pdf.drawString(column, row_y, text)
            row_y -= 17
        if not rows:
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.8)
            pdf.drawString(x + 12, header_y - 18, "Demonstrações trimestrais indisponíveis na fonte.")

    def _range_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fundamentals: dict[str, Any], payload: dict[str, Any]) -> None:
        self._rounded_box(pdf, x, y, w, h)
        self._section_title(pdf, "Faixa de 52 semanas", x + 11, y + h - 20, w - 22, accent=BLUE)
        low = self._num(fundamentals.get("technical52WeekLow"))
        high = self._num(fundamentals.get("technical52WeekHigh"))
        price = (payload.get("price") or {}).get("price")
        track_y = y + h - 52
        track_x = x + 18
        track_w = w - 36
        if low is not None and high is not None and high > low:
            pdf.setFillColor(LIGHT)
            pdf.roundRect(track_x, track_y, track_w, 7, 3.5, fill=1, stroke=0)
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.0)
            pdf.drawString(track_x, track_y - 11, self._money(low, payload["currency"]))
            pdf.drawRightString(track_x + track_w, track_y - 11, self._money(high, payload["currency"]))
            if price is not None and low <= price <= high:
                position = track_x + (price - low) / (high - low) * track_w
                pdf.setFillColor(BLUE)
                pdf.circle(position, track_y + 3.5, 4.2, fill=1, stroke=0)
                pdf.setFont("Helvetica-Bold", 6.4)
                pdf.drawCentredString(position, track_y + 12, self._money(price, payload["currency"]))
        else:
            pdf.setFillColor(SUB)
            pdf.setFont("Helvetica", 6.8)
            pdf.drawString(x + 12, track_y, "Faixa de 52 semanas indisponível na fonte.")
        ma_y = y + 16
        ma50 = self._num(fundamentals.get("movingAverage50Day"))
        ma200 = self._num(fundamentals.get("movingAverage200Day"))
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica", 6.4)
        pdf.drawString(x + 12, ma_y, f"MM 50d: {self._money(ma50, payload['currency']) if ma50 else 'N/D'}")
        pdf.drawRightString(x + w - 12, ma_y, f"MM 200d: {self._money(ma200, payload['currency']) if ma200 else 'N/D'}")

    def _sources_box(self, pdf: canvas.Canvas, x: float, y: float, w: float, h: float, payload: dict[str, Any]) -> None:
        self._rounded_box(pdf, x, y, w, h, fill=GOLD_LIGHT)
        self._section_title(pdf, "Fontes & procedência", x + 11, y + h - 20, w - 22)
        lines = ["• EODHD Fundamentals: demonstrações, múltiplos, técnicos e ratings."]
        if payload["market"] == "B3":
            lines.append("• Blend do screener noturno: Brapi + EODHD cross-validados, com overlay oficial CVM/RI quando publicado.")
        else:
            lines.append("• Blend do screener noturno: múltiplos validados no ciclo canônico diário.")
        if payload.get("fmp_consensus"):
            lines.append("• FMP: consenso de preço-alvo dos analistas.")
        if payload.get("news_sentiment"):
            lines.append("• Finnhub: sentimento agregado de notícias.")
        lines.append("• Massive/EODHD intraday não participam: fundamentos apenas.")
        paragraph = Paragraph("<br/>".join(escape(line) for line in lines), self.styles["small"])
        _, used = paragraph.wrap(w - 24, h - 34)
        paragraph.drawOn(pdf, x + 12, y + h - 32 - used)

    def _footer(self, pdf: canvas.Canvas, payload: dict[str, Any], generated_at: datetime) -> None:
        pdf.setStrokeColor(BORDER)
        pdf.line(MARGIN, 72, PAGE_W - MARGIN, 72)
        footer = (
            "<b>Chewie Fundamentals</b> é uma leitura descritiva dos fundamentos reportados e do consenso público. "
            "Não contém preço-alvo proprietário C3PO, não alimenta screening nem decisões de trading, e não constitui recomendação individual de investimento. "
            "Números conforme reportados pelas fontes; períodos podem diferir entre provedores."
        )
        paragraph = Paragraph(footer, self.styles["small"])
        _, used = paragraph.wrap(PAGE_W - 2 * MARGIN, 30)
        paragraph.drawOn(pdf, MARGIN, 66 - used)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica", 5.8)
        pdf.drawRightString(
            PAGE_W - MARGIN, 13,
            f"Gerado em {generated_at:%d/%m/%Y %H:%M} UTC | {payload['symbol']} · {payload['market']}",
        )

    # ------------------------------------------------------------------ helpers

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
        pdf: canvas.Canvas, x: float, y: float, w: float,
        label: str, value: str, sub: str, *, fill=LIGHT, value_color=INK,
    ) -> None:
        ChewieFundamentalsPdfRenderer._rounded_box(pdf, x, y, w, 45, fill=fill)
        pdf.setFillColor(SUB)
        pdf.setFont("Helvetica-Bold", 6.2)
        pdf.drawString(x + 9, y + 32, label.upper())
        pdf.setFillColor(value_color)
        pdf.setFont("Helvetica-Bold", ChewieFundamentalsPdfRenderer._fit_font(value, "Helvetica-Bold", 15.5, 9.5, w - 18))
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
    def _num(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else None

    @staticmethod
    def _multiple(value: float | None) -> str:
        return "N/M" if value is None else f"{value:.1f}x".replace(".", ",")

    @staticmethod
    def _percent(value: float | None) -> str:
        return "N/D" if value is None else f"{value:.1f}%".replace(".", ",")

    @staticmethod
    def _signed_percent(value: float | None) -> str:
        return "N/D" if value is None else f"{value:+.1f}%".replace(".", ",")

    @staticmethod
    def _money(value: float | None, currency: str, *, decimals: int = 2) -> str:
        if value is None:
            return "N/D"
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        formatted = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{prefix} {formatted}"

    @classmethod
    def _compact_money(cls, value: float | None, currency: str) -> str:
        if value is None:
            return "N/D"
        prefix = "R$" if currency == "BRL" else "US$" if currency == "USD" else currency
        magnitude = abs(value)
        if magnitude >= 1e12:
            return f"{prefix} {value / 1e12:.2f} tri".replace(".", ",")
        if magnitude >= 1e9:
            return f"{prefix} {value / 1e9:.2f} bi".replace(".", ",")
        if magnitude >= 1e6:
            return f"{prefix} {value / 1e6:.1f} mi".replace(".", ",")
        return cls._money(value, currency, decimals=0)

    def _eps_pair(self, fundamentals: dict[str, Any], currency: str) -> str:
        trailing = self._num(fundamentals.get("trailingEps"))
        forward = self._num(fundamentals.get("forwardEps"))
        if trailing is None and forward is None:
            return "N/D"
        left = self._money(trailing, currency) if trailing is not None else "N/D"
        right = self._money(forward, currency) if forward is not None else "N/D"
        return f"{left} → {right}"
