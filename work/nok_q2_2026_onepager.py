#!/usr/bin/env python3
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


OUT = Path("outputs/nok-one-pager-q2-2026.pdf")

PAGE_W, PAGE_H = landscape(A4)
M = 8 * mm

INK = colors.HexColor("#111827")
SUB = colors.HexColor("#59636E")
LIGHT = colors.HexColor("#F5F7F9")
BORDER = colors.HexColor("#D9E0E7")
BLUE = colors.HexColor("#0078D4")
BLUE_LIGHT = colors.HexColor("#EAF5FC")
GREEN = colors.HexColor("#087A55")
GREEN_LIGHT = colors.HexColor("#E9F7F0")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#D97706")
AMBER_LIGHT = colors.HexColor("#FFF6E5")
WHITE = colors.white

price = 9.14
consensus = 15.02
target = 14.00
buy_in = 7.78
upside = (target / price - 1.0) * 100.0

valuation_methods = [
    ("Goldman Sachs", 13.06),
    ("Morgan Stanley", 15.17),
    ("Bridgewater", 13.70),
    ("JPMorgan", 15.40),
    ("BlackRock", 12.64),
]

styles = {
    "body": ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=7.25,
        leading=9.25,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=0,
    ),
    "small": ParagraphStyle(
        "small",
        fontName="Helvetica",
        fontSize=6.0,
        leading=7.2,
        textColor=SUB,
        alignment=TA_JUSTIFY,
        spaceAfter=0,
    ),
    "bullet": ParagraphStyle(
        "bullet",
        fontName="Helvetica",
        fontSize=7.1,
        leading=8.8,
        textColor=INK,
        leftIndent=7,
        firstLineIndent=-7,
        alignment=TA_JUSTIFY,
        spaceAfter=2,
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


def section_title(c, title, x, y, w, accent=BLUE):
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
    c.setFont("Helvetica-Bold", 17)
    c.drawString(x + 9, y + 14, value)
    c.setFillColor(SUB)
    c.setFont("Helvetica", 6.1)
    c.drawRightString(x + w - 8, y + 7, sub)


def metric_table(c, x, y, w, h):
    rounded_box(c, x, y, w, h)
    section_title(c, "Q2 2026 - resultado reportado", x + 11, y + h - 20, w - 22)
    columns = [x + 12, x + 170, x + 254, x + 337]
    header_y = y + h - 46
    c.setFillColor(LIGHT)
    c.rect(x + 9, header_y - 4, w - 18, 16, fill=1, stroke=0)
    for i, text in enumerate(("Métrica", "Q2 2026", "Q2 2025", "YoY / delta")):
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawString(columns[i], header_y + 1, text.upper())

    rows = [
        ("Receita consolidada", "EUR 4,82 bi", "EUR 4,44 bi", "+8%"),
        ("Lucro operacional comparável", "EUR 434 mi", "EUR 367 mi", "+18%"),
        ("Margem operacional comparável", "9,0%", "8,3%", "+0,7 p.p."),
        ("EPS diluído comparável", "EUR 0,07", "EUR 0,04", "+75%"),
        ("Network Infrastructure", "EUR 2,04 bi", "EUR 1,83 bi", "+12%"),
        ("Vendas AI & Cloud", "EUR 446 mi", "EUR 220 mi", "+103%"),
    ]
    row_y = header_y - 14
    for idx, row in enumerate(rows):
        if idx % 2:
            c.setFillColor(colors.HexColor("#FAFBFC"))
            c.rect(x + 9, row_y - 5, w - 18, 16, fill=1, stroke=0)
        for i, text in enumerate(row):
            c.setFillColor(GREEN if i == 3 else INK)
            c.setFont("Helvetica-Bold" if i in (0, 3) else "Helvetica", 7.1)
            c.drawString(columns[i], row_y, text)
        row_y -= 17


def valuation_table(c, x, y, w, h):
    rounded_box(c, x, y, w, h, fill=colors.HexColor("#FBFCFE"))
    section_title(c, "Valuation - cinco metodologias", x + 11, y + h - 20, w - 22, BLUE)

    c.setFillColor(LIGHT)
    c.rect(x + 9, y + h - 52, w - 18, 17, fill=1, stroke=0)
    for text, xpos in (("Modelo", x + 12), ("TP", x + 145), ("Upside", x + w - 60)):
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 6.2)
        c.drawString(xpos, y + h - 46, text.upper())

    yy = y + h - 69
    for idx, (name, value) in enumerate(valuation_methods):
        if idx % 2:
            c.setFillColor(WHITE)
            c.rect(x + 9, yy - 5, w - 18, 18, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 6.9)
        c.drawString(x + 12, yy, name)
        c.setFont("Helvetica-Bold", 7.0)
        c.drawRightString(x + 190, yy, f"US$ {value:.2f}")
        c.setFillColor(GREEN)
        c.drawRightString(x + w - 12, yy, f"+{(value / price - 1) * 100:.1f}%")
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
    c.setStrokeColor(colors.HexColor("#C9DFF0"))
    c.line(band_x + slot, band_y + 8, band_x + slot, band_y + band_h - 8)
    c.line(band_x + 2 * slot, band_y + 8, band_x + 2 * slot, band_y + band_h - 8)

    summaries = [
        ("NOSSO TP", f"US$ {target:.2f}", f"+{upside:.1f}% upside", BLUE),
        ("CONSENSO", f"US$ {consensus:.2f}", "11 analistas", INK),
        ("BUY-IN", f"US$ {buy_in:.2f}", "entrada disciplinada", AMBER),
    ]
    for idx, (label, value, sub, color) in enumerate(summaries):
        center = band_x + slot * (idx + 0.5)
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 5.8)
        c.drawCentredString(center, band_y + 43, label)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 11.5)
        c.drawCentredString(center, band_y + 24, value)
        c.setFillColor(SUB)
        c.setFont("Helvetica", 5.4)
        c.drawCentredString(center, band_y + 9, sub)


def bullet_box(c, x, y, w, h, title, bullets, accent=BLUE, fill=WHITE):
    rounded_box(c, x, y, w, h, fill=fill)
    section_title(c, title, x + 11, y + h - 20, w - 22, accent)
    top = y + h - 33
    for bullet in bullets:
        used = para(c, f"- {bullet}", x + 13, top, w - 25, "bullet", 70)
        top -= used + 1


def scenario_box(c, x, y, w, h):
    rounded_box(c, x, y, w, h, fill=WHITE, stroke=BORDER)
    section_title(c, "Cenários de preço-alvo", x + 11, y + h - 20, w - 22, AMBER)
    scenarios = [
        ("BEAR", "US$ 8,50", f"{(8.50 / price - 1) * 100:+.0f}%", RED, colors.HexColor("#FFF1F1"), colors.HexColor("#F2B8B5")),
        ("BASE", f"US$ {target:.0f}", f"+{upside:.0f}%", BLUE, BLUE_LIGHT, colors.HexColor("#A9D3EE")),
        ("BULL", "US$ 18", f"+{(18 / price - 1) * 100:.0f}%", GREEN, GREEN_LIGHT, colors.HexColor("#A9D9C4")),
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
        c.setFont("Helvetica-Bold", 11.0)
        c.drawCentredString(center, cards_y + 21, value)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawCentredString(center, cards_y + 8, move)

    multiples = [
        ("P/E", "63,4x"),
        ("FWRD P/E", "21,0x"),
        ("EV/EBITDA", "24,0x"),
        ("PEG derivado", "3,47x"),
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
        c.setFont("Helvetica-Bold", 4.9)
        c.drawCentredString(xx + slot / 2, band_y + 31, label.upper())
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8.7)
        c.drawCentredString(xx + slot / 2, band_y + 13, value)


def draw():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("NOK One Pager - Q2 2026")

    c.setFillColor(INK)
    c.rect(0, PAGE_H - 78, PAGE_W, 78, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, PAGE_H - 21, "EQUITY RESEARCH | EARNINGS UPDATE")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(M, PAGE_H - 50, "NOK | NOKIA")
    c.setFillColor(colors.HexColor("#CAD1D8"))
    c.setFont("Helvetica", 8)
    c.drawString(M, PAGE_H - 66, "Q2 2026: demanda de AI & Cloud dobra; optical/IP acelera; caixa ainda exige disciplina")

    card_y = PAGE_H - 65
    kpi(c, 470, card_y, 105, "Preço de fechamento", f"US$ {price:.2f}", "31/jul/26", fill=WHITE)
    kpi(c, 582, card_y, 105, "Novo TP 12m", f"US$ {target:.0f}", "base case", fill=BLUE_LIGHT, value_color=BLUE)
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
            "Receita comparável cresceu 9% em moeda constante; Network Infrastructure avançou 12%, puxada por Optical (+20%) e IP (+16%).",
            "Vendas AI & Cloud mais que dobraram; pedidos de EUR 2,8 bi, com metade da conversão esperada nos próximos 12 meses.",
            "Mobile Infrastructure cresceu 7% em moeda constante, mas a margem caiu para 11,6%, mantendo a unidade sob observação.",
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
            "Lucro operacional comparável cresceu 18% e a margem subiu 0,7 p.p.; o prejuízo operacional reportado reflete a aceleração da reestruturação.",
            "O FCF foi negativo em EUR 732 mi por capital de giro, pagamentos de incentivos, reestruturação e capex; a conversão anual segue guiada em 55%-75%.",
            "A Nokia encerrou o trimestre com EUR 2,8 bi de caixa líquido, suficiente para financiar capacidade optical, mas sem folga para erros de execução.",
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
            "Infinera e a demanda por interconexão de data centers reposicionam a Nokia como fornecedora crítica para o ciclo de IA.",
            "Optical e IP combinam crescimento, backlog e margem; a produção de componentes InP nos EUA fortalece a oferta e a diferenciação.",
            "AI-RAN, 6G e NVIDIA adicionam opcionalidade; licenciamento e Mobile Infrastructure sustentam a base de lucro.",
            "O TP de US$ 14 exige conversão dos pedidos AI & Cloud e melhora de margem, sem incorporar todo o otimismo do consenso.",
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
            "Guidance 2026: lucro operacional comparável de EUR 2,1-2,6 bi; a revisão de EUR 0,1 bi foi técnica, não uma melhora operacional.",
            "Para Q3, a companhia espera receita +3%-7% sequencial e lucro comparável quase estável, antes de uma aceleração relevante no Q4.",
            "Monitorar a conversão dos EUR 2,8 bi de pedidos, restrições de componentes, margem de Mobile Infrastructure e FCF após a reestruturação.",
            "Concorrência com Ericsson, Huawei e fornecedores de data center, ciclos de capex de telecom e execução da Infinera podem comprimir o múltiplo.",
        ],
        accent=RED,
        fill=colors.HexColor("#FFFAFA"),
    )

    scenario_box(c, right_x, 91, right_w, 160)

    c.setStrokeColor(BORDER)
    c.line(M, 72, PAGE_W - M, 72)
    footer = (
        "<b>Fontes:</b> Nokia Q2 and Half Year 2026 Report; StockAnalysis/S&amp;P Global e Investing.com para preço, múltiplos e cobertura pública. "
        "<b>Metodologia:</b> média de cinco abordagens proprietárias, horizonte de 12 meses; buy-in incorpora margem de segurança e risco de execução. "
        "Material informativo; não constitui recomendação individual de investimento."
    )
    para(c, footer, M, 66, PAGE_W - 2 * M, "small", 30)
    c.setFillColor(SUB)
    c.setFont("Helvetica", 5.8)
    c.drawRightString(PAGE_W - M, 13, "Atualizado em 01/08/2026 | ADR NYSE: NOK | Horizonte: 12 meses")

    c.showPage()
    c.save()
    print(OUT.resolve())


if __name__ == "__main__":
    draw()
