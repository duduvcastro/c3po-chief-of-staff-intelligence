from __future__ import annotations

import csv
import io
import math
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any


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
        if cash is not None:
            balance["cash"] = cash
            balance["cashAndShortTermInvestments"] = cash + (short_term or 0.0)
        if current_debt is not None or long_term_debt is not None:
            balance["shortLongTermDebtTotal"] = (current_debt or 0.0) + (long_term_debt or 0.0)
        share_count = shares.get(tax_id, {}).get(latest_period)
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
            if _fold(row.get("ORDEM_EXERC")) != "ULTIMO":
                continue
            period = str(row.get(period_field) or row.get("DT_REFER") or "")[:10]
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


def _read_share_capital(
    archive: zipfile.ZipFile,
    filename: str,
    issuers: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    if filename not in archive.namelist():
        return {}
    selected: dict[tuple[str, str], tuple[int, float]] = {}
    with archive.open(filename) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline=""), delimiter=";")
        for row in reader:
            tax_id = str(row.get("CNPJ_CIA") or "")
            if tax_id not in issuers:
                continue
            period = str(row.get("DT_REFER") or "")[:10]
            total = _number(row.get("QT_ACAO_TOTAL_CAP_INTEGR"))
            treasury = _number(row.get("QT_ACAO_TOTAL_TESOURO")) or 0.0
            if not period or total is None:
                continue
            version = _integer(row.get("VERSAO"))
            key = (tax_id, period)
            prior = selected.get(key)
            if prior is None or version >= prior[0]:
                selected[key] = (version, max(total - treasury, 0.0))
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (tax_id, period), (_, value) in selected.items():
        output[tax_id][period] = value
    return dict(output)


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
