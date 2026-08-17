#!/usr/bin/env python3
import datetime as dt
import html
import statistics
import sys
from pathlib import Path

import morning_summary as ms
import prnr3_single_pager as base


OUT_DIR = Path("outputs")

PAGES = {
    "TOTS3": {
        "symbol": "TOTS3.SA",
        "name": "TOTVS",
        "sector": "Software, ERP, SaaS, Techfin e business performance",
        "quality": 86,
        "ai": 76,
        "cyclical": False,
        "required_upside": 0.40,
        "buy_in_discount": 0.10,
        "consensus_value": 49.75,
        "consensus_analysts": 12,
        "consensus_rating": "Compra/Overweight",
        "shares_outstanding": 617_180_000,
        "coverage": [
            {"house": "BTG Pactual", "target": 55.00, "rating": "Compra", "date": "26/06/2026", "call_date": "2026-06-26"},
            {"house": "Itau BBA", "target": 46.00, "rating": "Compra", "date": "Jun/26", "call_date": "2026-06-18"},
            {"house": "XP Investimentos", "target": 48.00, "rating": "Compra", "date": "2026", "call_date": "2026-04-01"},
        ],
        "thesis": [
            "TOTVS combina baixa ciclicidade, alta recorrencia e uma base instalada ampla, o que melhora previsibilidade de receita e protege margem em ciclos macro mais fracos.",
            "O principal motor de valor e a expansao de ARPU via cross-sell em ERP, Techfin e business performance, com ganho de margem se a companhia sustentar disciplina de despesas.",
            "A tese ganha forca se os proximos trimestres mostrarem crescimento orgânico de software acima da inflacao, churn controlado e melhor conversao de EBITDA em caixa.",
        ],
        "risk": [
            "Valuation ainda exige crescimento consistente; qualquer desaceleracao em SaaS/ERP pode comprimir multiplos.",
            "Execucao em Techfin e integracao de produtos precisam preservar margem, sem aumentar inadimplencia ou capital empregado de forma excessiva.",
        ],
        "guidance": [
            ("2T26", "Monitorar crescimento organico de software, net revenue retention e margem EBITDA consolidada."),
            ("2S26", "Gatilho positivo seria Techfin crescer com melhor risco/retorno e business performance entregar escala."),
            ("2026", "Sem guidance numerico publico trimestral formal; usar calls, releases e consenso como proxy de acompanhamento."),
        ],
        "sources": {
            "BTG": "https://content.btgpactual.com/research/ativo/TOTS3",
            "Itau BBA / media": "https://www.moneytimes.com.br/totvs-tots3-itau-bba-passa-a-tesoura-no-preco-alvo-mas-ainda-ve-potencial-de-61-para-acao-apsa/",
            "XP": "https://conteudos.xpi.com.br/acoes/tots3/",
            "Investing": "https://br.investing.com/equities/totvs-on-ej-nm-consensus-estimates",
            "Yahoo": "https://finance.yahoo.com/quote/TOTS3.SA",
        },
    },
    "SUZB3": {
        "symbol": "SUZB3.SA",
        "name": "Suzano",
        "sector": "Celulose, papel, exportacao e ciclo global de commodities",
        "quality": 72,
        "ai": 54,
        "cyclical": True,
        "required_upside": 0.40,
        "buy_in_discount": 0.12,
        "consensus_value": 65.58,
        "consensus_analysts": 16,
        "consensus_rating": "Compra/Overweight",
        "shares_outstanding": 1_250_000_000,
        "coverage": [
            {"house": "BTG Pactual", "target": 72.00, "rating": "Compra", "date": "Jun/26", "call_date": "2026-06-26"},
            {"house": "XP Investimentos", "target": 66.00, "rating": "Compra", "date": "2026", "call_date": "2026-04-01"},
            {"house": "UBS", "target": 64.00, "rating": "Compra", "date": "2026", "call_date": "2026-03-01"},
            {"house": "Genial / mercado", "target": 63.50, "rating": "Compra", "date": "2026", "call_date": "2026-02-01"},
        ],
        "thesis": [
            "Suzano e uma produtora de baixo custo global; quando o ciclo de celulose melhora, a alavancagem operacional e o cambio podem acelerar EBITDA e fluxo de caixa.",
            "O projeto Cerrado aumenta escala e dilui custo estrutural, mas a criacao de valor depende de rampa operacional, precos internacionais e disciplina na desalavancagem.",
            "A tese fica mais forte se a companhia capturar volumes com spreads melhores e reduzir divida liquida/EBITDA sem sacrificar retorno ao acionista.",
        ],
        "risk": [
            "O risco central e ciclo de celulose: China, oferta global e preco spot podem mudar rapidamente a percepcao de lucro.",
            "Alavancagem, capex, FX e custo logistico podem atrasar o rerating mesmo com ativos de qualidade.",
        ],
        "guidance": [
            ("2T26", "Acompanhar realizacao de preco de celulose, volumes e evolucao do custo caixa apos rampa do Cerrado."),
            ("2S26", "Gatilho positivo seria maior geracao de FCF e trajetoria clara de desalavancagem."),
            ("2026", "Sem guidance numerico publico trimestral formal consolidado; monitorar releases, calls e consenso setorial."),
        ],
        "sources": {
            "BTG": "https://content.btgpactual.com/research/ativo/SUZB3",
            "XP": "https://conteudos.xpi.com.br/acoes/suzb3/",
            "Investing": "https://br.investing.com/equities/suzano-papel-celulose-consensus-estimates",
            "Yahoo": "https://finance.yahoo.com/quote/SUZB3.SA",
        },
    },
    "VALE3": {
        "symbol": "VALE3.SA",
        "name": "Vale",
        "sector": "Mineracao, minerio de ferro, metais basicos, China e dividendos",
        "quality": 70,
        "ai": 58,
        "cyclical": True,
        "required_upside": 0.40,
        "buy_in_discount": 0.12,
        "consensus_value": 89.50,
        "consensus_analysts": 7,
        "consensus_rating": "Compra/Overweight",
        "shares_outstanding": 4_270_000_000,
        "coverage": [
            {"house": "TradingView consenso", "target": 89.50, "rating": "Compra", "date": "Jul/26", "call_date": "2026-07-08"},
            {"house": "TradingView bull case", "target": 104.00, "rating": "Alta", "date": "Jul/26", "call_date": "2026-07-08"},
            {"house": "TradingView bear case", "target": 75.00, "rating": "Neutro", "date": "Jul/26", "call_date": "2026-07-08"},
        ],
        "thesis": [
            "Vale segue como uma das formas mais liquidas de exposicao a minerio de ferro, com geracao de caixa elevada quando preco realizado, premio de qualidade e cambio trabalham a favor.",
            "A assimetria vem de valuation descontado, potencial de dividendos/recompras e opcionalidade em metais basicos, desde que a demanda chinesa e a disciplina de capex sustentem EBITDA.",
            "A tese ganha forca se os proximos trimestres mostrarem volumes estaveis, custo caixa controlado, reducao de provisoes/risco juridico e continuidade de retorno ao acionista.",
        ],
        "risk": [
            "O risco principal e macro/commodity: desaceleracao da China, queda do minerio e menor premio de qualidade comprimem lucro rapidamente.",
            "Passivos ambientais, licenciamento, seguranca operacional, intervencao regulatoria e FX podem afetar valuation e politica de dividendos.",
        ],
        "guidance": [
            ("2T26", "Acompanhar volume de minerio, preco realizado vs benchmark, custo C1 e evolucao de provisoes."),
            ("2S26", "Gatilho positivo seria combinacao de demanda chinesa melhor, disciplina de oferta e manutencao de FCF forte."),
            ("2026", "Monitorar guidance de producao, capex, metais basicos, dividendos e revisoes de consenso apos cada resultado."),
        ],
        "sources": {
            "TradingView": "https://www.tradingview.com/symbols/BMFBOVESPA-VALE3/forecast/",
            "Yahoo": "https://finance.yahoo.com/quote/VALE3.SA",
            "Investing": "https://br.investing.com/equities/vale-on-n1-consensus-estimates",
            "Vale RI": "https://www.vale.com/investors",
        },
    },
    "ITUB4": {
        "symbol": "ITUB4.SA",
        "name": "Itau Unibanco",
        "sector": "Banco universal, credito, seguros, wealth, adquirencia e eficiencia operacional",
        "quality": 88,
        "ai": 72,
        "cyclical": False,
        "required_upside": 0.30,
        "buy_in_discount": 0.09,
        "consensus_value": 48.50,
        "consensus_analysts": 12,
        "consensus_rating": "Compra/Overweight",
        "shares_outstanding": 9_800_000_000,
        "coverage": [
            {"house": "TradingView consenso", "target": 48.50, "rating": "Compra", "date": "Jul/26", "call_date": "2026-07-10"},
            {"house": "BTG Pactual / mercado", "target": 51.00, "rating": "Compra", "date": "2026", "call_date": "2026-06-01"},
            {"house": "XP Investimentos / mercado", "target": 49.00, "rating": "Compra", "date": "2026", "call_date": "2026-05-01"},
            {"house": "Itau BBA / mercado", "target": 47.50, "rating": "Neutro/Compra", "date": "2026", "call_date": "2026-04-01"},
        ],
        "thesis": [
            "Itau e a franquia bancaria de maior qualidade da B3: ROE elevado, custo de risco disciplinado, escala digital e mix de receitas resiliente sustentam premio frente aos pares.",
            "A tese depende de manter crescimento de carteira com inadimplencia controlada, eficiencia operacional, capital confortavel e distribuicao de dividendos/JCP sem comprometer crescimento.",
            "O rerating fica mais provavel se os proximos trimestres confirmarem NII resiliente, custo de credito benigno, fee income forte e manutencao de ROE acima do custo de capital.",
        ],
        "risk": [
            "O risco principal e o ciclo de credito: deterioracao em pessoa fisica/PME, competicao de spreads e pressao regulatoria podem comprimir margem e ROE.",
            "Por ser banco premium, parte da qualidade ja esta no preco; upside depende de lucro continuar surpreendendo e de mercado aceitar multiplos mais altos.",
        ],
        "guidance": [
            ("2T26", "Monitorar margem financeira com clientes, custo de credito, inadimplencia acima de 90 dias e crescimento da carteira por segmento."),
            ("2S26", "Gatilho positivo seria combinacao de ROE alto, provisoes controladas, eficiencia melhor e revisao para cima do lucro recorrente."),
            ("2026", "Acompanhar guidance de carteira, NII, custo de credito, comissoes, despesas e payout; bancos devem reagir a juros, atividade e regulacao."),
        ],
        "sources": {
            "TradingView": "https://www.tradingview.com/symbols/BMFBOVESPA-ITUB4/forecast/",
            "Yahoo": "https://finance.yahoo.com/quote/ITUB4.SA",
            "Investing": "https://br.investing.com/equities/itauunibanco-pn-edj-n1-consensus-estimates",
            "Itau RI": "https://www.itau.com.br/relacoes-com-investidores/",
        },
    },
    "RAPT4": {
        "symbol": "RAPT4.SA",
        "name": "Randoncorp",
        "sector": "Implementos rodoviarios, autopecas, servicos financeiros e ciclo de transporte/logistica",
        "quality": 62,
        "ai": 50,
        "cyclical": True,
        "required_upside": 0.42,
        "buy_in_discount": 0.14,
        "consensus_value": 7.50,
        "consensus_analysts": 9,
        "consensus_rating": "Compra/Outperform",
        "shares_outstanding": 330_000_000,
        "coverage": [
            {"house": "TradingView consenso", "target": 7.50, "rating": "Compra", "date": "Jul/26", "call_date": "2026-07-10"},
            {"house": "Mercado / bull case", "target": 8.50, "rating": "Compra", "date": "2026", "call_date": "2026-06-01"},
            {"house": "Mercado / base case", "target": 7.50, "rating": "Compra", "date": "2026", "call_date": "2026-06-01"},
            {"house": "Mercado / bear case", "target": 6.20, "rating": "Neutro", "date": "2026", "call_date": "2026-06-01"},
        ],
        "thesis": [
            "Randoncorp e uma tese ciclica de transporte/logistica: implementos, autopecas, reposicao e servicos financeiros tendem a reagir quando juros, frete e renovacao de frota melhoram.",
            "A assimetria vem de valuation descontado, EV/EBITDA baixo e potencial de normalizacao de margem se volumes industriais, mix de autopecas e controle de custos surpreenderem.",
            "A tese ganha forca se os proximos trimestres mostrarem recuperacao de pedidos, melhora de margem EBITDA, capital de giro sob controle e geracao de caixa mais previsivel.",
        ],
        "risk": [
            "O risco principal e ciclo: demanda por implementos e autopecas depende de juros, credito, frete, agro, atividade industrial e confianca dos transportadores.",
            "Margem pode sofrer com ociosidade, pressao de custos, mix mais fraco, inadimplencia em servicos financeiros e atraso na retomada de caminhões/implementos.",
        ],
        "guidance": [
            ("2T26", "Monitorar receita por divisao, carteira de pedidos, margem EBITDA, capital de giro e sinais de melhora em implementos e reposicao."),
            ("2S26", "Gatilho positivo seria retomada de volumes com disciplina de preco, melhora de mix e geracao de caixa operacional."),
            ("2026", "Acompanhar ciclo de juros, credito para transporte, safra/agro, exportacoes, margem de autopecas e revisoes de consenso apos resultados."),
        ],
        "sources": {
            "TradingView": "https://www.tradingview.com/symbols/BMFBOVESPA-RAPT4/forecast/",
            "Yahoo": "https://finance.yahoo.com/quote/RAPT4.SA",
            "Investing": "https://br.investing.com/equities/randon-part-pn-consensus-estimates",
            "Randoncorp RI": "https://ri.randoncorp.com/",
        },
    },
}


def main():
    OUT_DIR.mkdir(exist_ok=True)
    tickers = sys.argv[1:] or ["TOTS3", "SUZB3"]
    for ticker in tickers:
        cfg = PAGES[ticker.upper()]
        data = build_page_data(ticker.upper(), cfg)
        html_path = OUT_DIR / f"{ticker.lower()}-single-pager.html"
        pdf_path = OUT_DIR / f"{ticker.lower()}-single-pager.pdf"
        html_path.write_text(render_html(data), encoding="utf-8")
        ok, msg = ms.make_chromium_pdf(html_path, pdf_path)
        if not ok:
            ok, msg = ms.make_pdf(html_path, pdf_path)
        if not ok:
            raise RuntimeError(f"{ticker}: PDF nao gerado: {msg}")
        print(f"{ticker}: HTML {html_path}")
        print(f"{ticker}: PDF {pdf_path}")


def build_page_data(ticker, cfg):
    symbol = cfg["symbol"]
    history = base.fetch_yahoo_history(symbol, "1y", "1d")
    meta = ms.fetch_yahoo_chart_meta(symbol)
    price = base.num(meta.get("regularMarketPrice")) or base.latest_close(history)
    previous_close = base.num(meta.get("chartPreviousClose")) or base.num(meta.get("previousClose"))
    if previous_close is None and len(history) >= 2:
        previous_close = history[-2]["close"]
    day_change = (price / previous_close - 1) * 100 if price is not None and previous_close else None
    quote = base.fetch_yahoo_quote(symbol)
    market_cap = base.num(meta.get("marketCap")) or base.num(quote.get("marketCap"))
    if market_cap is None and price is not None and cfg.get("shares_outstanding"):
        market_cap = price * cfg["shares_outstanding"]

    ms.CANDIDATE_SYMBOLS[ticker] = symbol
    ms.CANDIDATE_IS_ETF[ticker] = False
    ms.CANDIDATE_REQUIRED_UPSIDE[ticker] = cfg["required_upside"]
    ms.CANDIDATE_BUY_IN_DISCOUNT[ticker] = cfg["buy_in_discount"]
    item = {
        "ticker": ticker,
        "symbol": symbol,
        "sector": cfg["sector"],
        "quality": cfg["quality"],
        "ai": cfg["ai"],
        "cyclical": cfg["cyclical"],
        "catalyst": cfg["thesis"][1],
        "risk": cfg["risk"][0],
    }
    multiples = ms.fetch_candidate_multiples(ticker, symbol, "")
    price_context = ms.fetch_candidate_price_context(symbol)
    model = ms.candidate_modeled_target_snapshot(item, price, cfg["consensus_value"], multiples, price_context)
    our_tp = model.get("target_value")
    buy_in = ms.candidate_buy_in_value(ticker, price, our_tp, price_context, multiples)
    consensus_value = cfg["consensus_value"]
    consensus_analysts = cfg["consensus_analysts"]
    summary_snapshot = ms.latest_summary_candidate_snapshot(ticker)
    if summary_snapshot:
        snapshot_price = summary_snapshot.get("price")
        snapshot_our_tp = summary_snapshot.get("our_tp")
        snapshot_buy_in = summary_snapshot.get("buy_in")
        snapshot_consensus = summary_snapshot.get("consensus")
        if snapshot_price is not None:
            price = snapshot_price
        if snapshot_our_tp is not None:
            if our_tp and model.get("methods"):
                factor = snapshot_our_tp / our_tp
                model["methods"] = {
                    name: (value * factor if value else value)
                    for name, value in model.get("methods", {}).items()
                }
            our_tp = snapshot_our_tp
        if snapshot_buy_in is not None:
            buy_in = snapshot_buy_in
        if snapshot_consensus is not None:
            consensus_value = snapshot_consensus
        if summary_snapshot.get("analysts") is not None:
            consensus_analysts = summary_snapshot["analysts"]
    return {
        "ticker": ticker,
        "cfg": cfg,
        "as_of": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "price": price,
        "previous_close": previous_close,
        "day_change": day_change,
        "market_cap": market_cap,
        "history": history,
        "multiples": multiples,
        "price_context": price_context,
        "our_tp": our_tp,
        "buy_in": buy_in,
        "model_methods": model.get("methods", {}),
        "our_upside": base.pct_change(price, our_tp),
        "consensus_value": consensus_value,
        "consensus_analysts": consensus_analysts,
        "consensus_upside": base.pct_change(price, consensus_value),
        "buy_in_distance": base.pct_change(buy_in, price) if buy_in else None,
    }


def render_html(data):
    cfg = data["cfg"]
    ticker = data["ticker"]
    price_chart = base.sparkline_svg(data["history"], 590, 155, cfg["coverage"], show_legend=False)
    method_values = [value for value in data["model_methods"].values() if value]
    max_method = max(method_values) if method_values else None
    min_method = min(method_values) if method_values else None
    method_rows = "".join(
        valuation_method_row(name, value, max_method, min_method)
        for name, value in data["model_methods"].items()
        if value
    )
    coverage_rows = "".join(
        f"<tr><td>{html.escape(item['house'])}</td><td>{base.money(item.get('target'))}</td><td>{html.escape(item['rating'])}</td><td>{html.escape(item['date'])}</td></tr>"
        for item in cfg["coverage"]
    )
    guidance_rows = "".join(
        f"<li><span class='tag'>{html.escape(label)}</span> {html.escape(text)}</li>"
        for label, text in cfg["guidance"]
    )
    source_links = " | ".join(
        f"<a href='{html.escape(url)}'>{html.escape(name)}</a>" for name, url in cfg["sources"].items()
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{ticker} Single Pager</title>
  <style>
    @page {{ size: A4 landscape; margin: 8mm; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: #101828; background: #fff; }}
    .page {{ width: 281mm; min-height: 194mm; position: relative; padding: 0; }}
    .top {{ display: grid; grid-template-columns: 1fr 1.25fr; gap: 7mm; align-items: end; border-bottom: 2px solid #d9e2ec; padding-bottom: 4mm; }}
    .eyebrow {{ color: #667085; font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .7px; }}
    h1 {{ margin: 1mm 0 0; font-size: 34px; line-height: 1; letter-spacing: 0; }}
    .subtitle {{ color: #475467; font-size: 12px; margin-top: 2mm; }}
    .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 2mm; }}
    .kpi {{ border: 1px solid #d9e2ec; background: #f8fafc; padding: 2.2mm 2.5mm; min-height: 16mm; }}
    .kpi-label {{ font-size: 8px; color: #667085; text-transform: uppercase; font-weight: 850; letter-spacing: .4px; }}
    .kpi-value {{ font-size: 17px; font-weight: 950; margin-top: 1mm; white-space: nowrap; }}
    .kpi-sub {{ font-size: 8.3px; color: #667085; margin-top: .6mm; }}
    .pos {{ color: #067647; }} .neg {{ color: #b42318; }} .blue {{ color: #175cd3; }} .purple {{ color: #7c3aed; }}
    .valuation-high {{ color: #067647; font-weight: 850; }}
    .valuation-low {{ color: #b42318; font-weight: 850; }}
    .our-tp-row td {{ color: #175cd3; font-weight: 950; }}
    .grid {{ display: grid; grid-template-columns: 1.18fr .82fr; gap: 5mm; margin-top: 3.5mm; }}
    .left, .right {{ display: grid; gap: 2.6mm; }}
    .box {{ border: 1px solid #d9e2ec; padding: 2.6mm; background: #fff; break-inside: avoid; }}
    .compact-box {{ padding-top: 2mm; padding-bottom: 2mm; }}
    .box-title {{ font-size: 9.6px; color: #475467; font-weight: 900; text-transform: uppercase; letter-spacing: .6px; margin-bottom: 1.6mm; }}
    .chart-title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 4mm; margin-bottom: 1.6mm; }}
    .chart-title-row .box-title {{ margin-bottom: 0; }}
    .call-legend {{ display: flex; align-items: center; gap: 4mm; color: #667085; font-size: 9px; font-weight: 500; text-transform: none; letter-spacing: 0; }}
    .call-legend span {{ display: inline-flex; align-items: center; gap: 1.4mm; }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
    .dot.buy {{ background: #16a34a; }}
    .dot.hold {{ background: #175cd3; }}
    .dot.sell {{ background: #111827; }}
    .chart-wrap {{ height: 45mm; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; font-size: 7.8px; color: #667085; text-transform: uppercase; letter-spacing: .35px; background: #f2f5f8; padding: 4px 5px; }}
    td {{ font-size: 9.4px; padding: 4px 5px; border-top: 1px solid #edf1f5; vertical-align: top; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.6mm; }}
    .metric {{ background: #f8fafc; border: 1px solid #e7ebf0; padding: 1.8mm; min-height: 12mm; }}
    .metric b {{ display: block; font-size: 12px; margin-top: .7mm; }}
    .metric span {{ color: #667085; font-size: 7.8px; font-weight: 800; text-transform: uppercase; }}
    .metric em {{ display: block; color: #667085; font-size: 7.8px; margin-top: .7mm; font-style: normal; }}
    .bullets {{ margin: 0; padding-left: 4mm; }}
    .bullets li {{ font-size: 9.0px; line-height: 1.22; margin-bottom: 1.25mm; text-align: justify; text-justify: inter-word; }}
    .compact-bullets li {{ margin-bottom: .8mm; }}
    .tag {{ display: inline-block; padding: 1px 4px; border-radius: 3px; background: #eef4ff; color: #175cd3; font-size: 7px; font-weight: 900; text-transform: uppercase; }}
    .footer {{ position: absolute; bottom: 7mm; left: 0; right: 0; display: flex; justify-content: space-between; gap: 4mm; color: #98a2b3; font-size: 7.8px; border-top: 1px solid #edf1f5; padding-top: 2mm; }}
    a {{ color: inherit; text-decoration: none; }}
    .note {{ color: #667085; font-size: 8px; line-height: 1.2; margin-top: 1.2mm; text-align: justify; text-justify: inter-word; }}
  </style>
</head>
<body>
<section class="page">
  <div class="top">
    <div>
      <div class="eyebrow">Single Pager | B3 Equity Model</div>
      <h1>{ticker} | {html.escape(cfg['name'])}</h1>
      <div class="subtitle">{html.escape(cfg['sector'])} | Atualizado em {html.escape(data['as_of'])}</div>
    </div>
    <div class="kpis">
      {base.price_kpi(base.brl_plain(data["price"]), data["day_change"])}
      {base.kpi("Our TP", base.money(data["our_tp"]), base.signed_pct(data["our_upside"]) + " upside", "blue")}
      {base.kpi("Consensus", base.money(data["consensus_value"]), f"{data['consensus_analysts']} analistas | {base.signed_pct(data['consensus_upside'])}", "purple")}
      {base.kpi("Buy-in", base.money(data["buy_in"]), base.signed_pct(data["buy_in_distance"]) + " vs preco")}
      {base.kpi("Mkt Cap", base.brl_big(data["market_cap"]), "Yahoo Finance")}
    </div>
  </div>

  <div class="grid">
    <div class="left">
      <div class="box">
        <div class="chart-title-row">
          <div class="box-title">Stock performance | ultimos 12 meses + analyst calls</div>
          <div class="call-legend">
            <span><i class="dot buy"></i>Buy</span>
            <span><i class="dot hold"></i>Hold</span>
            <span><i class="dot sell"></i>Sell</span>
          </div>
        </div>
        <div class="chart-wrap">{price_chart}</div>
        <div class="metric-grid">
          {base.metric("12m return", base.signed_pct(base.history_return(data["history"])))}
          {base.metric("52w low/high", f"{base.brl_plain(base.history_low(data['history']))} / {base.brl_plain(base.history_high(data['history']))}")}
          {base.metric("Vol. anualizada", base.signed_pct(base.history_volatility(data["history"]), plus=False))}
          {base.metric("Ultimo fechamento", base.brl_plain(base.latest_close(data["history"])))}
        </div>
      </div>

      <div class="box">
        <div class="box-title">Quant snapshot | multiplos e preco</div>
        <div class="metric-grid">
          {metric_from_multiples("P/E", data["multiples"])}
          {metric_from_multiples("FWRD P/E", data["multiples"])}
          {metric_from_multiples("EV/EBITDA", data["multiples"])}
          {metric_from_multiples("PEG Ratio", data["multiples"])}
          {base.metric("6m percentile", percentile_text(data["price_context"].get("percentile_rank_6m")))}
          {base.metric("20d SMA", base.brl_plain(data["price_context"].get("sma_20d")))}
          {base.metric("50d SMA", base.brl_plain(data["price_context"].get("sma_50d")))}
          {base.metric("6m range", f"{base.brl_plain(data['price_context'].get('low_6m'))} / {base.brl_plain(data['price_context'].get('high_6m'))}")}
        </div>
      </div>

      <div class="box compact-box">
        <div class="box-title">AI thesis & risk</div>
        <ul class="bullets compact-bullets">
          <li><b class="pos">Tese:</b> {html.escape(cfg["thesis"][0])}</li>
          <li><b class="pos">Por que comprar:</b> {html.escape(cfg["thesis"][1])}</li>
          <li><b>Trigger:</b> {html.escape(cfg["thesis"][2])}</li>
          <li><b class="neg">Risco:</b> {html.escape(" ".join(cfg["risk"]))}</li>
        </ul>
      </div>
    </div>

    <div class="right">
      <div class="box">
        <div class="box-title">Valuation model | nossa metodologia</div>
        <table>
          <thead><tr><th>Driver</th><th>Valor</th></tr></thead>
          <tbody>
            {method_rows}
            <tr class="our-tp-row"><td>Our TP medio</td><td>{base.money(data['our_tp'])}</td></tr>
            <tr><td><b>Buy-in price</b></td><td><b>{base.money(data['buy_in'])}</b></td></tr>
          </tbody>
        </table>
      </div>

      <div class="box">
        <div class="box-title">Consensus/TP | public coverage</div>
        <table>
          <thead><tr><th>Casa</th><th>TP</th><th>Rec.</th><th>Rev.</th></tr></thead>
          <tbody>
            <tr><td><b>Consenso publico</b></td><td><b>{base.money(data['consensus_value'])}</b></td><td>{html.escape(cfg['consensus_rating'])}</td><td>{data['consensus_analysts']} analistas</td></tr>
            <tr><td><b>Nosso modelo</b></td><td><b>{base.money(data['our_tp'])}</b></td><td>TP medio 5 metodologias</td><td>{base.signed_pct(data['our_upside'])}</td></tr>
            {coverage_rows}
          </tbody>
        </table>
      </div>

      <div class="box">
        <div class="box-title">Guidance / proximos trimestres</div>
        <ul class="bullets">{guidance_rows}</ul>
        <div class="note">Quando nao ha guidance numerico formal por trimestre, o acompanhamento usa releases, calls, consenso e drivers operacionais publicos.</div>
      </div>
    </div>
  </div>

  <div class="footer">
    <span>Chief of Staff Digital | {ticker} single pager | Uso interno, nao e recomendacao de investimento.</span>
    <span>Fontes: {source_links}</span>
  </div>
</section>
</body>
</html>"""


def metric_from_multiples(label, multiples):
    value = "N/D"
    for part in (multiples or "").split(" | "):
        if part.startswith(label + " "):
            value = part.replace(label + " ", "")
            break
    return base.metric(label, value)


def valuation_method_row(name, value, max_method, min_method):
    cls = ""
    if max_method is not None and abs(value - max_method) < 0.0001:
        cls = " class='valuation-high'"
    elif min_method is not None and abs(value - min_method) < 0.0001:
        cls = " class='valuation-low'"
    return (
        f"<tr{cls}><td>{html.escape(base.method_display_name(name))}</td>"
        f"<td>{base.money(value)}</td></tr>"
    )


def percentile_text(value):
    if value is None:
        return "N/D"
    return f"{value * 100:.0f}%"


if __name__ == "__main__":
    sys.exit(main())
