#!/usr/bin/env python3
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


OUT = Path("outputs/amzn-one-pager-q2-2026.pdf")

PAGE_W, PAGE_H = landscape(A4)
M = 8 * mm

INK = colors.HexColor("#111827")
SUB = colors.HexColor("#59636E")
LIGHT = colors.HexColor("#F5F7F9")
BORDER = colors.HexColor("#D9E0E7")
ORANGE = colors.HexColor("#FF9900")
ORANGE_LIGHT = colors.HexColor("#FFF5E6")
BLUE = colors.HexColor("#1473E6")
BLUE_LIGHT = colors.HexColor("#EAF3FF")
GREEN = colors.HexColor("#087A55")
GREEN_LIGHT = colors.HexColor("#E9F7F0")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#D97706")
WHITE = colors.white

# Market close and public consensus as of 03/Aug/2026.
price = 284.02
day_change = 4.58
consensus = 323.29
consensus_analysts = 62

# Shared five-method framework used by the Chief of Staff screening model.
valuation_methods = [
    ("Goldman Sachs", 359.0282945462299),
    ("Morgan Stanley", 358.17139054973177),
    ("Bridgewater", 380.043263717395),
    ("JPMorgan", 363.49465033806894),
    ("BlackRock", 376.43800490283525),
]
target = sum(value for _, value in valuation_methods) / len(valuation_methods)
buy_in = 209.51
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
        fontSize=6.85,
        leading=8.45,
        textColor=INK,
        leftIndent=7,
        firstLineIndent=-7,
        alignment=TA_JUSTIFY,
        spaceAfter=1.5,
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


def section_title(c, title, x, y, w, accent=ORANGE):
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
    section_title(c, "2T26 - resultado operacional", x + 11, y + h - 20, w - 22)
    columns = [x + 12, x + 170, x + 254, x + 337]
    header_y = y + h - 46
    c.setFillColor(LIGHT)
    c.rect(x + 9, header_y - 4, w - 18, 16, fill=1, stroke=0)
    for i, text in enumerate(("Métrica", "2T26", "2T25", "YoY / delta")):
        c.setFillColor(SUB)
        c.setFont("Helvetica-Bold", 6.4)
        c.drawString(columns[i], header_y + 1, text.upper())

    rows = [
        ("Receita consolidada", "US$ 200,6 bi", "US$ 167,7 bi", "+20%"),
        ("Lucro operacional", "US$ 27,5 bi", "US$ 19,2 bi", "+43%"),
        ("Margem operacional", "13,7%", "11,4%", "+2,3 p.p."),
        ("AWS - receita", "US$ 42,2 bi", "US$ 30,9 bi", "+37%"),
        ("AWS - lucro operacional", "US$ 16,6 bi", "US$ 10,2 bi", "+64%"),
        ("Advertising services", "US$ 19,8 bi", "US$ 15,7 bi", "+26%"),
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
        c.setFont("Helvetica-Bold", 11.5)
        c.drawCentredString(center, band_y + 24, value)
        c.setFillColor(SUB)
        c.setFont("Helvetica", 5.4)
        c.drawCentredString(center, band_y + 9, sub)


def bullet_box(c, x, y, w, h, title, bullets, accent=ORANGE, fill=WHITE):
    rounded_box(c, x, y, w, h, fill=fill)
    section_title(c, title, x + 11, y + h - 20, w - 22, accent)
    top = y + h - 31
    for bullet in bullets:
        used = para(c, f"- {bullet}", x + 13, top, w - 25, "bullet", 70)
        top -= used + 0.5


def scenario_box(c, x, y, w, h):
    rounded_box(c, x, y, w, h, fill=WHITE, stroke=BORDER)
    section_title(c, "Cenários de preço-alvo", x + 11, y + h - 20, w - 22, ORANGE)
    scenarios = [
        ("BEAR", "US$ 230", f"{(230 / price - 1) * 100:+.0f}%", RED, colors.HexColor("#FFF1F1"), colors.HexColor("#F2B8B5")),
        ("BASE", f"US$ {target:.0f}", f"+{upside:.0f}%", BLUE, BLUE_LIGHT, colors.HexColor("#A9D3EE")),
        ("BULL", "US$ 425", f"+{(425 / price - 1) * 100:.0f}%", GREEN, GREEN_LIGHT, colors.HexColor("#A9D9C4")),
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
        ("P/E REPORTADO", "22,8x"),
        ("FWRD P/E", "30,6x"),
        ("EV/EBITDA", "18,9x"),
        ("PEG RATIO", "1,53x"),
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
    c.setTitle("AMZN One Pager - 2T26")

    c.setFillColor(INK)
    c.rect(0, PAGE_H - 78, PAGE_W, 78, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, PAGE_H - 21, "EQUITY RESEARCH | EARNINGS UPDATE")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(M, PAGE_H - 50, "AMZN | AMAZON.COM")
    c.setFillColor(colors.HexColor("#CAD1D8"))
    c.setFont("Helvetica", 8)
    c.drawString(M, PAGE_H - 66, "2T26: AWS acelera para 37%; margem expande; capex e financiamento viram o teste central")

    card_y = PAGE_H - 65
    kpi(c, 470, card_y, 105, "Preço de fechamento", f"US$ {price:.2f}", f"03/ago/26 | +{day_change:.2f}%", fill=WHITE)
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
            "Receita cresceu 20%, com aceleração simultânea em lojas online (+15%), serviços a sellers (+16%), publicidade (+26%) e AWS (+37%).",
            "AWS atingiu US$ 42,2 bi e o maior crescimento em 18 trimestres; a margem subiu para 39,4%, combinando escala, chips próprios e demanda de IA.",
            "North America entregou margem de 7,9% e International 4,1%; a melhora do varejo amplia a diversificação do lucro além de AWS.",
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
            "O lucro operacional avançou 43% e é a melhor medida do trimestre; o lucro líquido de US$ 62,6 bi inclui ganho pré-impostos de US$ 53,4 bi, principalmente Anthropic.",
            "O caixa operacional TTM subiu 33% para US$ 161,4 bi, mas o FCF caiu para -US$ 7,6 bi após forte expansão de infraestrutura de IA.",
            "Caixa e títulos somavam US$ 123,0 bi em junho; a dívida longa subiu para US$ 128,9 bi antes da emissão adicional de US$ 25 bi registrada em julho.",
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
            "AWS, publicidade e a logística Prime formam três motores de alta margem sobre uma base de mais de US$ 775 bi de receita TTM.",
            "Os negócios de IA e chips da AWS superaram, cada um, US$ 25 bi de run rate; Bedrock adicionou mais clientes nos últimos seis meses do que nos dois primeiros anos.",
            "Trainium, Graviton5 e os compromissos plurianuais de Anthropic e OpenAI reduzem custo por inferência e sustentam demanda visível por capacidade.",
            "Globalstar/Amazon Leo, Alexa+, Pharmacy e Supply Chain Services adicionam opcionalidade; o TP não antecipa contribuição material desses vetores no curto prazo.",
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
            "Guidance 3T26: receita de US$ 197-202 bi (+9% a +12%) e lucro operacional de US$ 22,5-26,5 bi; o calendário do Prime Day reduz a comparação reportada.",
            "Capex de 2026 foi elevado para cerca de US$ 220 bi. A tese exige que contratos e utilização da capacidade convertam esse investimento em receita, margem e FCF.",
            "Monitorar AWS, publicidade, margem do varejo, depreciação, FCF e dívida. O P/E reportado está artificialmente reduzido pelo ganho não recorrente com Anthropic.",
            "Concorrência em cloud/IA, antitruste, tarifas, memória mais cara, execução do Amazon Leo e volatilidade do valor da Anthropic são os principais riscos.",
        ],
        accent=RED,
        fill=colors.HexColor("#FFFAFA"),
    )

    scenario_box(c, right_x, 91, right_w, 160)

    c.setStrokeColor(BORDER)
    c.line(M, 72, PAGE_W - M, 72)
    footer = (
        "<b>Fontes:</b> Amazon 2T26 Earnings Release e earnings call; SEC Forms 10-Q/8-K; StockAnalysis/S&P Global e TipRanks para consenso. "
        "<b>Metodologia:</b> média de cinco abordagens proprietárias, horizonte de 12 meses; buy-in incorpora retorno mínimo, risco de execução e margem de segurança. "
        "Material informativo; não constitui recomendação individual de investimento."
    )
    para(c, footer, M, 66, PAGE_W - 2 * M, "small", 30)
    c.setFillColor(SUB)
    c.setFont("Helvetica", 5.8)
    c.drawRightString(PAGE_W - M, 13, "Atualizado em 03/08/2026 | Horizonte: 12 meses")

    c.showPage()
    c.save()
    print(OUT.resolve())


if __name__ == "__main__":
    draw()
