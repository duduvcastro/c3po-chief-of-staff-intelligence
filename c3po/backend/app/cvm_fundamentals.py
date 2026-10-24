from __future__ import annotations

import csv
import io
import math
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field as dataclass_field
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo


DRE_ACCOUNTS = {
    "3.01": "totalRevenue",
    "3.03": "grossProfit",
    "3.05": "operatingIncome",
    "3.07": "incomeBeforeTax",
    "3.08": "incomeTaxExpense",
    "3.11": "consolidatedNetIncome",
    "3.11.01": "netIncome",
}
BPA_ACCOUNTS = {
    "1": "totalAssets",
    "1.01.01": "cash",
    "1.01.02": "shortTermInvestments",
}
BPP_ACCOUNTS = {
    "2.01.04": "currentDebt",
    "2.02.01": "longTermDebt",
    "2.03": "totalStockholderEquity",
}


def extract_itr_official_fundamentals(
    archive_payload: bytes,
    *,
    year: int,
    issuers: dict[str, dict[str, Any]],
    source_url: str,
) -> list[dict[str, Any]]:
    """Extract standardized consolidated ITR accounts for mapped B3 issuers."""
    if not archive_payload or not issuers:
        return []
    with zipfile.ZipFile(io.BytesIO(archive_payload)) as archive:
        dre = _read_statement(
            archive,
            f"itr_cia_aberta_DRE_con_{year}.csv",
            issuers,
            DRE_ACCOUNTS,
            period_field="DT_FIM_EXERC",
            include_prior_comparative=True,
            require_year_to_date=True,
        )
        bpa = _read_statement(
            archive,
            f"itr_cia_aberta_BPA_con_{year}.csv",
            issuers,
            BPA_ACCOUNTS,
            period_field="DT_REFER",
        )
        bpp = _read_statement(
            archive,
            f"itr_cia_aberta_BPP_con_{year}.csv",
            issuers,
            BPP_ACCOUNTS,
            period_field="DT_REFER",
        )
        shares = _read_share_capital(
            archive,
            f"itr_cia_aberta_composicao_capital_{year}.csv",
            issuers,
        )

    output: list[dict[str, Any]] = []
    for tax_id, issuer in issuers.items():
        symbols = [str(symbol).upper() for symbol in issuer.get("symbols", []) if symbol]
        if not symbols:
            continue
        ytd_rows = dre.get(tax_id, {})
        quarterly_income = _quarterize_income(ytd_rows)
        latest_period = max(
            [*ytd_rows, *bpa.get(tax_id, {}), *bpp.get(tax_id, {}), *shares.get(tax_id, {})],
            default="",
        )
        if not latest_period:
            continue
        balance = {
            **bpa.get(tax_id, {}).get(latest_period, {}),
            **bpp.get(tax_id, {}).get(latest_period, {}),
        }
        cash = _number(balance.pop("cash", None))
        short_term = _number(balance.pop("shortTermInvestments", None))
        current_debt = _number(balance.pop("currentDebt", None))
        long_term_debt = _number(balance.pop("longTermDebt", None))
        company_ev_balance = None
        if (
            cash is not None
            and short_term is not None
            and current_debt is not None
            and long_term_debt is not None
        ):
            company_ev_balance = {
                "asOf": latest_period,
                "totalCash": cash + short_term,
                "totalDebt": current_debt + long_term_debt,
            }
        if cash is not None:
            balance["cash"] = cash
            balance["cashAndShortTermInvestments"] = cash + (short_term or 0.0)
        if current_debt is not None or long_term_debt is not None:
            balance["shortLongTermDebtTotal"] = (current_debt or 0.0) + (long_term_debt or 0.0)
        share_composition = shares.get(tax_id, {}).get(latest_period)
        share_count = _number((share_composition or {}).get("total"))
        published_at = issuer.get("published_at") or datetime.now(timezone.utc)
        for symbol in symbols:
            payload: dict[str, Any] = {
                "market": "B3",
                "symbol": symbol,
                "as_of": latest_period,
                "published_at": published_at.isoformat() if isinstance(published_at, datetime) else str(published_at),
                "source_name": "CVM Dados Abertos - ITR consolidado",
                "source_url": source_url,
                "currency": "BRL",
                "unit": "BRL",
                "quarterlyIncome": quarterly_income,
                "quarterlyBalance": [{"date": latest_period, **balance}] if balance else [],
                "quarterlyCashFlow": [],
                "official_metrics": {
                    "cvmRegulatorId": issuer.get("regulator_id"),
                    "cvmCompanyName": issuer.get("company_name"),
                    "cvmTaxId": tax_id,
                    "shareCapitalComposition": (
                        {"asOf": latest_period, **share_composition}
                        if share_composition
                        else None
                    ),
                    "companyEvBalance": company_ev_balance,
                },
            }
            if share_count and share_count > 0:
                payload["sharesOutstanding"] = share_count
            output.append(payload)
    return output


def _read_statement(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
    accounts: dict[str, str],
    *,
    period_field: str,
    include_prior_comparative: bool = False,
    require_year_to_date: bool = False,
) -> dict[str, dict[str, dict[str, float]]]:
    if filename not in archive.namelist():
        return {}
    selected: dict[tuple[str, str, str], tuple[int, float]] = {}
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            account = str(row.get("CD_CONTA") or "")
            if tax_id not in issuers or account not in accounts:
                continue
            allowed_orders = {"ULTIMO", "PENULTIMO"} if include_prior_comparative else {"ULTIMO"}
            if _fold(row.get("ORDEM_EXERC")) not in allowed_orders:
                continue
            period = str(row.get(period_field) or row.get("DT_REFER") or "")[:10]
            if require_year_to_date and not _is_year_to_date_row(
                row.get("DT_INI_EXERC"),
                period,
            ):
                continue
            value = _scaled_value(row.get("VL_CONTA"), row.get("ESCALA_MOEDA"))
            if not period or value is None:
                continue
            version = _integer(row.get("VERSAO"))
            key = (tax_id, period, accounts[account])
            prior = selected.get(key)
            if prior is None or version >= prior[0]:
                selected[key] = (version, value)
    output: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for (tax_id, period, field), (_, value) in selected.items():
        output[tax_id][period][field] = value
    return {tax_id: dict(periods) for tax_id, periods in output.items()}


def _is_year_to_date_row(start_value: Any, end_value: Any) -> bool:
    """Select the cumulative DRE row that can be safely quarterized.

    CVM ITR files publish both year-to-date and standalone-quarter rows with
    the same account and end date. Mixing the standalone row into a cumulative
    series would subtract the prior quarter twice.
    """
    try:
        start = date.fromisoformat(str(start_value or "")[:10])
        end = date.fromisoformat(str(end_value or "")[:10])
    except ValueError:
        return False
    return start == date(end.year, 1, 1) and start <= end


def _read_share_capital(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, float | None]]]:
    if filename not in archive.namelist():
        return {}
    selected: dict[tuple[str, str], tuple[int, dict[str, float | None]]] = {}
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            if tax_id not in issuers:
                continue
            period = str(row.get("DT_REFER") or "")[:10]
            ordinary = _net_share_count(
                row.get("QT_ACAO_ORDIN_CAP_INTEGR"),
                row.get("QT_ACAO_ORDIN_TESOURO"),
            )
            preferred = _net_share_count(
                row.get("QT_ACAO_PREF_CAP_INTEGR"),
                row.get("QT_ACAO_PREF_TESOURO"),
            )
            total = _net_share_count(
                row.get("QT_ACAO_TOTAL_CAP_INTEGR"),
                row.get("QT_ACAO_TOTAL_TESOURO"),
            )
            if not period or total is None:
                continue
            version = _integer(row.get("VERSAO"))
            key = (tax_id, period)
            prior = selected.get(key)
            if prior is None or version >= prior[0]:
                selected[key] = (
                    version,
                    {
                        "ordinary": ordinary,
                        "preferred": preferred,
                        "total": total,
                    },
                )
    output: dict[str, dict[str, dict[str, float | None]]] = defaultdict(dict)
    for (tax_id, period), (_, value) in selected.items():
        output[tax_id][period] = value
    return dict(output)


def _net_share_count(issued: Any, treasury: Any) -> float | None:
    issued_count = _number(issued)
    if issued_count is None:
        return None
    return max(issued_count - (_number(treasury) or 0.0), 0.0)


def _quarterize_income(rows: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous: dict[str, float] = {}
    previous_year: int | None = None
    for period in sorted(rows):
        try:
            period_date = date.fromisoformat(period)
        except ValueError:
            continue
        current = rows[period]
        if previous_year != period_date.year:
            previous = {}
        quarter: dict[str, Any] = {"date": period}
        for field, value in current.items():
            quarter[field] = value - previous.get(field, 0.0)
        if "netIncome" not in quarter and "consolidatedNetIncome" in quarter:
            quarter["netIncome"] = quarter["consolidatedNetIncome"]
        quarter.pop("consolidatedNetIncome", None)
        output.append(quarter)
        previous = current
        previous_year = period_date.year
    return sorted(output, key=lambda row: row["date"], reverse=True)


def _scaled_value(value: Any, scale: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    folded = _fold(scale)
    multiplier = 1_000.0 if folded == "MIL" else 1_000_000.0 if folded in {"MILHAO", "MILHOES"} else 1.0
    return number * multiplier


def _fold(value: Any) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").upper().strip()


def _integer(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# --------------------------------------------------------------------------------------------------------------------
# Complete statements (ITR + DFP): income (DRE), D&A from the value-added statement (DVA) for EBITDA, cash flow (DFC,
# indirect or direct method), balance (BPA/BPP) and capital composition -- consolidated, or individual for an issuer
# that files no consolidated statement. Accounts are matched by code AND description: in a bank or insurer layout 3.05
# is pre-tax income and 2.02.01 is deposits, and the legacy code-only mapping above would file them as operating income
# and debt. A field whose account is missing or ambiguous is left out, never guessed.

STATEMENTS_SOURCE_NAME = "CVM Dados Abertos - ITR/DFP"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
QUARTER_END_DAYS = {3: 31, 6: 30, 9: 30, 12: 31}
STATEMENT_HISTORY_QUARTERS = 8
# Raw as-filed columns handed to the vintage capture, unscaled and unparsed: the vintage is the document.
VINTAGE_COLUMNS = (
    "ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA",
    "VL_CONTA", "ESCALA_MOEDA", "MOEDA", "ST_CONTA_FIXA",
)
CAPITAL_VINTAGE_COLUMNS = (
    "QT_ACAO_ORDIN_CAP_INTEGR", "QT_ACAO_PREF_CAP_INTEGR", "QT_ACAO_TOTAL_CAP_INTEGR",
    "QT_ACAO_ORDIN_TESOURO", "QT_ACAO_PREF_TESOURO", "QT_ACAO_TOTAL_TESOURO",
)
# Every account this extractor reads sits at level <= 2 (3.11.01, 6.02.03, 2.03.09...): a vintage keeps those lines, so
# any number served from these statements can be rebuilt from the original filing; deeper detail lines are not kept
# (about 60% of the rows, measured on the 2026 ITR dump).
VINTAGE_MAX_LEVEL = 2
VINTAGE_FLUSH_ROWS = 20_000  # bounded memory: the capture receives a file in batches, a document may span two


@dataclass(frozen=True)
class CvmPackage:
    """One CVM open-data archive: the ``itr``/``dfp`` documents whose reference date falls in ``year``."""

    document_type: str
    year: int
    payload: bytes
    source_url: str


@dataclass(frozen=True)
class _Concept:
    field: str
    matches: Callable[[str, str], bool]
    additive: bool = False  # sum every matching account (capex lines) instead of requiring exactly one
    magnitude: bool = False  # DVA retentions are filed negative; the concept is their size


@dataclass(frozen=True)
class CvmVintageBatch:
    """Raw rows of one statement file, grouped by document (CNPJ, DT_REFER, VERSAO), for the vintage capture."""

    scan: "CvmPackageScan"
    issuers: dict[str, dict[str, Any]]
    statement: str
    columns: tuple[str, ...]
    rows: dict[tuple[str, str, int], list[list[str]]]


@dataclass
class CvmPackageScan:
    """What one package contributes: the best document per (issuer, scope, statement group, span), capital
    composition and the document index. Holds no archive bytes."""

    document_type: str
    year: int
    source_url: str
    candidates: dict[tuple[str, str, str, str, str], tuple[tuple[int, int, str], dict[str, float], dict[str, Any]]] = dataclass_field(default_factory=dict)
    capital: dict[tuple[str, str], tuple[int, dict[str, float | None]]] = dataclass_field(default_factory=dict)
    documents: dict[tuple[str, str, int], dict[str, str]] = dataclass_field(default_factory=dict)


def _level(code: str) -> int:
    return code.count(".")


def _is_capex_line(code: str, text: str) -> bool:
    """Investing outflows for property, plant and intangibles. DFC investing lines are free text, so this keeps to
    acquisition/addition wording and drops disposals, redemptions and investments in subsidiaries."""
    if not code.startswith("6.02.") or _level(code) != 2:
        return False
    if any(word in text for word in ("VENDA", "ALIENA", "RECEBIMENTO", "BAIXA", "RESGATE")):
        return False
    if not any(word in text for word in ("IMOBILIZADO", "INTANGIVE", "ATIVO FIXO")):
        return False
    return text.startswith(("AQUISI", "ADIC", "COMPRA", "INVESTIMENTO", "IMOBILIZADO", "INTANGIVE", "PAGAMENTO"))


INCOME_CONCEPTS = (
    _Concept("totalRevenue", lambda code, text: _level(code) == 1 and text.startswith(("RECEITA DE VENDA", "RECEITAS DE VENDA"))),
    _Concept("grossProfit", lambda code, text: _level(code) == 1 and text == "RESULTADO BRUTO"),
    _Concept("operatingIncome", lambda code, text: _level(code) == 1 and "ANTES DO RESULTADO FINANCEIRO E DOS TRIBUTOS" in text),
    _Concept("incomeBeforeTax", lambda code, text: _level(code) == 1 and text.startswith("RESULTADO ANTES DOS TRIBUTOS SOBRE O LUCRO")),
    _Concept("incomeTaxExpense", lambda code, text: _level(code) == 1 and text.startswith("IMPOSTO DE RENDA E CONTRIBUICAO SOCIAL")),
    _Concept(
        "consolidatedNetIncome",
        lambda code, text: _level(code) == 1
        and text.startswith(("LUCRO/PREJUIZO", "LUCRO OU PREJUIZO LIQUIDO"))
        and text.endswith("PERIODO"),
    ),
    _Concept("netIncome", lambda code, text: _level(code) == 2 and text.startswith("ATRIBUIDO") and "CONTROLADORA" in text),
)
VALUE_ADDED_CONCEPTS = (
    _Concept(
        "depreciationAndAmortization",
        lambda code, text: code.startswith("7.") and _level(code) == 2 and text.startswith("DEPRECIACAO"),
        magnitude=True,
    ),
)
CASH_FLOW_CONCEPTS = (
    _Concept(
        "totalCashFromOperatingActivities",
        lambda code, text: code == "6.01" and text.startswith("CAIXA LIQUIDO") and "OPERACION" in text,
    ),
    _Concept("capitalExpenditures", _is_capex_line, additive=True),
)
ASSET_CONCEPTS = (
    _Concept("totalAssets", lambda code, text: code == "1" and text.startswith("ATIVO TOTAL")),
    _Concept("cash", lambda code, text: code in {"1.01", "1.01.01"} and text.startswith("CAIXA E EQUIVALENTES DE CAIXA")),
    _Concept("shortTermInvestments", lambda code, text: code == "1.01.02" and text.startswith("APLICACOES FINANCEIRAS")),
)
LIABILITY_CONCEPTS = (
    _Concept("currentDebt", lambda code, text: code == "2.01.04" and text.startswith("EMPRESTIMOS E FINANCIAMENTOS")),
    _Concept("longTermDebt", lambda code, text: code == "2.02.01" and text.startswith("EMPRESTIMOS E FINANCIAMENTOS")),
    _Concept("totalEquity", lambda code, text: _level(code) == 1 and text.startswith("PATRIMONIO LIQUIDO")),
    _Concept(
        "nonControllingInterest",
        lambda code, text: _level(code) == 2 and text.startswith("PARTICIPACAO DOS ACIONISTAS NAO CONTROLADORES"),
    ),
)
# (statement file, group, concepts, flow statement). Consolidated files are read first: an issuer seen there is
# never read from the individual files of the same package.
STATEMENT_FILES: tuple[tuple[str, str, tuple[_Concept, ...], bool], ...] = (
    ("DRE", "income", INCOME_CONCEPTS, True),
    ("DVA", "value_added", VALUE_ADDED_CONCEPTS, True),
    ("DFC_MI", "cash_flow", CASH_FLOW_CONCEPTS, True),
    ("DFC_MD", "cash_flow", CASH_FLOW_CONCEPTS, True),
    ("BPA", "assets", ASSET_CONCEPTS, False),
    ("BPP", "liabilities", LIABILITY_CONCEPTS, False),
)

FLOW_GROUPS = frozenset(group for _, group, _, flow in STATEMENT_FILES if flow)

VintageSink = Callable[[CvmVintageBatch], Any]


def scan_cvm_package(
    package: CvmPackage,
    issuers: dict[str, dict[str, Any]],
    *,
    vintage_sink: VintageSink | None = None,
) -> CvmPackageScan:
    """Read one ITR/DFP archive once. ``vintage_sink`` receives the raw as-filed rows (levels <= 2) of each document
    of the mapped issuers, in batches of at most ``VINTAGE_FLUSH_ROWS`` rows."""
    document_type = package.document_type.upper()
    scan = CvmPackageScan(document_type, package.year, package.source_url)
    if not package.payload or not issuers:
        return scan
    prefix = f"{package.document_type.lower()}_cia_aberta"
    with zipfile.ZipFile(io.BytesIO(package.payload)) as archive:
        names = set(archive.namelist())
        index_name = f"{prefix}_{package.year}.csv"
        if index_name in names:
            scan.documents = _read_document_index(archive, index_name, issuers)
        consolidated: set[str] = set()
        for scope in ("con", "ind"):
            for statement, group, concepts, flow in STATEMENT_FILES:
                filename = f"{prefix}_{statement}_{scope}_{package.year}.csv"
                if filename not in names:
                    continue
                seen = _scan_statement(
                    archive,
                    filename,
                    issuers,
                    scan,
                    statement=f"{statement}_{scope}",
                    group=group,
                    concepts=concepts,
                    flow=flow,
                    scope=scope,
                    skip=consolidated if scope == "ind" else frozenset(),
                    vintage_sink=vintage_sink,
                )
                if scope == "con":
                    consolidated |= seen
        capital_name = f"{prefix}_composicao_capital_{package.year}.csv"
        if capital_name in names:
            _scan_share_capital(archive, capital_name, issuers, scan, vintage_sink=vintage_sink)
    return scan


def extract_cvm_official_statements(
    scans: Sequence[CvmPackageScan],
    *,
    issuers: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay payloads (one per symbol) with quarterized income, cash flow and balance from every scanned package.

    Per period the issuer's own filing wins over a later filing's comparative (the as-filed figure), then the highest
    version. Q4 is the DFP year minus the ITR nine months; a quarter whose prior cumulative period is missing is filled
    only by a standalone three-month row, never by a longer difference. EBITDA = EBIT (3.05, industrial layout) + D&A
    (DVA), only when both exist for the quarter."""
    candidates: dict[tuple[str, str, str, str, str], tuple[tuple[int, int, str], dict[str, float], dict[str, Any]]] = {}
    capital: dict[tuple[str, str], tuple[int, dict[str, float | None]]] = {}
    documents: dict[tuple[str, str, int], dict[str, str]] = {}
    for scan in scans:
        for key, candidate in scan.candidates.items():
            prior = candidates.get(key)
            if prior is None or candidate[0] > prior[0]:
                candidates[key] = candidate
        for key, entry in scan.capital.items():
            prior_capital = capital.get(key)
            if prior_capital is None or entry[0] >= prior_capital[0]:
                capital[key] = entry
        documents.update(scan.documents)

    by_issuer: dict[str, dict[tuple[str, str, str, str], tuple[dict[str, float], dict[str, Any]]]] = defaultdict(dict)
    for (tax_id, scope, group, start, end), (_, values, document) in candidates.items():
        by_issuer[tax_id][(scope, group, start, end)] = (values, document)

    output: list[dict[str, Any]] = []
    for tax_id, issuer in issuers.items():
        symbols = [str(symbol).upper() for symbol in issuer.get("symbols", []) if symbol]
        entries = by_issuer.get(tax_id)
        if not symbols or not entries:
            continue
        scope = "con" if any(key[0] == "con" for key in entries) else "ind"
        spans: dict[str, dict[tuple[str, str], dict[str, float]]] = defaultdict(dict)
        span_documents: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
        for (entry_scope, group, start, end), (values, document) in entries.items():
            if entry_scope == scope:
                spans[group][(start, end)] = values
                span_documents[group][(start, end)] = document

        income = _quarterly_flows(spans["income"])
        value_added = _quarterly_flows(spans["value_added"])
        cash = _quarterly_flows(spans["cash_flow"])
        quarterly_income = [_income_row(period, income[period], value_added.get(period, {})) for period in income]
        quarterly_cash_flow = [row for period in cash if (row := _cash_flow_row(period, cash[period]))]
        points: dict[str, dict[str, float]] = defaultdict(dict)
        for group in ("assets", "liabilities"):
            for (_, end), values in spans[group].items():
                if _is_quarter_end(end):
                    points[end].update(values)
        balances = {period: _balance_row(period, values, scope) for period, values in points.items()}

        periods = [*income, *cash, *balances]
        if not periods:
            continue
        latest_period = max(periods)
        quarterly_income = _recent(quarterly_income, latest_period)
        quarterly_cash_flow = _recent(quarterly_cash_flow, latest_period)
        quarterly_balance = _recent([row for row, _ in balances.values() if len(row) > 1], latest_period)
        company_ev_balance = balances[latest_period][1] if latest_period in balances else None

        share_period = max((period for (key_tax_id, period) in capital if key_tax_id == tax_id and period <= latest_period), default=None)
        share_composition = capital[(tax_id, share_period)][1] if share_period else None
        share_count = _number((share_composition or {}).get("total"))

        period_documents = _period_documents(span_documents, documents, tax_id)
        latest_document = period_documents.get(latest_period) or {}
        received_on = _iso_date(latest_document.get("receivedOn"))
        # CVM files a receipt DATE: the end of that day in Sao Paulo, as the vintages' accepted_at, so a reader never
        # sees the document before it could have existed. Never the wall clock: an unknown receipt stays unknown (and a
        # rerun does not append a new snapshot for it).
        published_at = datetime.combine(received_on, time.max, tzinfo=SAO_PAULO) if received_on else None
        for symbol in symbols:
            payload: dict[str, Any] = {
                "market": "B3",
                "symbol": symbol,
                "as_of": latest_period,
                "published_at": published_at.isoformat() if published_at else None,
                "source_name": f"{STATEMENTS_SOURCE_NAME} {'consolidado' if scope == 'con' else 'individual'}",
                "source_url": latest_document.get("sourceUrl"),
                "currency": "BRL",
                "unit": "BRL",
                "quarterlyIncome": quarterly_income,
                "quarterlyCashFlow": quarterly_cash_flow,
                "quarterlyBalance": quarterly_balance,
                "official_metrics": {
                    "cvmRegulatorId": issuer.get("regulator_id"),
                    "cvmCompanyName": issuer.get("company_name"),
                    "cvmTaxId": tax_id,
                    "statementScope": "consolidated" if scope == "con" else "individual",
                    "shareCapitalComposition": (
                        {"asOf": share_period, **share_composition} if share_composition else None
                    ),
                    "companyEvBalance": company_ev_balance,
                    "periodDocuments": period_documents,
                },
            }
            if share_count and share_count > 0:
                payload["sharesOutstanding"] = share_count
            output.append(payload)
    return output


def _read_document_index(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
) -> dict[tuple[str, str, int], dict[str, str]]:
    output: dict[tuple[str, str, int], dict[str, str]] = {}
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            if tax_id not in issuers:
                continue
            key = (tax_id, str(row.get("DT_REFER") or "")[:10], _integer(row.get("VERSAO")))
            output[key] = {
                "DT_RECEB": str(row.get("DT_RECEB") or "")[:10],
                "ID_DOC": str(row.get("ID_DOC") or ""),
                "CATEG_DOC": str(row.get("CATEG_DOC") or ""),
                "LINK_DOC": str(row.get("LINK_DOC") or ""),
            }
    return output


def _scan_statement(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
    scan: CvmPackageScan,
    *,
    statement: str,
    group: str,
    concepts: tuple[_Concept, ...],
    flow: bool,
    scope: str,
    skip: set[str] | frozenset[str],
    vintage_sink: VintageSink | None,
) -> set[str]:
    seen: set[str] = set()
    hits: dict[tuple[str, str, int, str, str], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    vintages = _VintageBuffer(scan, issuers, statement, VINTAGE_COLUMNS, vintage_sink)
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            if tax_id not in issuers or tax_id in skip:
                continue
            seen.add(tax_id)
            refer = str(row.get("DT_REFER") or "")[:10]
            version = _integer(row.get("VERSAO"))
            code = str(row.get("CD_CONTA") or "")
            if _level(code) <= VINTAGE_MAX_LEVEL:
                vintages.add((tax_id, refer, version), row)
            if _fold(row.get("MOEDA")) not in {"", "REAL"}:
                continue
            text = _fold(row.get("DS_CONTA"))
            matched = [concept for concept in concepts if concept.matches(code, text)]
            end = str(row.get("DT_FIM_EXERC") or "")[:10]
            value = _scaled_value(row.get("VL_CONTA"), row.get("ESCALA_MOEDA"))
            if not matched or not end or value is None:
                continue
            start = str(row.get("DT_INI_EXERC") or "")[:10] if flow else ""
            for concept in matched:
                hits[(tax_id, refer, version, start, end)][concept.field][code] = abs(value) if concept.magnitude else value
    for (tax_id, refer, version, start, end), fields in hits.items():
        values = _resolve_concepts(fields, concepts)
        if not values:
            continue
        key = (tax_id, scope, group, start, end)
        rank = (int(refer == end), version, refer)
        prior = scan.candidates.get(key)
        if prior is None or rank > prior[0]:
            scan.candidates[key] = (
                rank,
                values,
                {"document": scan.document_type, "referenceDate": refer, "version": version, "sourceUrl": scan.source_url},
            )
    vintages.flush()
    return seen


class _VintageBuffer:
    def __init__(
        self,
        scan: CvmPackageScan,
        issuers: dict[str, dict[str, Any]],
        statement: str,
        columns: tuple[str, ...],
        sink: VintageSink | None,
    ) -> None:
        self.scan = scan
        self.issuers = issuers
        self.statement = statement
        self.columns = columns
        self.sink = sink
        self.rows: dict[tuple[str, str, int], list[list[str]]] = defaultdict(list)
        self.count = 0

    def add(self, document: tuple[str, str, int], row: dict[str, Any]) -> None:
        if self.sink is None:
            return
        self.rows[document].append([str(row.get(column) or "") for column in self.columns])
        self.count += 1
        if self.count >= VINTAGE_FLUSH_ROWS:
            self.flush()

    def flush(self) -> None:
        if self.sink is not None and self.rows:
            self.sink(CvmVintageBatch(self.scan, self.issuers, self.statement, self.columns, dict(self.rows)))
        self.rows = defaultdict(list)
        self.count = 0


def _resolve_concepts(fields: dict[str, dict[str, float]], concepts: tuple[_Concept, ...]) -> dict[str, float]:
    values: dict[str, float] = {}
    for concept in concepts:
        accounts = fields.get(concept.field)
        if not accounts:
            continue
        if concept.additive:
            values[concept.field] = sum(accounts.values())
        elif len(accounts) == 1:  # two accounts answering one concept is a layout we do not know: never pick one
            values[concept.field] = next(iter(accounts.values()))
    return values


def _scan_share_capital(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
    scan: CvmPackageScan,
    *,
    vintage_sink: VintageSink | None,
) -> None:
    vintages = _VintageBuffer(scan, issuers, "composicao_capital", CAPITAL_VINTAGE_COLUMNS, vintage_sink)
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            if tax_id not in issuers:
                continue
            period = str(row.get("DT_REFER") or "")[:10]
            version = _integer(row.get("VERSAO"))
            vintages.add((tax_id, period, version), row)
            total = _net_share_count(row.get("QT_ACAO_TOTAL_CAP_INTEGR"), row.get("QT_ACAO_TOTAL_TESOURO"))
            if not period or total is None:
                continue
            prior = scan.capital.get((tax_id, period))
            if prior is None or version >= prior[0]:
                scan.capital[(tax_id, period)] = (
                    version,
                    {
                        "ordinary": _net_share_count(row.get("QT_ACAO_ORDIN_CAP_INTEGR"), row.get("QT_ACAO_ORDIN_TESOURO")),
                        "preferred": _net_share_count(row.get("QT_ACAO_PREF_CAP_INTEGR"), row.get("QT_ACAO_PREF_TESOURO")),
                        "total": total,
                    },
                )
    vintages.flush()


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _quarter_end(year: int, month: int) -> date:
    return date(year, month, QUARTER_END_DAYS[month])


def _is_quarter_end(value: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return QUARTER_END_DAYS.get(parsed.month) == parsed.day


def _quarterly_flows(spans: dict[tuple[str, str], dict[str, float]]) -> dict[str, dict[str, float]]:
    """Quarter values from calendar-year cumulative spans (Q = YTD(t) - YTD(t - 1 quarter); Q1 = YTD). A standalone
    three-month span fills only what the difference cannot give; fiscal years not starting on 1 January are skipped,
    as in the legacy ITR reader."""
    output: dict[str, dict[str, float]] = {}
    for end in sorted({end for _, end in spans}):
        if not _is_quarter_end(end):
            continue
        end_date = date.fromisoformat(end)
        year_start = date(end_date.year, 1, 1).isoformat()
        quarter: dict[str, float] = {}
        ytd = spans.get((year_start, end))
        if ytd is not None:
            if end_date.month == 3:
                quarter = dict(ytd)
            else:
                prior = spans.get((year_start, _quarter_end(end_date.year, end_date.month - 3).isoformat()))
                if prior is not None:
                    quarter = {name: value - prior[name] for name, value in ytd.items() if name in prior}
        standalone = spans.get((date(end_date.year, end_date.month - 2, 1).isoformat(), end))
        for name, value in (standalone or {}).items():
            quarter.setdefault(name, value)
        if quarter:
            output[end] = quarter
    return output


def _income_row(period: str, income: dict[str, float], value_added: dict[str, float]) -> dict[str, Any]:
    row: dict[str, Any] = {"date": period, **income}
    if "netIncome" not in row and "consolidatedNetIncome" in row:
        row["netIncome"] = row["consolidatedNetIncome"]
    row.pop("consolidatedNetIncome", None)
    amortization = value_added.get("depreciationAndAmortization")
    if amortization is not None:
        row["depreciationAndAmortization"] = amortization
        if row.get("operatingIncome") is not None:
            row["ebitda"] = row["operatingIncome"] + amortization
    return row


def _cash_flow_row(period: str, values: dict[str, float]) -> dict[str, Any] | None:
    row: dict[str, Any] = {"date": period, **values}
    capex = row.get("capitalExpenditures")
    if capex is not None and capex > 0:  # a net inflow is not capex: the investing lines did not classify cleanly
        row.pop("capitalExpenditures")
    operating = row.get("totalCashFromOperatingActivities")
    if operating is not None and row.get("capitalExpenditures") is not None:
        row["freeCashFlow"] = operating + row["capitalExpenditures"]
    return row if len(row) > 1 else None


def _balance_row(period: str, values: dict[str, float], scope: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cash = values.get("cash")
    short_term = values.get("shortTermInvestments")
    current_debt = values.get("currentDebt")
    long_term_debt = values.get("longTermDebt")
    row: dict[str, Any] = {"date": period}
    if values.get("totalAssets") is not None:
        row["totalAssets"] = values["totalAssets"]
    if cash is not None:
        row["cash"] = cash
        row["cashAndShortTermInvestments"] = cash + (short_term or 0.0)
    if current_debt is not None or long_term_debt is not None:
        row["shortLongTermDebtTotal"] = (current_debt or 0.0) + (long_term_debt or 0.0)
    equity = values.get("totalEquity")
    if equity is not None:
        row["totalEquity"] = equity
        minority = values.get("nonControllingInterest")
        if minority is not None:
            row["totalStockholderEquity"] = equity - minority
        elif scope == "ind":  # individual statements carry no non-controlling interest
            row["totalStockholderEquity"] = equity
    ev_balance = None
    if cash is not None and short_term is not None and current_debt is not None and long_term_debt is not None:
        ev_balance = {"asOf": period, "totalCash": cash + short_term, "totalDebt": current_debt + long_term_debt}
    return row, ev_balance


def _recent(rows: list[dict[str, Any]], latest_period: str) -> list[dict[str, Any]]:
    ordered = sorted((row for row in rows if row["date"] <= latest_period), key=lambda row: row["date"], reverse=True)
    return ordered[:STATEMENT_HISTORY_QUARTERS]


def _period_documents(
    span_documents: dict[str, dict[tuple[str, str], dict[str, Any]]],
    documents: dict[tuple[str, str, int], dict[str, str]],
    tax_id: str,
) -> dict[str, dict[str, Any]]:
    """The filing behind each period: the income statement's cumulative row, else its standalone row, else the
    balance sheet. ``receivedOn`` is the CVM receipt date (DT_RECEB) of that version. ``contributing`` lists EVERY
    document version a figure of the period was read from — each statement (DRE, DVA, DFC, balance sheet) ending on it
    and, for the flows, the earlier cumulative of the same year it was differenced against — with its own receipt date,
    so the overlay's receipt guard can check all of them."""
    receipt = {key: value.get("DT_RECEB") or None for key, value in documents.items() if key[0] == tax_id}

    def stamped(document: dict[str, Any]) -> dict[str, Any]:
        return {**document, "receivedOn": receipt.get((tax_id, document["referenceDate"], document["version"]))}

    chosen: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    for group_rank, group in enumerate(("income", "cash_flow", "assets", "liabilities")):
        for (start, end), document in span_documents.get(group, {}).items():
            if not _is_quarter_end(end):
                continue
            priority = (group_rank, 0 if start in {"", f"{end[:4]}-01-01"} else 1)
            if end not in chosen or priority < chosen[end][0]:
                chosen[end] = (priority, document)
    output: dict[str, dict[str, Any]] = {}
    for end, (_, document) in sorted(chosen.items()):
        end_date = date.fromisoformat(end)
        prior = _quarter_end(end_date.year, end_date.month - 3).isoformat() if end_date.month > 3 else None
        contributing: dict[tuple[str, str, int], dict[str, Any]] = {}
        for group, spans in span_documents.items():
            for (start, span_end), item in spans.items():
                differenced = prior is not None and group in FLOW_GROUPS and start == f"{end[:4]}-01-01" and span_end == prior
                if span_end == end or differenced:
                    contributing[(item["document"], item["referenceDate"], item["version"])] = item
        output[end] = {
            **stamped(document),
            "contributing": [
                {key: value for key, value in stamped(item).items() if key in {"document", "referenceDate", "version", "receivedOn"}}
                for _, item in sorted(contributing.items())
            ],
        }
    return output
