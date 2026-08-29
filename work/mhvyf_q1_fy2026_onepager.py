#!/usr/bin/env python3
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


OUT = Path("outputs/mhvyf-one-pager-q1-fy2026-usd.pdf")

PAGE_W, PAGE_H = landscape(A4)
M = 8 * mm

INK = colors.HexColor("#111827")
SUB = colors.HexColor("#59636E")
LIGHT = colors.HexColor("#F5F7F9")
BORDER = colors.HexColor("#D9E0E7")
MHI_RED = colors.HexColor("#D71920")
RED_LIGHT = colors.HexColor("#FFF0F1")
BLUE = colors.HexColor("#1473E6")
BLUE_LIGHT = colors.HexColor("#EAF3FF")
GREEN = colors.HexColor("#087A55")
GREEN_LIGHT = colors.HexColor("#E9F7F0")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#D97706")
WHITE = colors.white

# Primary Tokyo listing converted at the report's USD/JPY reference rate.
fx_usdjpy = 156.70
price = 4091.00 / fx_usdjpy
day_change = 7.69
consensus = 5335.58 / fx_usdjpy
consensus_analysts = 16

# Internal five-method framework, registered in the repository on 17/08/2026.
valuation_methods = [
    ("Múltiplos de Lucro + EV/EBITDA", 5250.0 / fx_usdjpy),
    ("Fluxo de Caixa Descontado", 5600.0 / fx_usdjpy),
    ("Blend Ajustado ao Risco", 4750.0 / fx_usdjpy),
    ("Momentum de Lucro", 5950.0 / fx_usdjpy),
    ("Qualidade & Fluxo de Caixa", 5650.0 / fx_usdjpy),
]
target = sum(value for _, value in valuation_methods) / len(valuation_methods)
buy_in = 3110.0 / fx_usdjpy
upside = (target / price - 1.0) * 100.0

styles = {
    "body": ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=7.15,
        leading=9.0,
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
        fontSize=6.75,
        leading=8.25,
        textColor=INK,
        leftIndent=7,
        firstLineIndent=-7,
        alignment=TA_JUSTIFY,
        spaceAfter=1.4,
    ),
    "right": ParagraphStyle(
        "right",
        fontName="Helvetica",
        fontSize=7.0,
        leading=8.5,
        textColor=INK,
        alignment=TA_RIGHT,
    ),
}


def para(c, text, x, top, width, style="body", max_height=200):
    p = Paragraph(text, styles[style])
    _, h = p.wrap(width, max_height)
    p.drawOn(c, x, top - h)
    return h


def rounded_box(c, x, y, w, h, fill=WHITE, stroke=BORDER, radius=6):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def section_title(c, title, x, y, w, accent=MHI_RED):
    c.setFillColor(accent)
    c.rect(x, y - 1, 3, 12, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x + 8, y + 1, title.upper())
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(x + 8, y - 3, x + w, y - 3)


def kpi(c, x, y, w, label, value, sub, fill=LIGHT, value_color=INK):
    rounded_box(c, x, y, w, 45, fill=fill)
    c.setFillColor(SUB)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawString(x + 9, y + 32, label.upper())
    c.setFillColor(value_color)
    c.setFont("Helvetica-Bold", 16.2)
    c.drawString(x + 9, y + 14, value)
    c.setFillColor(SUB)
    c.setFont("Helvetica", 5.9)
    c.drawRightString(x + w - 8, y + 7, sub)


def metric_table(c, x, y, w, h):
    rounded_box(c, x, y, w, h)
    section_title(c, "1T FY2026 - desempenho consolidado", x + 11, y + h - 20, w - 22)
    columns = [x + 12, x + 176, x + 271, x + 359]
    header_y = y + h - 46
    c.setFillColor(LIGHT)
    c.rect(x + 9, header_y - 4, w - 18, 16, fill=1, stroke=0)
    for i, text in enumerate(("Métrica", "1T FY2026", "1T FY2025", "YoY / delta")):
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawString(columns[i], header_y + 1, text.upper())

    rows = [
        ("Pedidos recebidos", "US$ 12,91 bi", "US$ 10,27 bi", "+25,7%"),
        ("Receita", "US$ 7,62 bi", "US$ 6,60 bi", "+15,5%"),
        ("Lucro de negócios", "US$ 1,02 bi", "US$ 0,62 bi", "+65,0%"),
        ("Margem de negócios", "13,4%", "9,4%", "+4,0 p.p."),
        ("Lucro líquido atribuível", "US$ 0,86 bi", "US$ 0,44 bi", "+97,4%"),
        ("Guidance lucro FY2026", "US$ 3,45 bi", "US$ 2,76 bi FY25", "+24,9%"),
    ]
    row_y = header_y - 14
    for idx, row in enumerate(rows):
        if idx % 2:
            c.setFillColor(colors.HexColor("#FAFBFC"))
            c.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
        for i, text in enumerate(row):
            c.setFillColor(GREEN if i == 3 else INK)
            c.setFont("Helvetica-Bold" if i in (0, 3) else "Helvetica", 7.0)
            c.drawString(columns[i], row_y, text)
        row_y -= 17


def valuation_table(c, x, y, w, h):
    rounded_box(c, x, y, w, h, fill=colors.HexColor("#FBFCFE"))
    section_title(c, "Valuation - cinco metodologias", x + 11, y + h - 20, w - 22, BLUE)
    c.setFillColor(SUB)
    c.setFont("Helvetica-Oblique", 4.6)
    c.drawRightString(x + w - 11, y + h - 16.5, "estimativas internas registradas em 17/08/2026")

    c.setFillColor(LIGHT)
    c.rect(x + 9, y + h - 52, w - 18, 17, fill=1, stroke=0)
    for text, xpos in (("Modelo", x + 12), ("TP", x + 145), ("Upside", x + w - 60)):
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawString(xpos, y + h - 46, text.upper())

    yy = y + h - 69
    method_values = [value for _, value in valuation_methods]
    highest = max(method_values)
    lowest = min(method_values)
    for idx, (name, value) in enumerate(valuation_methods):
        if idx % 2:
            c.setFillColor(WHITE)
            c.rect(x + 9, yy - 5, w - 18, 18, fill=1, stroke=0)
        value_color = GREEN if value == highest else RED if value == lowest else INK
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.9)
        c.drawString(x + 12, yy, name)
        c.setFillColor(value_color)
        c.setFont("Helvetica-Bold", 7.0)
        c.drawRightString(x + 190, yy, f"US$ {value:.2f}")
        c.setFillColor(GREEN if value >= price else RED)
        c.drawRightString(x + w - 12, yy, f"{(value / price - 1) * 100:+.1f}%")
        yy -= 19

    c.setStrokeColor(BORDER)
    c.line(x + 10, yy + 8, x + w - 10, yy + 8)

    band_x = x + 10
    band_y = y + 12
    band_w = w - 20
    band_h = 58
    c.setFillColor(BLUE_LIGHT)
    c.setStrokeColor(colors.HexColor("#C9DFF0"))
    c.roundRect(band_x, band_y, band_w, band_h, 5, fill=1, stroke=1)
    slot = band_w / 3
    c.line(band_x + slot, band_y + 8, band_x + slot, band_y + band_h - 8)
    c.line(band_x + 2 * slot, band_y + 8, band_x + 2 * slot, band_y + band_h - 8)

    summaries = [
        ("NOSSO TP", f"US$ {target:.2f}", f"+{upside:.1f}% upside", BLUE),
        ("CONSENSO", f"US$ {consensus:.2f}", f"{consensus_analysts} analistas", INK),
        ("BUY-IN", f"US$ {buy_in:.2f}", "entrada disciplinada", AMBER),
    ]
    for idx, (label, value, sub, color) in enumerate(summaries):
        center = band_x + slot * (idx + 0.5)
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 5.8)
        c.drawCentredString(center, band_y + 43, label)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 11.1)
        c.drawCentredString(center, band_y + 24, value)
        c.setFillColor(SUB)
        c.setFont("Helvetica", 5.4)
        c.drawCentredString(center, band_y + 9, sub)


def bullet_box(c, x, y, w, h, title, bullets, accent=MHI_RED, fill=WHITE):
    rounded_box(c, x, y, w, h, fill=fill)
    section_title(c, title, x + 11, y + h - 20, w - 22, accent)
    top = y + h - 31
    for bullet in bullets:
        used = para(c, f"- {bullet}", x + 13, top, w - 25, "bullet", 70)
        top -= used + 0.4


def scenario_box(c, x, y, w, h):
    rounded_box(c, x, y, w, h, fill=WHITE, stroke=BORDER)
    section_title(c, "Cenários de preço-alvo", x + 11, y + h - 20, w - 22, MHI_RED)
    scenarios = [
        ("BEAR", f"US$ {3400 / fx_usdjpy:.2f}", f"{((3400 / fx_usdjpy) / price - 1) * 100:+.0f}%", RED, RED_LIGHT, colors.HexColor("#F2B8B5")),
        ("BASE", f"US$ {target:.2f}", f"+{upside:.0f}%", BLUE, BLUE_LIGHT, colors.HexColor("#A9D3EE")),
        ("BULL", f"US$ {6400 / fx_usdjpy:.2f}", f"+{((6400 / fx_usdjpy) / price - 1) * 100:.0f}%", GREEN, GREEN_LIGHT, colors.HexColor("#A9D9C4")),
    ]
    cards_x = x + 12
    cards_y = y + 67
    cards_w = w - 24
    gap = 6
    card_w = (cards_w - 2 * gap) / 3
    for idx, (label, value, move, color, fill, stroke) in enumerate(scenarios):
        card_x = cards_x + idx * (card_w + gap)
        c.setFillColor(fill)
        c.setStrokeColor(stroke)
        c.setLineWidth(0.9 if label == "BASE" else 0.6)
        c.roundRect(card_x, cards_y, card_w, 54, 4, fill=1, stroke=1)
        center = card_x + card_w / 2
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 5.8)
        c.drawCentredString(center, cards_y + 40, label)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 10.2)
        c.drawCentredString(center, cards_y + 21, value)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawCentredString(center, cards_y + 8, move)

    multiples = [
        ("P/E REPORTADO", "41,4x"),
        ("FWRD P/E", "31,6x"),
        ("EV/EBITDA", "19,5x"),
        ("PEG RATIO", "1,73x"),
    ]
    band_x = x + 12
    band_y = y + 8
    band_w = w - 24
    band_h = 49
    label_w = 61
    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.7)
    c.roundRect(band_x, band_y, band_w, band_h, 4, fill=1, stroke=1)
    c.setFillColor(INK)
    c.roundRect(band_x, band_y, label_w, band_h, 4, fill=1, stroke=0)
    c.rect(band_x + label_w - 4, band_y, 4, band_h, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(band_x + label_w / 2, band_y + 30, "MÚLTIPLOS")
    c.setFillColor(colors.HexColor("#CAD1D8"))
    c.setFont("Helvetica", 5.2)
    c.drawCentredString(band_x + label_w / 2, band_y + 16, "PREÇO-BASE")
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(band_x + label_w / 2, band_y + 7, f"US$ {price:.2f}")

    metrics_w = band_w - label_w
    slot = metrics_w / 4
    for idx, (label, value) in enumerate(multiples):
        xx = band_x + label_w + idx * slot
        if idx:
            c.setStrokeColor(BORDER)
            c.line(xx, band_y + 7, xx, band_y + band_h - 7)
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 4.7)
        c.drawCentredString(xx + slot / 2, band_y + 31, label)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.7)
        c.drawCentredString(xx + slot / 2, band_y + 13, value)


def draw():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("MHVYF One Pager - 1T FY2026")

    c.setFillColor(INK)
    c.rect(0, PAGE_H - 78, PAGE_W, 78, fill=1, stroke=0)
    c.setFillColor(MHI_RED)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, PAGE_H - 21, "EQUITY RESEARCH | EARNINGS UPDATE")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 18.5)
    c.drawString(M, PAGE_H - 50, "MHVYF / 7011 | MITSUBISHI HEAVY INDUSTRIES")
    c.setFillColor(colors.HexColor("#CAD1D8"))
    c.setFont("Helvetica", 7.8)
    c.drawString(M, PAGE_H - 66, "1T FY2026: pedidos +26%; lucro de negócios +65%; energia, defesa e infraestrutura de IA sustentam o ciclo")

    card_y = PAGE_H - 65
    kpi(c, 470, card_y, 105, "Preço convertido", f"US$ {price:.2f}", f"04/ago/26 | +{day_change:.2f}%", fill=WHITE)
    kpi(c, 582, card_y, 105, "Novo TP 12m", f"US$ {target:.2f}", "base case", fill=BLUE_LIGHT, value_color=BLUE)
    kpi(c, 694, card_y, 123, "Upside", f"+{upside:.0f}%", "rating: COMPRA", fill=GREEN_LIGHT, value_color=GREEN)

    left_x = M
    left_w = 520
    right_x = left_x + left_w + 10
    right_w = PAGE_W - M - right_x

    metric_table(c, left_x, 354, left_w, 150)
    valuation_table(c, right_x, 262, right_w, 242)

    bullet_box(
        c,
        left_x,
        234,
        252,
        110,
        "Leitura do trimestre",
        [
            "Pedidos atingiram US$ 12,91 bi, alta de 25,7%, ampliando a visibilidade sobre energia, defesa e sistemas de infraestrutura.",
            "Receita cresceu 15,5% e o lucro de negócios 65,0%; a margem avançou de 9,4% para 13,4%, sinalizando mix melhor e forte alavancagem operacional.",
            "O lucro líquido quase dobrou para US$ 0,86 bi. A ação reagiu +7,7% no pregão do resultado, mesmo após valorização estrutural relevante.",
        ],
        accent=GREEN,
    )
    bullet_box(
        c,
        left_x + 262,
        234,
        258,
        110,
        "Qualidade do lucro e caixa",
        [
            "O avanço de lucro foi muito superior ao crescimento da receita; isso confirma melhoria de execução, preços e composição do backlog, não apenas expansão de volume.",
            "A companhia encerrou FY2025 com caixa líquido de cerca de US$ 2,93 bi; o FCF TTM indicado por S&P Global foi US$ 4,86 bi, oferecendo proteção para capex e dividendos.",
            "A venda da Mitsubishi Logisnext altera a base comparável. A leitura deve priorizar negócios continuados e conversão de backlog em caixa recorrente.",
        ],
        accent=RED,
        fill=colors.HexColor("#FFFAFA"),
    )

    bullet_box(
        c,
        left_x,
        91,
        252,
        132,
        "Tese de investimento",
        [
            "GTCC, nuclear, serviços e soluções integradas de energia posicionam a MHI para o crescimento de demanda elétrica e a necessidade de estabilidade das redes.",
            "Defesa e espaço se beneficiam do maior orçamento japonês, de programas plurianuais e de contratos com elevada barreira tecnológica e visibilidade de entrega.",
            "A oferta de energia e resfriamento para data centers ganhou validação com o chiller de 10 MW nos EUA e a participação no ecossistema NVIDIA DSX.",
            "A aliança com Preferred Networks adiciona IA embarcada, manutenção preditiva e automação a ativos industriais e de segurança nacional já dominados pela MHI.",
        ],
        accent=BLUE,
    )
    bullet_box(
        c,
        left_x + 262,
        91,
        258,
        132,
        "Riscos e próximos gatilhos",
        [
            "O valuation já exige execução: P/E forward de 31,6x e EV/EBITDA de 19,5x deixam a ação sensível a atrasos, custos de projeto e normalização de margens.",
            "Guidance FY2026: pedidos de US$ 44,67 bi, receita de US$ 34,46 bi, lucro de negócios de US$ 3,45 bi e lucro líquido de US$ 2,42 bi.",
            "A premissa cambial é USD/JPY 150 e EUR/JPY 180. Iene mais forte reduz conversão de receitas externas e pode pressionar competitividade e margem.",
            "Monitorar backlog, margem por segmento, FCF, defesa, turbinas a gás e comercialização de data centers. MHVYF tem baixa liquidez; 7011.T é a referência correta.",
        ],
        accent=RED,
        fill=colors.HexColor("#FFFAFA"),
    )

    scenario_box(c, right_x, 91, right_w, 160)

    c.setStrokeColor(BORDER)
    c.line(M, 72, PAGE_W - M, 72)
    footer = (
        "<b>Fontes:</b> MHI Q1 FY2026 Financial Results (04/08/2026), FY2025 Financial Results e 2024 Medium-Term Business Plan; "
        "MHI releases sobre NVIDIA DSX e Preferred Networks; StockAnalysis/S&amp;P Global para preço, múltiplos, caixa e consenso. "
        "<b>Metodologia:</b> média de cinco estimativas internas registradas em 17/08/2026, horizonte de 12 meses. Valores convertidos de 7011.T pela taxa USD/JPY 156,70; MHVYF está sujeito a câmbio e liquidez OTC. "
        "Material informativo; não constitui recomendação individual de investimento."
    )
    para(c, footer, M, 66, PAGE_W - 2 * M, "small", 30)
    c.setFillColor(SUB)
    c.setFont("Helvetica", 5.8)
    c.drawRightString(PAGE_W - M, 13, "Atualizado em 04/08/2026 | Horizonte: 12 meses")

    c.showPage()
    c.save()
    print(OUT.resolve())


if __name__ == "__main__":
    draw()
