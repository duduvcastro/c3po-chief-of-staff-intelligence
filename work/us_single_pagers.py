#!/usr/bin/env python3
import datetime as dt
import html
import re
import sys
import urllib.request
from pathlib import Path

import morning_summary as ms
import prnr3_single_pager as base


OUT_DIR = Path("outputs")

PAGES = {
    "ZETA": {
        "symbol": "ZETA",
        "name": "Zeta Global",
        "sector": "AI-powered marketing cloud, customer data platform, identity graph and emerging business intelligence layer",
        "quality": 72,
        "ai": 84,
        "cyclical": False,
        "turnaround": False,
        "required_upside": 0.40,
        "buy_in_discount": 0.10,
        "shares_outstanding": 235_000_000,
        "coverage": [
            {"house": "Yahoo / Wall Street consensus", "target": None, "rating": "Buy consensus", "date": "live"},
            {"house": "StockAnalysis forecast", "target": None, "rating": "Analyst average", "date": "live"},
            {"house": "AI/BI scenario from public investor commentary", "target": 40.00, "rating": "Base-case scenario", "date": "Jul/26"},
        ],
        "thesis": [
            "Zeta is increasingly a data/AI decisioning platform, not only a marketing cloud: the core asset is its identity graph, behavioral signals and workflow layer that can support business intelligence use cases beyond campaign execution.",
            "The OpenAI/Athena angle strengthens the AI thesis: if Athena becomes an enterprise decision layer and not merely a marketing assistant, Zeta could deserve a higher revenue multiple than traditional ad-tech/martech peers.",
            "The more aggressive bull case depends on management proving that the new business intelligence push can expand TAM, replace legacy systems of record in large accounts and sustain 20%+ revenue growth with margin expansion.",
        ],
        "risk": [
            "Several bullish claims still need validation in filings/calls: the size of the incremental BI TAM, the economics of Palantir/OpenAI integrations, and whether reported enterprise wins translate into recurring platform revenue.",
            "The main risk is quality of growth: acquisitions, stock-based compensation, privacy regulation, customer churn and competitive pressure from Salesforce, Adobe and other data clouds can pressure the multiple.",
            "If AI monetization disappoints, if the company remains perceived as ad-tech rather than enterprise software, or if margins fail to expand, the stock can derate despite headline revenue growth.",
        ],
        "guidance": [
            ("2026", "Track organic revenue growth, adjusted EBITDA margin, free cash flow conversion and net revenue retention."),
            ("AI/BI", "Confirm commercial traction for Athena and the business intelligence layer: number of paying clients, expansion revenue, ROI proof points and whether Zeta becomes system-of-record in large accounts."),
            ("Valuation", "A 6x sales scenario would imply materially higher upside; require evidence that Zeta is being valued as enterprise AI/data software rather than marketing/ad-tech."),
            ("Risk control", "Monitor SBC, acquisition integration, privacy/regulatory changes and concentration among large enterprise customers."),
        ],
        "sources": {
            "Yahoo": "https://finance.yahoo.com/quote/ZETA",
            "StockAnalysis": "https://stockanalysis.com/stocks/zeta/forecast/",
            "Zeta IR": "https://investors.zetaglobal.com/",
            "Barron's / OpenAI": "https://www.barrons.com/articles/zeta-global-stock-openai-ai-ed14599f",
            "Nasdaq": "https://www.nasdaq.com/market-activity/stocks/zeta",
        },
    },
    "XNDU": {
        "symbol": "XNDU",
        "name": "Xanadu Quantum Technologies",
        "sector": "Photonic quantum computing hardware, PennyLane quantum software and cloud-accessible quantum systems",
        "quality": 46,
        "ai": 72,
        "cyclical": True,
        "turnaround": True,
        "required_upside": 0.60,
        "buy_in_discount": 0.20,
        "shares_outstanding": 295_000_000,
        "quarterly_revenue": 2_800_000,
        "cash": 272_500_000,
        "adjusted_ebitda": -13_900_000,
        "quant_metrics_override": [
            ("FY26e revenue", "US$ 8.1 MM"),
            ("Rev. growth", "+76.3%"),
            ("FCF burn TTM", "US$ 64.0 MM"),
            ("Cash runway", "4.3 anos"),
        ],
        "multiples_override": "P/E N/M | FWRD P/E N/M | EV/EBITDA N/M | PEG Ratio N/M",
        "coverage": [
            {"house": "Yahoo / Wall Street consensus", "target": None, "rating": "Speculative consensus", "date": "live"},
            {"house": "StockAnalysis forecast", "target": None, "rating": "Analyst average", "date": "live"},
            {"house": "Quantum platform scenario", "target": 22.00, "rating": "Base-case scenario", "date": "Jul/26"},
            {"house": "High-conviction quantum bull case", "target": 35.00, "rating": "Bull scenario", "date": "Jul/26"},
        ],
        "thesis": [
            "Xanadu is a pure public bet on photonic quantum computing: room-temperature photonics, optical networking and modular error correction could scale differently from superconducting/ion-trap peers.",
            "PennyLane gives Xanadu software mindshare and a bridge between quantum hardware, simulation and ML workflows before hardware revenue is mature.",
            "A rerating needs proof: larger reliable systems, more funded enterprise/government contracts, software adoption and a credible path to fault-tolerant quantum around 2029-2030.",
        ],
        "risk": [
            "Pre-profit, long-duration equity: small revenue base, losses, dilution and share-registration pressure can dominate.",
            "Commercial timing is the main risk: quantum advantage may remain economically distant, while larger competitors can compress strategic value.",
        ],
        "guidance": [
            ("2026", "Track revenue, net loss/cash burn, liquidity after SPAC/PIPE and Canadian government funding updates."),
            ("Technology", "Watch processor scale, error correction, optical networking, uptime and 2029-2030 timeline credibility."),
            ("Software", "Monitor PennyLane users/downloads, enterprise integrations and conversion into paid workflows."),
            ("Risk control", "Treat as venture-style public equity: size for dilution, volatility and commercialization delays."),
        ],
        "sources": {
            "Yahoo": "https://finance.yahoo.com/quote/XNDU",
            "StockAnalysis": "https://stockanalysis.com/stocks/xndu/forecast/",
            "Xanadu": "https://www.xanadu.ai/",
            "Investors.com": "https://www.investors.com/news/technology/xanadu-stock-quantum-computing-stocks-q12026/",
            "Barron's": "https://www.barrons.com/articles/xanadu-quantum-technologies-earnings-stock-price-f0940d54",
            "Nasdaq": "https://www.nasdaq.com/market-activity/stocks/xndu",
        },
    },
    "SBET": {
        "symbol": "SBET",
        "name": "SharpLink Gaming",
        "sector": "Ethereum treasury strategy, online sports-betting affiliate technology and crypto-linked equity optionality",
        "quality": 34,
        "ai": 54,
        "cyclical": True,
        "turnaround": True,
        "required_upside": 0.30,
        "buy_in_discount": 0.09,
        "shares_outstanding": 75_000_000,
        "coverage": [
            {"house": "Yahoo / Wall Street consensus", "target": None, "rating": "Speculative Buy consensus", "date": "live"},
            {"house": "StockAnalysis forecast", "target": None, "rating": "Analyst average", "date": "live"},
        ],
        "thesis": [
            "SharpLink is no longer a clean operating-company valuation: the equity is mostly a high-beta Ethereum treasury vehicle with residual sports-betting affiliate technology optionality.",
            "The upside case depends on ETH appreciation, treasury execution, transparent capital allocation and whether the company can avoid issuing equity at moments that dilute per-share crypto exposure.",
            "A valid buy case needs a discount to modeled treasury value plus evidence that management is not simply using the public listing as a financing wrapper for a volatile crypto trade.",
        ],
        "risk": [
            "This is a very speculative microcap: liquidity, dilution, crypto drawdowns, financing terms and sentiment can dominate fundamentals over any traditional multiple-based valuation.",
            "If ETH falls, if new shares are issued below intrinsic treasury value, or if disclosure around treasury holdings is not clear, the stock can reprice violently even with analyst upside.",
        ],
        "guidance": [
            ("Treasury", "Track ETH holdings per diluted share, staking yield, custody/disclosure quality and whether capital raises are accretive or dilutive to treasury value."),
            ("Operating", "Core gaming affiliate revenue is currently secondary; watch whether it stabilizes, burns cash or becomes a distraction from the treasury strategy."),
            ("Risk control", "Position sizing should be small and rules-based: the main variables are ETH price, dilution, liquidity and market appetite for crypto-treasury equities."),
        ],
        "sources": {
            "Yahoo": "https://finance.yahoo.com/quote/SBET",
            "StockAnalysis": "https://stockanalysis.com/stocks/sbet/forecast/",
            "SharpLink IR": "https://investors.sharplink.com/",
            "Nasdaq": "https://www.nasdaq.com/market-activity/stocks/sbet",
        },
    },
    "ONDS": {
        "symbol": "ONDS",
        "name": "Ondas Holdings",
        "sector": "Autonomous drones, counter-UAS, rail wireless networks and AI defense systems",
        "quality": 48,
        "ai": 78,
        "cyclical": True,
        "turnaround": True,
        "required_upside": 0.55,
        "buy_in_discount": 0.16,
        "shares_outstanding": 102_000_000,
        "coverage": [
            {"house": "Yahoo / Wall Street consensus", "target": None, "rating": "Buy consensus", "date": "live"},
            {"house": "StockAnalysis forecast", "target": None, "rating": "Analyst average", "date": "live"},
        ],
        "thesis": [
            "Ondas is a high-beta defense/autonomous systems story: revenue acceleration, counter-UAS demand and the Palantir partnership can justify a premium if backlog converts into gross profit.",
            "The most important proof point is operating leverage: backlog is valuable only if deliveries scale with improving adjusted EBITDA and cash burn moderation.",
            "A cleaner entry needs confirmation that 2026 revenue guidance is achievable without excessive dilution or margin leakage from acquisitions.",
        ],
        "risk": [
            "Execution risk is high: acquisitions, defense procurement timing, customer concentration and still-negative EBITDA can make the equity volatile.",
            "The stock already prices a large growth narrative; any delay in backlog conversion, funding needs or lower gross margin can reset valuation quickly.",
        ],
        "guidance": [
            ("2026", "Company commentary/news flow points to very high revenue growth and raised full-year revenue outlook; validate against each quarterly filing."),
            ("2H26", "Watch counter-UAS deliveries, backlog conversion, Palantir integration and whether adjusted EBITDA loss narrows with scale."),
            ("Cash", "Dilution and working-capital funding remain key variables until the business shows durable operating cash flow."),
        ],
        "sources": {
            "Yahoo": "https://finance.yahoo.com/quote/ONDS",
            "StockAnalysis": "https://stockanalysis.com/stocks/onds/forecast/",
            "Ondas IR": "https://ir.ondas.com/",
            "Barron's": "https://www.barrons.com/articles/palantir-backed-ondas-stock-jumps-autonomous-drone-company-sees-revenue-grow-1-065-da6b5e1d",
        },
    },
    "ZVRA": {
        "symbol": "ZVRA",
        "name": "Zevra Therapeutics",
        "sector": "Rare disease therapeutics, MIPLYFFA commercialization and pipeline optionality",
        "quality": 58,
        "ai": 46,
        "cyclical": False,
        "turnaround": True,
        "required_upside": 0.50,
        "buy_in_discount": 0.18,
        "shares_outstanding": 61_000_000,
        "coverage": [
            {"house": "Yahoo / Wall Street consensus", "target": None, "rating": "Buy consensus", "date": "live"},
            {"house": "StockAnalysis forecast", "target": None, "rating": "Analyst average", "date": "live"},
        ],
        "thesis": [
            "Zevra is a rare-disease commercialization story: MIPLYFFA execution, patient starts and payer access are more important than headline multiples.",
            "The upside case depends on durable launch momentum, operating expense control and optionality from the broader rare-disease pipeline.",
            "If revenue growth keeps compounding while cash burn becomes more predictable, the stock can rerate from biotech optionality toward a more commercial-stage profile.",
        ],
        "risk": [
            "Single-product concentration, payer friction, small patient population and clinical/regulatory pipeline risk can create sharp drawdowns.",
            "Biotech sentiment and funding conditions matter: even with revenue growth, valuation can compress if losses or dilution remain above expectations.",
        ],
        "guidance": [
            ("2026", "Track MIPLYFFA demand, net revenue per patient, reimbursement progress and operating expense discipline."),
            ("Pipeline", "Catalysts depend on clinical/regulatory updates and whether management can expand the rare-disease platform beyond the lead product."),
            ("Cash", "Monitor runway, gross-to-net dynamics and whether commercialization scale reduces cash burn over the next quarters."),
        ],
        "sources": {
            "Yahoo": "https://finance.yahoo.com/quote/ZVRA",
            "StockAnalysis": "https://stockanalysis.com/stocks/zvra/forecast/",
            "Zevra IR": "https://investors.zevra.com/",
        },
    },
    "MSFT": {
        "symbol": "MSFT",
        "name": "Microsoft",
        "sector": "Azure cloud, Microsoft 365, Copilot, enterprise software, security, gaming and AI infrastructure",
        "quality": 96,
        "ai": 94,
        "cyclical": False,
        "turnaround": False,
        "required_upside": 0.30,
        "buy_in_discount": 0.10,
        "shares_outstanding": 7_427_000_000,
        "coverage": [
            {"house": "StockAnalysis / S&P Global", "target": 557.25, "rating": "Strong Buy", "date": "Jul/26", "call_date": "2026-07-27"},
            {"house": "Morgan Stanley", "target": 600.00, "rating": "Overweight", "date": "Jul/26", "call_date": "2026-07-24"},
            {"house": "Guggenheim", "target": 586.00, "rating": "Buy", "date": "27/07/2026", "call_date": "2026-07-27"},
            {"house": "UBS", "target": 480.00, "rating": "Buy", "date": "27/07/2026", "call_date": "2026-07-27"},
        ],
        "thesis": [
            "Microsoft combines a dominant enterprise distribution layer with Azure, Microsoft 365, security, GitHub and Copilot, creating multiple paths to monetize AI across infrastructure, applications and usage-based services.",
            "FY26 Q4 strengthened the operating case: revenue reached US$ 90.0 billion, Azure grew 43%, Microsoft Cloud grew 27% and commercial RPO reached US$ 678 billion, improving visibility despite record AI infrastructure investment.",
            "The rerating case requires Azure capacity additions and Copilot adoption to keep converting into revenue growth, while model efficiency and pricing protect gross margin and free cash flow through the FY27 capex cycle.",
        ],
        "risk": [
            "The central risk is return on AI capital: FY27 capex is expected to grow and Q1 spend should exceed US$ 50 billion, so slower Azure/Copilot monetization could pressure free cash flow and valuation.",
            "Cloud competition, model commoditization, capacity constraints, cybersecurity failures, antitrust regulation and dependence on large AI partners can reduce growth or raise the cost of maintaining Microsoft's platform advantage.",
            "After the post-earnings price reaction, entry discipline matters: strong fundamentals do not eliminate multiple compression if rates rise, margins soften or consensus estimates become too optimistic.",
        ],
        "guidance": [
            ("FY27 Q1", "Company revenue of US$ 89.85-90.95 billion, or 16%-17% growth; Intelligent Cloud revenue of US$ 40.95-41.25 billion, with Azure growth near 45% in constant currency."),
            ("M365", "Commercial cloud growth of about 16% in constant currency on an adjusted basis, with acceleration expected through FY27 from Copilot, E5, E7 and usage-based billing."),
            ("FY27", "Management expects double-digit revenue and operating income growth, operating margin down less than one point, continued positive free cash flow and an effective tax rate near 20%."),
            ("CAPEX", "FY27 capital expenditures should grow; Q1 spend is expected above US$ 50 billion, while calendar 2026 capex is now approximately US$ 175 billion after lease reclassification."),
        ],
        "sources": {
            "Microsoft FY26 Q4": "https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q4/press-release-webcast",
            "Microsoft call": "https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4",
            "StockAnalysis": "https://stockanalysis.com/stocks/msft/forecast/",
            "TipRanks": "https://www.tipranks.com/stocks/msft/forecast",
            "MarketBeat": "https://www.marketbeat.com/stocks/NASDAQ/MSFT/forecast/",
            "Yahoo": "https://finance.yahoo.com/quote/MSFT",
        },
    },
}


def main():
    OUT_DIR.mkdir(exist_ok=True)
    tickers = [item.upper() for item in (sys.argv[1:] or ["ONDS", "ZVRA"])]
    for ticker in tickers:
        data = build_page_data(ticker, PAGES[ticker])
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

    ms.CANDIDATE_SYMBOLS[ticker] = symbol
    ms.CANDIDATE_IS_ETF[ticker] = False
    ms.CANDIDATE_REQUIRED_UPSIDE[ticker] = cfg["required_upside"]
    ms.CANDIDATE_BUY_IN_DISCOUNT[ticker] = cfg["buy_in_discount"]
    consensus_display, consensus_value = ms.fetch_candidate_target_price(ticker)
    analysts = parse_analyst_count(consensus_display)
    multiples = cfg.get("multiples_override") or ms.fetch_candidate_multiples(ticker, symbol, "")
    price_context = ms.fetch_candidate_price_context(symbol)
    item = {
        "ticker": ticker,
        "symbol": symbol,
        "sector": cfg["sector"],
        "quality": cfg["quality"],
        "ai": cfg["ai"],
        "cyclical": cfg["cyclical"],
        "turnaround": cfg["turnaround"],
        "catalyst": cfg["thesis"][1],
        "risk": cfg["risk"][0],
    }
    model = ms.candidate_modeled_target_snapshot(item, price, consensus_value, multiples, price_context)
    our_tp = model.get("target_value")
    buy_in = ms.candidate_buy_in_value(ticker, price, our_tp, price_context, multiples)
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
            model["target_value"] = snapshot_our_tp
        if snapshot_buy_in is not None:
            buy_in = snapshot_buy_in
        if snapshot_consensus is not None:
            consensus_value = snapshot_consensus
        if summary_snapshot.get("analysts") is not None:
            analysts = summary_snapshot["analysts"]
            consensus_display = f"{usd(consensus_value)} ({analysts} analistas)"
    market_cap = stockanalysis_market_cap(ticker) or (price * cfg["shares_outstanding"] if price else None)
    quant_metrics = build_quant_metrics(cfg, market_cap, multiples)
    coverage = hydrate_coverage(cfg["coverage"], consensus_value)
    return {
        "ticker": ticker,
        "cfg": cfg,
        "as_of": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "price": price,
        "day_change": day_change,
        "market_cap": market_cap,
        "history": history,
        "multiples": multiples,
        "quant_metrics": quant_metrics,
        "price_context": price_context,
        "consensus_display": consensus_display,
        "consensus_value": consensus_value,
        "consensus_analysts": analysts,
        "coverage": coverage,
        "our_tp": our_tp,
        "buy_in": buy_in,
        "model_methods": model.get("methods", {}),
        "our_upside": base.pct_change(price, our_tp),
        "consensus_upside": base.pct_change(price, consensus_value),
        "buy_in_distance": base.pct_change(buy_in, price) if buy_in else None,
    }


def latest_summary_candidate_snapshot(ticker):
    files = sorted(OUT_DIR.glob("*summary-*.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files:
        snapshot = summary_candidate_snapshot_from_html(path, ticker)
        if snapshot:
            snapshot["source"] = str(path)
            return snapshot
    return None


def summary_candidate_snapshot_from_html(path, ticker):
    text = path.read_text(encoding="utf-8", errors="ignore")
    marker = f"candidate-symbol'>{html.escape(ticker)}"
    start = text.find(marker)
    if start < 0:
        return None
    row_start = text.rfind("<tr", 0, start)
    row_end = text.find("</tr>", start)
    if row_start < 0 or row_end < 0:
        return None
    row = html.unescape(text[row_start : row_end + 5])
    return {
        "price": extract_money(row, r"class='current-price'>([^<]+)<"),
        "consensus": extract_money(row, r"class='target-price'>([^<]+)<"),
        "our_tp": extract_money(row, r"class='model-target-price'>([^<]+)<"),
        "buy_in": extract_money(row, r"class='buy-price'>([^<]+)<"),
        "analysts": extract_int(row, r"\((\d+)\s+analistas\)"),
    }


def extract_money(text, pattern):
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    value = normalize_number(match.group(1))
    return value


def extract_int(text, pattern):
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else None


def normalize_number(value):
    cleaned = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def render_html(data):
    cfg = data["cfg"]
    ticker = data["ticker"]
    price_chart = base.sparkline_svg(data["history"], 590, 155, data["coverage"], show_legend=False)
    method_values = [value for value in data["model_methods"].values() if value]
    max_method = max(method_values) if method_values else None
    min_method = min(method_values) if method_values else None
    method_rows = "".join(
        valuation_method_row(name, value, max_method, min_method)
        for name, value in data["model_methods"].items()
        if value
    )
    coverage_rows = "".join(
        f"<tr><td>{html.escape(row['house'])}</td><td>{usd(row.get('target'))}</td><td>{html.escape(row['rating'])}</td><td>{html.escape(row['date'])}</td></tr>"
        for row in data["coverage"]
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
    .left, .right {{ display: grid; gap: 2.1mm; }}
    .box {{ border: 1px solid #d9e2ec; padding: 2.2mm; background: #fff; break-inside: avoid; }}
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
    .chart-wrap {{ height: 40mm; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; font-size: 7.8px; color: #667085; text-transform: uppercase; letter-spacing: .35px; background: #f2f5f8; padding: 4px 5px; }}
    td {{ font-size: 9.4px; padding: 4px 5px; border-top: 1px solid #edf1f5; vertical-align: top; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.6mm; }}
    .metric {{ background: #f8fafc; border: 1px solid #e7ebf0; padding: 1.8mm; min-height: 12mm; }}
    .metric b {{ display: block; font-size: 12px; margin-top: .7mm; }}
    .metric span {{ color: #667085; font-size: 7.8px; font-weight: 800; text-transform: uppercase; }}
    .metric em {{ display: block; color: #667085; font-size: 7.8px; margin-top: .7mm; font-style: normal; }}
    .bullets {{ margin: 0; padding-left: 4mm; }}
    .bullets li {{ font-size: 8.35px; line-height: 1.14; margin-bottom: .85mm; text-align: justify; text-justify: inter-word; }}
    .compact-bullets li {{ margin-bottom: .55mm; }}
    .tag {{ display: inline-block; padding: 1px 4px; border-radius: 3px; background: #eef4ff; color: #175cd3; font-size: 7px; font-weight: 900; text-transform: uppercase; }}
    .footer {{ position: absolute; bottom: 1.5mm; left: 0; right: 0; display: flex; justify-content: space-between; gap: 4mm; color: #98a2b3; font-size: 6.8px; border-top: 1px solid #edf1f5; padding-top: 1mm; }}
    a {{ color: inherit; text-decoration: none; }}
  </style>
</head>
<body>
<section class="page">
  <div class="top">
    <div>
      <div class="eyebrow">Single Pager | US Equity Model</div>
      <h1>{ticker} | {html.escape(cfg['name'])}</h1>
      <div class="subtitle">{html.escape(cfg['sector'])} | Atualizado em {html.escape(data['as_of'])}</div>
    </div>
    <div class="kpis">
      {usd_price_kpi(data["price"], data["day_change"])}
      {kpi("Our TP", usd(data["our_tp"]), base.signed_pct(data["our_upside"]) + " upside", "blue")}
      {kpi("Consensus", usd(data["consensus_value"]), f"{data['consensus_analysts'] or 'N/D'} analistas | {base.signed_pct(data['consensus_upside'])}", "purple")}
      {kpi("Buy-in", usd(data["buy_in"]), base.signed_pct(data["buy_in_distance"]) + " vs preco")}
      {kpi("Mkt Cap", usd_big(data["market_cap"]), "estimate / public data")}
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
          {base.metric("52w low/high", f"{plain(data['history'] and base.history_low(data['history']))} / {plain(data['history'] and base.history_high(data['history']))}")}
          {base.metric("Vol. anualizada", base.signed_pct(base.history_volatility(data["history"]), plus=False))}
          {base.metric("Ultimo fechamento", plain(base.latest_close(data["history"])))}
        </div>
      </div>

      <div class="box">
        <div class="box-title">Quant snapshot | multiples e preco</div>
        <div class="metric-grid">
          {render_quant_metrics(data)}
          {base.metric("6m percentile", percentile_text(data["price_context"].get("percentile_rank_6m")))}
          {base.metric("20d SMA", plain(data["price_context"].get("sma_20d")))}
          {base.metric("50d SMA", plain(data["price_context"].get("sma_50d")))}
          {base.metric("6m range", f"{plain(data['price_context'].get('low_6m'))} / {plain(data['price_context'].get('high_6m'))}")}
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
            <tr class="our-tp-row"><td>Our TP medio</td><td>{usd(data['our_tp'])}</td></tr>
            <tr><td><b>Buy-in price</b></td><td><b>{usd(data['buy_in'])}</b></td></tr>
          </tbody>
        </table>
      </div>

      <div class="box">
        <div class="box-title">Consensus/TP | public coverage</div>
        <table>
          <thead><tr><th>Fonte</th><th>TP</th><th>Rec.</th><th>Rev.</th></tr></thead>
          <tbody>
            <tr><td><b>Consenso publico</b></td><td><b>{usd(data['consensus_value'])}</b></td><td>Analyst average</td><td>{data['consensus_analysts'] or 'N/D'} analistas</td></tr>
            <tr><td><b>Nosso modelo</b></td><td><b>{usd(data['our_tp'])}</b></td><td>TP medio 5 metodologias</td><td>{base.signed_pct(data['our_upside'])}</td></tr>
            {coverage_rows}
          </tbody>
        </table>
      </div>

      <div class="box">
        <div class="box-title">Guidance / proximos catalisadores</div>
        <ul class="bullets">{guidance_rows(cfg["guidance"])}</ul>
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


def kpi(label, value, sub="", cls=""):
    return f"<div class='kpi'><div class='kpi-label'>{html.escape(label)}</div><div class='kpi-value {cls}'>{html.escape(value)}</div><div class='kpi-sub'>{html.escape(sub or '')}</div></div>"


def usd_price_kpi(price, day_change):
    arrow_html = ""
    if day_change is not None:
        color = "#067647" if day_change >= 0 else "#b42318"
        arrow = "&#9650;" if day_change >= 0 else "&#9660;"
        arrow_html = f"<span style='color:{color}; font-size:13px; margin-left:6px; vertical-align:2px; font-weight:950'>{arrow}</span>"
    return (
        "<div class='kpi'><div class='kpi-label'>Price</div>"
        f"<div class='kpi-value'>{html.escape(plain(price))}{arrow_html}</div>"
        f"<div class='kpi-sub'>{html.escape(base.signed_pct(day_change) + ' hoje')}</div></div>"
    )


def valuation_method_row(name, value, max_method, min_method):
    cls = ""
    if max_method is not None and abs(value - max_method) < 0.0001:
        cls = " class='valuation-high'"
    elif min_method is not None and abs(value - min_method) < 0.0001:
        cls = " class='valuation-low'"
    return f"<tr{cls}><td>{html.escape(base.method_display_name(name))}</td><td>{usd(value)}</td></tr>"


def build_quant_metrics(cfg, market_cap, multiples):
    if cfg.get("quant_metrics_override"):
        return cfg["quant_metrics_override"]
    quarterly_revenue = cfg.get("quarterly_revenue")
    cash = cfg.get("cash")
    adjusted_ebitda = cfg.get("adjusted_ebitda")
    if quarterly_revenue and market_cap:
        revenue_run_rate = quarterly_revenue * 4
        enterprise_value = market_cap - (cash or 0)
        return [
            ("P/S", ratio_text(market_cap, revenue_run_rate)),
            ("EV/Sales", ratio_text(enterprise_value, revenue_run_rate)),
            ("EV/EBITDA", "N/M" if adjusted_ebitda and adjusted_ebitda < 0 else ratio_text(enterprise_value, adjusted_ebitda)),
            ("Cash", money_short(cash)),
        ]
    return [
        ("P/E", multiple_value("P/E", multiples)),
        ("FWRD P/E", multiple_value("FWRD P/E", multiples)),
        ("EV/EBITDA", multiple_value("EV/EBITDA", multiples)),
        ("PEG Ratio", multiple_value("PEG Ratio", multiples)),
    ]


def ratio_text(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return "N/M"
    return f"{numerator / denominator:.1f}x"


def money_short(value):
    if value is None:
        return "N/D"
    if abs(value) >= 1_000_000_000:
        return f"US$ {value / 1_000_000_000:.1f} BI"
    if abs(value) >= 1_000_000:
        return f"US$ {value / 1_000_000:.1f} MM"
    return f"US$ {value:,.0f}"


def multiple_value(label, multiples):
    for part in (multiples or "").split(" | "):
        if part.startswith(label + " "):
            return part.replace(label + " ", "")
    return "N/D"


def metric_from_multiples(label, multiples):
    return base.metric(label, multiple_value(label, multiples))


def render_quant_metrics(data):
    metrics = data.get("quant_metrics") or []
    return "\n          ".join(base.metric(label, value) for label, value in metrics)


def guidance_rows(rows):
    return "".join(f"<li><span class='tag'>{html.escape(label)}</span> {html.escape(text)}</li>" for label, text in rows)


def hydrate_coverage(rows, target):
    hydrated = []
    for row in rows:
        copy = dict(row)
        if copy.get("target") is None:
            copy["target"] = target
        hydrated.append(copy)
    return hydrated


def stockanalysis_market_cap(ticker):
    for path in ("market-cap", "statistics"):
        url = f"https://stockanalysis.com/stocks/{ticker.lower()}/{path}/"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                page = response.read().decode("utf-8", errors="replace")
            clean = re.sub(r"\s+", " ", html.unescape(page))
            match = re.search(r"Market Cap(?:italization)?</[^>]+>\s*<[^>]+>\$([0-9,.]+)\s*([BMK]?)", page, re.I)
            if not match:
                match = re.search(r"market cap(?:italization)?(?: is| of)?\s*\$([0-9,.]+)\s*([BMK])", clean, re.I)
            if match:
                return scaled_number(match.group(1), match.group(2))
        except Exception:
            continue
    return None


def scaled_number(raw, suffix):
    value = float(str(raw).replace(",", ""))
    suffix = (suffix or "").upper()
    if suffix == "B":
        return value * 1_000_000_000
    if suffix == "M":
        return value * 1_000_000
    if suffix == "K":
        return value * 1_000
    return value


def parse_analyst_count(display):
    match = re.search(r"\((\d+)\s*anal", str(display or ""), re.I)
    return int(match.group(1)) if match else None


def percentile_text(value):
    if value is None:
        return "N/D"
    return f"{value * 100:.0f}%"


def usd(value):
    if value is None:
        return "N/D"
    return f"US$ {value:,.2f}"


def plain(value):
    if value is None:
        return "N/D"
    return f"{float(value):.2f}"


def usd_big(value):
    if value is None:
        return "N/D"
    if value >= 1_000_000_000:
        return f"US$ {value / 1_000_000_000:.1f} BI"
    if value >= 1_000_000:
        return f"US$ {value / 1_000_000:.0f} mm"
    return usd(value)


if __name__ == "__main__":
    sys.exit(main())
