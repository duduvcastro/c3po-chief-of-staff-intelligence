import logging
import math
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from threading import Lock, RLock
from typing import Any
from zoneinfo import ZoneInfo

from ..config import Settings
from ..database import Database
from ..schemas import B3Candidate, B3CandidateResponse, MatrixPowerItem, MatrixPowerResponse
from ..investor_relations import normalize_company_name
from ..official_fundamentals import apply_official_fundamentals_map
from .brapi import BrapiClient
from .eodhd import EodhdClient
from .http import JsonHttpClient
from .sector_taxonomy import SECTOR_TAXONOMY_VERSION, canonical_b3_company_name, resolve_b3_sector
from ..valuation_policy import (
    C3PO_VALUATION_POLICY,
    METHODOLOGY_KEY,
    METHODOLOGY_NAME,
    METHODOLOGY_VERSION,
)


logger = logging.getLogger(__name__)

UNIVERSE_LIMIT = 350
CATALOG_FETCH_LIMIT = 700
BATCH_SIZE = 20
CACHE_MINUTES = 15
MIN_PRICE = 1.0
MIN_MARKET_CAP = 750_000_000
MIN_ADTV_90D = 5_000_000
MIN_HISTORY_DAYS = 40
TP_UPSIDE_PREMIUM = 0.06
MAX_ENTRY_DISTANCE = 15.0
MIN_VALUATION_CONFIDENCE = 70.0
MAX_METHOD_DISPERSION = 45.0
MIN_TP_VALIDATION_SCORE = 65.0
MIN_TP_SOURCE_AGREEMENT = 55.0
MIN_TP_SOURCE_COMPARISONS = 3
MIN_TP_ANALYSTS = 2
MAX_TP_CONSENSUS_GAP = 40.0
MAX_FUNDAMENTALS_AGE_DAYS = 180
PROVISIONAL_MIN_VALUATION_CONFIDENCE = 55.0
PROVISIONAL_MAX_METHOD_DISPERSION = 60.0
PROVISIONAL_MIN_SOURCE_AGREEMENT = 45.0
PROVISIONAL_MIN_SOURCE_COMPARISONS = 2
PROVISIONAL_MAX_FUNDAMENTALS_AGE_DAYS = 270
MAX_VALIDATED_TP_UPSIDE = 200.0
ABSOLUTE_LOW_RISK_LIMIT = 40.0
MATRIX_QUOTE_CACHE_SECONDS = 45
MATRIX_REFRESH_SECONDS = 60
MATRIX_PROVIDER_DELAY_MINUTES = 5
INSIDER_GOVERNANCE_LOOKBACK_DAYS = 180
INSIDER_SIGNAL_MIN_TRANSACTIONS_FOR_FULL_WEIGHT = 4
INSIDER_GOVERNANCE_MAX_SWING = 20.0
DISCLOSURE_GOVERNANCE_MAX_SWING = 12.0
DISCLOSURE_MATERIALITY_WEIGHTS = {"high": 1.0, "medium": 0.5, "low": 0.2}
PERSISTED_STATE_POLL_SECONDS = 15
AUXILIARY_CACHE_HOURS = 18
CALIBRATION_HORIZON_DAYS = 90
CALIBRATION_MIN_GLOBAL_SAMPLES = 40
CALIBRATION_MIN_PROFILE_SAMPLES = 15
CALIBRATION_FACTOR_LIMIT = 0.05
CONSENSUS_WEIGHT = 0.35
BCB_SELIC_SERIES_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1"
LATEST_COPOM_SELIC = 0.14
LATEST_COPOM_DECISION_AT = datetime(2026, 8, 5, 18, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
LATEST_COPOM_EFFECTIVE_DATE = date(2026, 8, 6)
SELIC_GOVERNOR_STALE_WARNING_DAYS = 50
# Data-source audit (2026-08-20): Brapi Pro's Tesouro Direto endpoints were
# never used at all, even though they're included in the plan we already
# pay for. A genuine, independently-observed market yield (unlike Selic,
# which is a policy rate) -- used purely as a divergence cross-check, not
# blended into the actual risk-free rate, since a short policy rate and a
# long bond yield normally differ by a real term premium and forcing them
# together would be its own source of error.
SELIC_MARKET_YIELD_DIVERGENCE_WARNING = 0.05


# Issuer-published consensus takes precedence when it is more broadly covered
# than the normalized provider feeds. Keep its date and source in the row so
# the nightly audit can age or replace it explicitly.
OFFICIAL_CONSENSUS_OVERRIDES: dict[str, dict[str, Any]] = {
    "PETR3": {
        "target_price": 51.37,
        "analyst_count": 10,
        "as_of": "2026-05-13",
        "max_age_days": 180,
        "source": "Petrobras RI",
        "source_url": "https://www.investidorpetrobras.com.br/servicos-ao-investidor/cobertura-de-analistas/",
    },
    "PETR4": {
        "target_price": 52.93,
        "analyst_count": 12,
        "as_of": "2026-05-13",
        "max_age_days": 180,
        "source": "Petrobras RI",
        "source_url": "https://www.investidorpetrobras.com.br/servicos-ao-investidor/cobertura-de-analistas/",
    },
}


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def positive(value: Any) -> float | None:
    result = number(value)
    return result if result is not None and result > 0 else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def median(values: list[float], fallback: float) -> float:
    clean = [value for value in values if value > 0 and math.isfinite(value)]
    return statistics.median(clean) if clean else fallback


def percentile(values: list[float], fraction: float) -> float:
    clean = sorted(value for value in values if value > 0 and math.isfinite(value))
    if not clean:
        return 0.0
    position = (len(clean) - 1) * clamp(fraction, 0.0, 1.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def signed_percentile(values: list[float], fraction: float, fallback: float = 0.0) -> float:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return fallback
    position = (len(clean) - 1) * clamp(fraction, 0.0, 1.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def robust_weighted_mean(values: dict[str, float], weights: dict[str, float]) -> float:
    usable = {name: value for name, value in values.items() if value > 0 and weights.get(name, 0.0) > 0}
    if not usable:
        return 0.0
    center = statistics.median(usable.values())
    normalized = {name: clamp(value, center * 0.70, center * 1.30) for name, value in usable.items()}
    total_weight = sum(weights[name] for name in normalized)
    return sum(value * weights[name] for name, value in normalized.items()) / total_weight


def batches(values: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


class B3ScreenerService:
    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        self._lock = RLock()
        self._cached: B3CandidateResponse | None = None
        self._cache_expires_at: datetime | None = None
        self._matrix_lock = Lock()
        self._matrix_rows: list[dict[str, Any]] = []
        self._matrix_basis_at: datetime | None = None
        self._matrix_macro: dict[str, float] = {"selic": LATEST_COPOM_SELIC, "ipca12m": 0.045}
        self._matrix_universe_size = 0
        self._matrix_coverage_audit: dict[str, int] = {}
        self._matrix_sector_audit: list[dict[str, Any]] = []
        self._matrix_cached: MatrixPowerResponse | None = None
        self._matrix_cache_expires_at: datetime | None = None
        self._eodhd_fundamentals: dict[str, dict[str, Any]] = {}
        self._eodhd_cache_expires_at: datetime | None = None
        self._eodhd_history: dict[str, dict[str, float]] = {}
        self._eodhd_history_cache_expires_at: datetime | None = None
        self._persisted_checked_at: datetime | None = None
        self._calibration_factors: dict[str, float] = {}

    def screen(self, *, refresh: bool = False) -> B3CandidateResponse:
        if not refresh:
            self._hydrate_persisted_state()
            if self._cached:
                return self._cached
        with self._lock:
            if not refresh:
                self._hydrate_persisted_state(force=True)
                if self._cached:
                    return self._cached
            now = datetime.now(timezone.utc)
            self._load_calibration_factors()
            response = self._build(now)
            self._cached = response
            self._cache_expires_at = None
            return response

    def matrix(self) -> MatrixPowerResponse:
        self._hydrate_persisted_state()
        now = datetime.now(timezone.utc)
        if not self._matrix_rows:
            self.screen(refresh=False)

        with self._matrix_lock:
            now = datetime.now(timezone.utc)
            if self._matrix_cached and self._matrix_cache_expires_at and now < self._matrix_cache_expires_at:
                return self._matrix_cached
            response = self._build_matrix(now)
            self._matrix_cached = response
            self._matrix_cache_expires_at = now + timedelta(seconds=MATRIX_QUOTE_CACHE_SECONDS)
            return response

    def valuation_for(self, symbol: str, *, build_if_missing: bool = False) -> dict[str, Any] | None:
        """Return the shared valuation basis, optionally building an on-demand B3 valuation."""
        clean = symbol.strip().upper().removesuffix(".SA")
        self._hydrate_persisted_state()
        if not self._matrix_rows:
            self.screen(refresh=False)
        row = next((item for item in self._matrix_rows if item.get("symbol") == clean), None)
        latest_ir = self.database.latest_valuation_ir_events([clean], market="B3").get(clean)
        latest_ir_at = max(
            (
                value for value in (
                    latest_ir.get("published_at") if latest_ir else None,
                    latest_ir.get("collected_at") if latest_ir else None,
                ) if isinstance(value, datetime)
            ),
            default=None,
        )
        row_is_current = bool(
            row
            and (
                latest_ir_at is None
                or self._matrix_basis_at is None
                or latest_ir_at <= self._matrix_basis_at
            )
        )
        if row_is_current:
            return dict(row)
        if row and build_if_missing:
            self.refresh_symbols([clean])
            refreshed = next((item for item in self._matrix_rows if item.get("symbol") == clean), None)
            return dict(refreshed) if refreshed else None

        targeted = self.database.latest_analysis_snapshot("security_valuation", clean)
        targeted_inputs = targeted.get("inputs") if targeted else None
        targeted_outputs = targeted.get("outputs") if targeted else None
        targeted_row = targeted_outputs.get("row") if isinstance(targeted_outputs, dict) else None
        targeted_at = targeted.get("published_at") if targeted else None
        current_day = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        snapshot_day = (
            targeted_at.astimezone(ZoneInfo("America/Sao_Paulo")).date()
            if isinstance(targeted_at, datetime) and targeted_at.tzinfo
            else targeted_at.date() if isinstance(targeted_at, datetime) else None
        )
        snapshot_is_current = bool(
            isinstance(targeted_inputs, dict)
            and targeted_inputs.get("methodology_version") == METHODOLOGY_VERSION
            and targeted_inputs.get("sector_taxonomy_version") == SECTOR_TAXONOMY_VERSION
            and isinstance(targeted_row, dict)
            and snapshot_day == current_day
            and (
                not isinstance(latest_ir_at, datetime)
                or not isinstance(targeted_at, datetime)
                or latest_ir_at <= targeted_at
            )
        )
        if snapshot_is_current:
            return dict(targeted_row)
        return self._build_targeted_valuation(clean) if build_if_missing else None

    def refresh_symbols(self, symbols: list[str]) -> dict[str, list[str]]:
        """Revalue affected B3 issuers and atomically republish shared snapshots."""
        clean_symbols = list(dict.fromkeys(
            symbol.strip().upper().removesuffix(".SA") for symbol in symbols if symbol.strip()
        ))
        if not clean_symbols:
            return {"updated": [], "targeted_only": [], "missing": []}
        with self._lock:
            self._hydrate_persisted_state(force=True)
            if not self._matrix_rows:
                self.screen(refresh=True)
            existing_symbols = {str(row.get("symbol") or "") for row in self._matrix_rows}
            for symbol in clean_symbols:
                self._eodhd_fundamentals.pop(symbol, None)
                self._eodhd_history.pop(symbol, None)

            updated: list[str] = []
            targeted_only: list[str] = []
            missing: list[str] = []
            replacements: dict[str, dict[str, Any]] = {}
            existing_rows = {
                str(row.get("symbol") or ""): dict(row)
                for row in self._matrix_rows
                if row.get("symbol")
            }
            latest_events = self.database.latest_valuation_ir_events(clean_symbols, market="B3")
            for symbol in clean_symbols:
                row = self._build_targeted_valuation(symbol)
                if not row:
                    preserved = existing_rows.get(symbol)
                    if preserved:
                        preserved.update(self._ir_freshness(
                            preserved.get("fundamentals_as_of"),
                            latest_events.get(symbol),
                        ))
                        replacements[symbol] = preserved
                        targeted_only.append(symbol)
                    else:
                        missing.append(symbol)
                    continue
                if symbol in existing_symbols:
                    replacements[symbol] = row
                    updated.append(symbol)
                else:
                    targeted_only.append(symbol)

            if replacements:
                self._matrix_rows = [
                    dict(replacements.get(str(row.get("symbol") or ""), row))
                    for row in self._matrix_rows
                ]
                generated_at = datetime.now(timezone.utc)
                self._matrix_basis_at = generated_at
                self._matrix_cached = None
                self._matrix_cache_expires_at = None
                response = self._candidate_response(
                    generated_at,
                    self._matrix_universe_size or len(self._matrix_rows),
                    self._matrix_rows,
                    self._matrix_macro,
                )
                self._cached = response
                self._persist_snapshot(response, self._matrix_macro)
            return {"updated": updated, "targeted_only": targeted_only, "missing": missing}

    def _build_targeted_valuation(self, symbol: str) -> dict[str, Any] | None:
        """Value a requested B3 security without applying Candidate/Matrix listing gates."""
        payload = self.http.get_json(
            f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/tickers",
            params={"search": symbol, "type": "stock", "subType": "stock", "limit": 10},
            headers=self._headers(),
        )
        catalog = self._targeted_catalog(payload.get("results", []), symbol)
        if not catalog:
            return None

        quotes = self._optional_quotes([symbol])
        if symbol not in quotes and self.settings.eodhd_api_token:
            quotes.update(self._eodhd_quote_map([symbol]))
        statistics_map = self._optional_fundamental_map("statistics", [symbol])
        financial_map = self._optional_fundamental_map("financial-data", [symbol])
        historical_map = self._optional_historical_map([symbol])
        eodhd_map = self._eodhd_fundamental_map([symbol]) if self.settings.eodhd_api_token else {}
        reference_symbols = self._targeted_consensus_reference_symbols(symbol)
        reference_quotes = self._optional_quotes(reference_symbols)
        reference_financial = (
            self._fundamental_map("financial-data", list(reference_quotes))
            if reference_quotes else {}
        )
        reference_eodhd = (
            self._eodhd_fundamental_map(list(reference_quotes))
            if self.settings.eodhd_api_token and reference_quotes else {}
        )
        consensus_references = self._consensus_reference_rows(
            reference_quotes,
            reference_financial,
            reference_eodhd,
        )
        if historical_map.get(symbol, {}).get("history_days", 0) < MIN_HISTORY_DAYS:
            fallback = self._eodhd_historical_map([symbol]).get(symbol)
            if fallback:
                historical_map[symbol] = fallback

        macro = dict(self._matrix_macro or self._macro_context())
        rows = self._prepare_rows(
            catalog,
            quotes,
            statistics_map,
            financial_map,
            historical_map,
            macro,
            eodhd_map,
            consensus_references,
            enforce_screening_gates=False,
            enforce_quality_gate=False,
        )
        if not rows:
            return None

        row = rows[0]
        comparison_rows = [dict(item) for item in self._matrix_rows if item.get("symbol") != symbol]
        self._value_row(row, self._sector_medians([*comparison_rows, row]), macro)
        if not positive(row.get("our_tp")) or not positive(row.get("buy_in")):
            return None
        row["valuation_scope"] = "on_demand_outside_screening_gates"
        self.database.reconcile_ir_results(
            {symbol: row.get("fundamentals_as_of")},
            market="B3",
        )
        basis = self.database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
        methodology_id = basis.get("methodology_version_id") if basis else None
        generated_at = datetime.now(timezone.utc)
        if methodology_id:
            self.database.save_analysis_snapshot(
                "security_valuation",
                symbol,
                methodology_id,
                {
                    "methodology_version": METHODOLOGY_VERSION,
                    "sector_taxonomy_version": SECTOR_TAXONOMY_VERSION,
                    "source": self._source_label(),
                    "scope": "on_demand_outside_screening_gates",
                },
                self._json_safe({"row": row}),
                generated_at,
            )
        return dict(row)

    def _hydrate_persisted_state(self, *, force: bool = False) -> None:
        if not self.database.database_url:
            return
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._persisted_checked_at
            and now - self._persisted_checked_at < timedelta(seconds=PERSISTED_STATE_POLL_SECONDS)
        ):
            return
        self._persisted_checked_at = now

        candidate = self.database.latest_analysis_snapshot("candidate_screen", "B3_TOP_10")
        candidate_outputs = candidate.get("outputs") if candidate else None
        candidate_version = candidate_outputs.get("methodology_version") if isinstance(candidate_outputs, dict) else None
        if candidate and candidate_version == METHODOLOGY_VERSION and (
            not self._cached or candidate["published_at"] > self._cached.generated_at
        ):
            try:
                self._cached = B3CandidateResponse.model_validate(candidate_outputs)
            except (TypeError, ValueError):
                pass

        basis = self.database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
        basis_inputs = basis.get("inputs") if basis else None
        basis_version = basis_inputs.get("methodology_version") if isinstance(basis_inputs, dict) else None
        if basis and basis_version == METHODOLOGY_VERSION and (not self._matrix_basis_at or basis["published_at"] > self._matrix_basis_at):
            output = basis.get("outputs") or {}
            rows = output.get("rows") if isinstance(output, dict) else None
            if isinstance(rows, list):
                self._matrix_rows = [dict(row) for row in rows if isinstance(row, dict)]
                self._matrix_basis_at = basis["published_at"]
                self._matrix_macro = dict(output.get("macro") or self._matrix_macro)
                self._matrix_universe_size = int(output.get("universe_size") or len(self._matrix_rows))
                self._matrix_coverage_audit = dict(output.get("coverage_audit") or {})
                self._matrix_cached = None
                self._matrix_cache_expires_at = None
        self._load_calibration_factors()

    def _load_calibration_factors(self) -> None:
        snapshot = self.database.latest_analysis_snapshot("valuation_calibration", "B3_POWER_MODEL")
        output = snapshot.get("outputs") if snapshot else None
        factors = output.get("factors") if isinstance(output, dict) else None
        if isinstance(factors, dict):
            self._calibration_factors = {
                str(profile): clamp(float(factor), 1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT)
                for profile, factor in factors.items()
                if number(factor) is not None
            }

    def _build(self, generated_at: datetime) -> B3CandidateResponse:
        if not self.settings.brapi_token:
            raise RuntimeError("Brapi credential is not configured")

        run_id = self.database.begin_ingestion_run(
            "brapi",
            "Brapi",
            "market_data",
            {"operation": "b3_top_10", "universe_limit": UNIVERSE_LIMIT, "methodology_version": METHODOLOGY_VERSION},
        )
        try:
            catalog_payload = self.http.get_json(
                f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/tickers",
                params={
                    "type": "stock",
                    "subType": "stock",
                    "sortBy": "volume",
                    "sortOrder": "desc",
                    "limit": CATALOG_FETCH_LIMIT,
                },
                headers=self._headers(),
            )
            raw_catalog = [item for item in catalog_payload.get("results", []) if isinstance(item, dict)]
            fractional_count = sum(
                str(item.get("symbol") or "").upper().endswith("F")
                for item in raw_catalog
            )
            catalog = [
                item for item in raw_catalog
                if not str(item.get("symbol") or "").upper().endswith("F")
            ][:UNIVERSE_LIMIT]
            self.database.register_ir_securities([
                {
                    "market": "B3",
                    "symbol": str(item.get("symbol", "")).upper(),
                    "company_name": str(item.get("name") or item.get("longName") or item.get("symbol") or ""),
                    "name_key": normalize_company_name(str(item.get("name") or item.get("longName") or item.get("symbol") or "")),
                    "exchange": "B3",
                }
                for item in catalog if item.get("symbol")
            ])
            symbols = [str(item.get("symbol", "")).upper() for item in catalog if item.get("symbol")]
            quotes = self._quotes(symbols)
            self.database.save_quotes("brapi", run_id, list(quotes.values()))
            statistics_map = self._fundamental_map("statistics", symbols)
            financial_map = self._fundamental_map("financial-data", symbols)
            historical_map = self._historical_map(symbols)
            eodhd_map: dict[str, dict[str, Any]] = {}
            if self.settings.eodhd_api_token and symbols:
                # EODHD must run before the quality gate so it can rescue missing
                # Brapi fields instead of only confirming rows that already passed.
                eodhd_map = self._eodhd_fundamental_map(symbols)
                missing_history = [
                    symbol for symbol in symbols
                    if historical_map.get(symbol, {}).get("history_days", 0) < MIN_HISTORY_DAYS
                ]
                for symbol, fallback in self._eodhd_historical_map(missing_history).items():
                    if fallback.get("history_days", 0) > historical_map.get(symbol, {}).get("history_days", 0):
                        historical_map[symbol] = fallback
            self.database.reconcile_ir_results(
                {
                    symbol: fundamentals.get("financialsAsOf") or fundamentals.get("updated_at")
                    for symbol, fundamentals in eodhd_map.items()
                },
                market="B3",
            )
            macro = self._macro_context()
            base_rows = self._prepare_rows(
                catalog,
                quotes,
                statistics_map,
                financial_map,
                historical_map,
                macro,
                eodhd_map,
            )
            reference_symbols = self._consensus_reference_symbols(catalog, base_rows)
            reference_quotes = self._quotes(reference_symbols) if reference_symbols else {}
            reference_financial = self._fundamental_map("financial-data", list(reference_quotes)) if reference_quotes else {}
            if self.settings.eodhd_api_token and reference_quotes:
                eodhd_map.update(self._eodhd_fundamental_map(list(reference_quotes)))
            consensus_references = self._consensus_reference_rows(reference_quotes, reference_financial, eodhd_map)
            coverage_audit: dict[str, int] = {}
            rows = self._prepare_rows(
                catalog,
                quotes,
                statistics_map,
                financial_map,
                historical_map,
                macro,
                eodhd_map,
                consensus_references,
                coverage_audit=coverage_audit,
            )
            sector_audit, sector_counts = self._sector_coverage_audit(catalog, eodhd_map)
            coverage_audit.update(sector_counts)
            coverage_audit["fractional_tickers_excluded"] = fractional_count
            self._matrix_sector_audit = sector_audit
            self.database.reconcile_ir_results(
                {row["symbol"]: row.get("fundamentals_as_of") for row in rows},
                market="B3",
            )
            self._matrix_rows = [dict(row) for row in rows]
            self._matrix_basis_at = generated_at
            self._matrix_macro = dict(macro)
            self._matrix_universe_size = len(symbols)
            self._matrix_coverage_audit = coverage_audit
            self._matrix_cached = None
            self._matrix_cache_expires_at = None
            self.database.finish_ingestion_run(run_id, "succeeded", len(symbols), len(quotes))
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", 0, 0, str(exc))
            raise

        response = self._candidate_response(generated_at, len(symbols), rows, macro)
        self._persist_snapshot(response, macro)
        return response

    def _candidate_response(
        self,
        generated_at: datetime,
        universe_size: int,
        rows: list[dict[str, Any]],
        macro: dict[str, float],
    ) -> B3CandidateResponse:
        items, tp_upside_cutoff, risk_cutoff = self._rank(rows, macro)
        return B3CandidateResponse(
            source=self._source_label(),
            methodology=METHODOLOGY_NAME,
            methodology_version=METHODOLOGY_VERSION,
            universe_size=universe_size,
            eligible_count=len(rows),
            generated_at=generated_at,
            items=items,
            criteria={
                "ranking": "C3PO TP upside, descending, inside the validated-TP Jedi Force Power Zone",
                "universe": "350 liquid B3 stocks; issuer share classes deduplicated",
                "minimums": "Price R$ 1; market cap R$ 750m; 90-day ADTV R$ 5m",
                "quality": "Sector-specific profitability and at least 60% fundamental completeness",
                "valuation": "Sector-adapted DCF, earnings, relative, residual/dividend and public-consensus methods reconciled across Brapi and EODHD All-In-One",
                "score": "Power Score: 35% return, 25% inverse risk, 15% quality, 15% confidence, 10% entry",
                "tp_upside": f"C3PO TP upside >= Selic + 6 p.p. = {tp_upside_cutoff:.1f}%",
                "entry": "Weighted median of five framework buy-ins, capped by the shared return hurdle; price distance <= 15%",
                "risk": f"Risk <= min(40, eligible-universe median) = {risk_cutoff:.1f}/100",
            "confidence": f"Validated TP only: score >= {MIN_TP_VALIDATION_SCORE:.0f}/100, confidence >= {MIN_VALUATION_CONFIDENCE:.0f}, dispersion <= {MAX_METHOD_DISPERSION:.0f}%, two sources, quarterly fundamentals <= {MAX_FUNDAMENTALS_AGE_DAYS} days and internal/consensus gap <= {MAX_TP_CONSENSUS_GAP:.0f}%",
            },
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.brapi_token}"}

    def _source_label(self) -> str:
        return "Brapi Pro + EODHD All-In-One" if self.settings.eodhd_api_token else "Brapi Pro"

    def _eodhd_fundamental_map(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        now = datetime.now(timezone.utc)
        clean_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        cache_is_fresh = bool(self._eodhd_cache_expires_at and now < self._eodhd_cache_expires_at)
        if not cache_is_fresh:
            self._eodhd_fundamentals = {}
        missing_symbols = [symbol for symbol in clean_symbols if symbol not in self._eodhd_fundamentals]
        if not missing_symbols:
            cached = {symbol: self._eodhd_fundamentals[symbol] for symbol in clean_symbols}
            return apply_official_fundamentals_map(self.database, cached, market="B3")

        run_id = self.database.begin_ingestion_run(
            "eodhd",
            "EODHD",
            "fundamental_data",
            {"operation": "b3_fundamentals", "symbols": missing_symbols, "methodology_version": METHODOLOGY_VERSION},
        )
        try:
            client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
            payload = client.fundamentals(missing_symbols, exchange="SA", workers=10)
            self._eodhd_fundamentals.update(payload)
            self._eodhd_cache_expires_at = now + timedelta(hours=AUXILIARY_CACHE_HOURS)
            self.database.finish_ingestion_run(run_id, "succeeded", len(missing_symbols), len(payload))
            fresh = {symbol: self._eodhd_fundamentals[symbol] for symbol in clean_symbols if symbol in self._eodhd_fundamentals}
            return apply_official_fundamentals_map(self.database, fresh, market="B3")
        except Exception as exc:
            self.database.finish_ingestion_run(run_id, "failed", len(missing_symbols), 0, str(exc))
            fallback = {symbol: self._eodhd_fundamentals[symbol] for symbol in clean_symbols if symbol in self._eodhd_fundamentals}
            return apply_official_fundamentals_map(self.database, fallback, market="B3")

    def _eodhd_historical_map(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        if not self.settings.eodhd_api_token or not symbols:
            return {}
        now = datetime.now(timezone.utc)
        clean_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols if symbol))
        cache_is_fresh = bool(self._eodhd_history_cache_expires_at and now < self._eodhd_history_cache_expires_at)
        if not cache_is_fresh:
            self._eodhd_history = {}
        missing_symbols = [symbol for symbol in clean_symbols if symbol not in self._eodhd_history]
        if missing_symbols:
            run_id = self.database.begin_ingestion_run(
                "eodhd",
                "EODHD",
                "market_data",
                {"operation": "b3_history_fallback", "symbols": missing_symbols, "methodology_version": METHODOLOGY_VERSION},
            )
            try:
                client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
                histories = client.histories(missing_symbols, exchange="SA", days=120, workers=10)
                normalized = {
                    symbol: stats
                    for symbol, rows in histories.items()
                    if (stats := self._history_statistics(rows))
                }
                self._eodhd_history.update(normalized)
                self._eodhd_history_cache_expires_at = now + timedelta(hours=AUXILIARY_CACHE_HOURS)
                self.database.finish_ingestion_run(run_id, "succeeded", len(missing_symbols), len(normalized))
            except Exception as exc:
                self.database.finish_ingestion_run(run_id, "failed", len(missing_symbols), 0, str(exc))
        return {symbol: self._eodhd_history[symbol] for symbol in clean_symbols if symbol in self._eodhd_history}

    def _quotes(self, symbols: list[str]) -> dict[str, Any]:
        client = BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http)
        output: dict[str, Any] = {}
        for group in batches(symbols):
            for quote in client.quotes(group):
                output[quote.symbol] = quote
        return output

    def _optional_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {}
        try:
            return self._quotes(symbols)
        except Exception:
            return {}

    @staticmethod
    def _targeted_catalog(items: Any, symbol: str) -> list[dict[str, Any]]:
        clean = symbol.strip().upper().removesuffix(".SA")
        exact_matches: list[dict[str, Any]] = []
        fractional_matches: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            provider_symbol = str(item.get("symbol") or "").upper()
            canonical = provider_symbol[:-1] if provider_symbol.endswith("F") else provider_symbol
            if canonical != clean:
                continue
            normalized = dict(item)
            normalized["symbol"] = clean
            target = exact_matches if provider_symbol == clean else fractional_matches
            target.append(normalized)
        return (exact_matches or fractional_matches)[:1]

    def _eodhd_quote_map(self, symbols: list[str]) -> dict[str, Any]:
        if not self.settings.eodhd_api_token or not symbols:
            return {}
        try:
            client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
            quotes = client.quotes([f"{symbol.upper().removesuffix('.SA')}.SA" for symbol in symbols])
            return {quote.symbol: quote for quote in quotes}
        except Exception:
            return {}

    def _optional_fundamental_map(self, endpoint: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
        try:
            return self._fundamental_map(endpoint, symbols)
        except Exception:
            return {}

    def _optional_historical_map(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        try:
            return self._historical_map(symbols)
        except Exception:
            return {}

    @staticmethod
    def _consensus_reference_symbols(
        catalog: list[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> list[str]:
        eligible_issuers = {str(row.get("issuer") or "") for row in rows}
        row_symbols = {str(row.get("symbol") or "") for row in rows}
        references: set[str] = set()
        for item in catalog:
            symbol = str(item.get("symbol") or "").upper()
            match = re.fullmatch(r"([A-Z]+)11F?", symbol)
            if not match or match.group(1) not in eligible_issuers:
                continue
            standard_unit = f"{match.group(1)}11"
            if standard_unit not in row_symbols:
                references.add(standard_unit)
        return sorted(references)

    @staticmethod
    def _targeted_consensus_reference_symbols(symbol: str) -> list[str]:
        """Return the issuer Unit used by analysts when another share class is requested."""
        match = re.fullmatch(r"([A-Z]+)(\d{1,2})", symbol.upper())
        if not match or match.group(2) == "11":
            return []
        return [f"{match.group(1)}11"]

    @classmethod
    def _consensus_reference_rows(
        cls,
        quotes: dict[str, Any],
        financial: dict[str, dict[str, Any]],
        eodhd: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        for symbol, quote in quotes.items():
            price = positive(quote.price)
            if not price:
                continue
            finance = financial.get(symbol, {})
            eod = eodhd.get(symbol, {})
            brapi_analysts = int(number(finance.get("numberOfAnalystOpinions")) or 0)
            eodhd_analysts = int(number(eod.get("numberOfAnalystOpinions")) or 0)
            references.append({
                "symbol": symbol,
                "issuer": re.match(r"^[A-Z]+", symbol).group(0) if re.match(r"^[A-Z]+", symbol) else symbol,
                "price": price,
                "brapi_consensus_tp": cls._valid_target(finance.get("targetMeanPrice"), price, brapi_analysts),
                "brapi_analysts": brapi_analysts,
                "eodhd_consensus_tp": cls._valid_target(eod.get("targetMeanPrice"), price, eodhd_analysts),
                "eodhd_analysts": eodhd_analysts,
            })
        return references

    def _fundamental_map(self, endpoint: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        url = f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/stocks/{endpoint}"
        for group in batches(symbols):
            payload = self.http.get_json(
                url,
                params={"symbols": ",".join(group), "mode": "current"},
                headers=self._headers(),
            )
            for item in payload.get("results", []):
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or item.get("requestedSymbol") or "").upper()
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                if symbol:
                    output[symbol] = data
        return output

    def _historical_map(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        output: dict[str, dict[str, float]] = {}
        url = f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/stocks/historical"
        for group in batches(symbols):
            payload = self.http.get_json(
                url,
                params={"symbols": ",".join(group), "range": "3mo", "interval": "1d", "sortOrder": "desc"},
                headers=self._headers(),
            )
            for item in payload.get("results", []):
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or item.get("requestedSymbol") or "").upper()
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                history = data.get("historicalDataPrice") if isinstance(data.get("historicalDataPrice"), list) else []
                traded_values = []
                closes = []
                for point in history[:66]:
                    if not isinstance(point, dict):
                        continue
                    close = positive(point.get("adjustedClose")) or positive(point.get("close"))
                    volume = positive(point.get("volume"))
                    if close:
                        closes.append(close)
                    if close and volume:
                        traded_values.append(close * volume)
                if symbol and traded_values:
                    log_returns = [math.log(closes[index] / closes[index + 1]) for index in range(len(closes) - 1)]
                    volatility = statistics.stdev(log_returns) * math.sqrt(252) if len(log_returns) >= 20 else None
                    recent_20d = closes[:20]
                    recent_60d = closes[:60]
                    output[symbol] = {
                        "adtv_90d": statistics.mean(traded_values),
                        "history_days": float(len(traded_values)),
                        "volatility_90d": volatility,
                        "support_60d": percentile(recent_60d, 0.25),
                        "median_20d": statistics.median(recent_20d),
                        "low_20d": min(recent_20d),
                        "last_close": recent_20d[0],
                    }
        return output

    @staticmethod
    def _history_statistics(rows: list[dict[str, Any]]) -> dict[str, float]:
        ordered = sorted(
            (row for row in rows if isinstance(row, dict)),
            key=lambda row: str(row.get("date") or ""),
            reverse=True,
        )[:66]
        closes: list[float] = []
        traded_values: list[float] = []
        for point in ordered:
            close = positive(point.get("close"))
            volume = positive(point.get("volume"))
            if close:
                closes.append(close)
            if close and volume:
                traded_values.append(close * volume)
        if not closes or not traded_values:
            return {}
        log_returns = [math.log(closes[index] / closes[index + 1]) for index in range(len(closes) - 1)]
        recent_20d = closes[:20]
        recent_60d = closes[:60]
        return {
            "adtv_90d": statistics.mean(traded_values),
            "history_days": float(len(traded_values)),
            "volatility_90d": statistics.stdev(log_returns) * math.sqrt(252) if len(log_returns) >= 20 else 0.0,
            "support_60d": percentile(recent_60d, 0.25),
            "median_20d": statistics.median(recent_20d),
            "low_20d": min(recent_20d),
            "last_close": recent_20d[0],
        }

    def _macro_context(self) -> dict[str, float]:
        defaults = {"selic": LATEST_COPOM_SELIC, "ipca12m": 0.045}
        provider_selic: float | None = None
        try:
            payload = self.http.get_json(
                f"{self.settings.brapi_base_url.rstrip('/')}/api/v2/macro/latest",
                params={"symbols": "selic,ipca12m"},
                headers=self._headers(),
            )
            for item in payload.get("results", []):
                if not isinstance(item, dict):
                    continue
                series = item.get("series") if isinstance(item.get("series"), dict) else {}
                latest = item.get("latest") if isinstance(item.get("latest"), dict) else {}
                slug = str(series.get("slug") or "")
                value = number(latest.get("value"))
                if slug in defaults and value is not None:
                    if slug == "selic":
                        provider_selic = value / 100
                    else:
                        defaults[slug] = value / 100
        except Exception:
            pass

        bcb_selic: float | None = None
        bcb_as_of: date | None = None
        try:
            payload = self.http.get_json(BCB_SELIC_SERIES_URL, params={"formato": "json"})
            latest = payload[-1] if isinstance(payload, list) and payload else {}
            value = number(latest.get("valor")) if isinstance(latest, dict) else None
            observed_at = str(latest.get("data") or "") if isinstance(latest, dict) else ""
            if value is not None:
                bcb_selic = value / 100
            if observed_at:
                bcb_as_of = datetime.strptime(observed_at, "%d/%m/%Y").date()
        except Exception:
            pass

        defaults["selic"] = self._effective_selic(
            provider_value=provider_selic,
            bcb_value=bcb_selic,
            bcb_as_of=bcb_as_of,
        )
        self._check_selic_against_market_yield(defaults["selic"])
        return defaults

    def _check_selic_against_market_yield(self, effective_selic: float) -> None:
        """Cross-checks the Selic-derived risk-free rate against a real,
        independently-observed market yield (Brapi Pro Tesouro Direto,
        longest-duration Tesouro Prefixado bond -- a genuine nominal
        yield, not a policy rate). Catches the exact failure mode this
        session spent all day chasing elsewhere: a feed silently going
        stale or wrong with nothing to flag it. Purely informational --
        never adjusts the computed rate, and any failure here is
        swallowed so it can't break the real risk-free calculation."""
        try:
            bonds = BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http).treasury_rates(
                indexer="prefixado",
            )
        except Exception:
            return
        if not bonds:
            return
        longest = max(bonds, key=lambda bond: bond.get("duration_days") or 0)
        observed_rate = longest.get("sell_rate") or longest.get("buy_rate")
        if observed_rate is None:
            return
        rate = observed_rate / 100 if observed_rate > 1 else observed_rate
        if rate <= 0:
            return
        divergence = abs(rate - effective_selic)
        if divergence > SELIC_MARKET_YIELD_DIVERGENCE_WARNING:
            logger.warning(
                "Selic-derived risk-free rate (%.2f%%) diverges %.2f points from the "
                "market-observed Tesouro Prefixado yield (%.2f%%, %s, %d days to maturity) "
                "-- verify the BCB/Brapi Selic feed isn't stale or wrong.",
                effective_selic * 100, divergence * 100, rate * 100,
                longest.get("symbol"), longest.get("duration_days"),
            )

    @staticmethod
    def _effective_selic(
        *,
        provider_value: float | None,
        bcb_value: float | None,
        bcb_as_of: date | None,
        now: datetime | None = None,
    ) -> float:
        current_time = now or datetime.now(ZoneInfo("America/Sao_Paulo"))
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        if bcb_value is not None and bcb_as_of is not None and bcb_as_of >= LATEST_COPOM_EFFECTIVE_DATE:
            return bcb_value
        if current_time >= LATEST_COPOM_DECISION_AT:
            stale_days = (current_time.date() - LATEST_COPOM_DECISION_AT.date()).days
            if stale_days > SELIC_GOVERNOR_STALE_WARNING_DAYS:
                logger.warning(
                    "Selic governor is %d days past LATEST_COPOM_DECISION_AT (%s) with no newer BCB "
                    "observation (bcb_as_of=%s) — LATEST_COPOM_SELIC/LATEST_COPOM_DECISION_AT/"
                    "LATEST_COPOM_EFFECTIVE_DATE may need a manual update after a subsequent COPOM meeting.",
                    stale_days, LATEST_COPOM_DECISION_AT.date(), bcb_as_of,
                )
            return LATEST_COPOM_SELIC
        return bcb_value or provider_value or LATEST_COPOM_SELIC

    def _prepare_rows(
        self,
        catalog: list[dict[str, Any]],
        quotes: dict[str, Any],
        stats: dict[str, dict[str, Any]],
        financial: dict[str, dict[str, Any]],
        history: dict[str, dict[str, float]],
        macro: dict[str, float],
        eodhd: dict[str, dict[str, Any]] | None = None,
        consensus_references: list[dict[str, Any]] | None = None,
        coverage_audit: dict[str, int] | None = None,
        enforce_screening_gates: bool = True,
        enforce_quality_gate: bool = True,
    ) -> list[dict[str, Any]]:
        eodhd = eodhd or {}
        if coverage_audit is not None:
            coverage_audit.clear()
            coverage_audit["universe"] = len(catalog)

        def reject(reason: str) -> None:
            if coverage_audit is not None:
                coverage_audit[reason] = coverage_audit.get(reason, 0) + 1

        rows: list[dict[str, Any]] = []
        catalog_symbols = [str(item.get("symbol", "")).upper() for item in catalog if item.get("symbol")]
        ir_events = self.database.latest_valuation_ir_events(catalog_symbols, market="B3")
        insider_activity = self.database.insider_transaction_activity(
            catalog_symbols, "B3", datetime.now(timezone.utc) - timedelta(days=INSIDER_GOVERNANCE_LOOKBACK_DAYS),
        )
        for item in catalog:
            symbol = str(item.get("symbol", "")).upper()
            quote = quotes.get(symbol)
            historical = history.get(symbol, {})
            if not quote:
                reject("missing_quote")
                continue
            if enforce_screening_gates and historical.get("history_days", 0) < MIN_HISTORY_DAYS:
                reject("insufficient_history")
                continue
            stat = stats.get(symbol, {})
            finance = financial.get(symbol, {})
            eod = eodhd.get(symbol, {})
            official_fundamentals = bool(eod.get("officialFundamentals"))
            price = positive(quote.price)
            reported_shares_hint = (
                positive(stat.get("sharesOutstanding"))
                or positive(stat.get("impliedSharesOutstanding"))
                or positive(eod.get("sharesOutstanding"))
            )
            market_cap = (
                positive(quote.market_cap)
                or positive(stat.get("marketCap"))
                or positive(eod.get("marketCap"))
                or (price * reported_shares_hint if price and reported_shares_hint else None)
            )
            adtv_90d = positive(historical.get("adtv_90d"))
            if not price or (enforce_screening_gates and price < MIN_PRICE):
                reject("price_gate")
                continue
            if not market_cap or (enforce_screening_gates and market_cap < MIN_MARKET_CAP):
                reject("market_cap_gate")
                continue
            if enforce_screening_gates and (not adtv_90d or adtv_90d < MIN_ADTV_90D):
                reject("liquidity_gate")
                continue

            name = canonical_b3_company_name(
                symbol,
                item.get("longName") or item.get("name") or symbol,
            )
            classification = resolve_b3_sector(
                symbol=symbol,
                name=name,
                brapi_sector=item.get("sector"),
                brapi_subsector=item.get("subsector"),
                eodhd=eod,
            )
            sector = classification.sector
            subsector = classification.industry
            profile = classification.valuation_profile
            cycle_metrics = self._cyclical_margin_profile(eod) if profile == "cyclical" else {}
            annual_growth_metrics = self._annual_growth_profile(eod)
            brapi_pe = self._valid_multiple(stat.get("trailingPE"), 1.5, 80.0)
            eodhd_pe = self._valid_multiple(eod.get("trailingPE"), 1.5, 80.0)
            pe = eodhd_pe if official_fundamentals and eodhd_pe else brapi_pe or eodhd_pe
            brapi_forward_pe = self._validated_forward_pe(
                stat.get("forwardPE"), brapi_pe, stat.get("forwardEps"), price,
            )
            eodhd_forward_pe = self._validated_forward_pe(
                eod.get("forwardPE"), eodhd_pe, eod.get("forwardEps"), price,
            )
            forward_pe = brapi_forward_pe or eodhd_forward_pe
            eodhd_ev_ebitda = self._valid_multiple(eod.get("enterpriseToEbitda"), 1.0, 50.0)
            brapi_ev_ebitda = self._valid_multiple(stat.get("enterpriseToEbitda"), 1.0, 50.0)
            ev_ebitda = eodhd_ev_ebitda if official_fundamentals and eodhd_ev_ebitda else eodhd_ev_ebitda or brapi_ev_ebitda
            peg = self._valid_multiple(eod.get("pegRatio"), 0.10, 10.0) or self._valid_multiple(stat.get("pegRatio"), 0.10, 10.0)
            roe = number(eod.get("returnOnEquity")) if official_fundamentals else number(finance.get("returnOnEquity")) or number(eod.get("returnOnEquity"))
            roa = number(eod.get("returnOnAssets")) if official_fundamentals else number(finance.get("returnOnAssets")) or number(eod.get("returnOnAssets"))
            profit_margin = number(eod.get("profitMargins")) if official_fundamentals else number(finance.get("profitMargins")) or number(stat.get("profitMargins")) or number(eod.get("profitMargins"))
            operating_margin = number(eod.get("operatingMargins")) if official_fundamentals else number(finance.get("operatingMargins")) or number(eod.get("operatingMargins"))
            revenue_growth = number(eod.get("revenueGrowthAnnual")) if official_fundamentals else number(eod.get("revenueGrowthAnnual")) or number(finance.get("revenueGrowthAnnual")) or number(finance.get("revenueGrowth"))
            earnings_growth = number(eod.get("earningsGrowthAnnual")) if official_fundamentals else number(eod.get("earningsGrowthAnnual")) or number(finance.get("earningsGrowthAnnual")) or number(finance.get("earningsGrowth")) or number(stat.get("earningsQuarterlyGrowth"))
            implied_shares = market_cap / price
            reported_shares = reported_shares_hint
            shares = reported_shares if reported_shares and 0.70 <= reported_shares / implied_shares <= 1.30 else implied_shares
            raw_eps = positive(stat.get("trailingEps")) or positive(stat.get("earningsPerShare")) or positive(eod.get("trailingEps"))
            eps = price / pe if pe else raw_eps if raw_eps and raw_eps <= price / 1.5 else None
            raw_forward_eps = positive(eod.get("forwardEps")) or positive(stat.get("forwardEps"))
            forward_eps = price / forward_pe if forward_pe else raw_forward_eps if raw_forward_eps and raw_forward_eps <= price / 1.5 else None
            eodhd_price_to_book = self._valid_multiple(eod.get("priceToBook"), 0.10, 30.0)
            brapi_price_to_book = self._valid_multiple(stat.get("priceToBook"), 0.10, 30.0)
            price_to_book = eodhd_price_to_book if official_fundamentals and eodhd_price_to_book else eodhd_price_to_book or brapi_price_to_book
            raw_book_value = positive(eod.get("bookValue")) or positive(stat.get("bookValue"))
            if price_to_book:
                book_value = price / price_to_book
            elif raw_book_value and 0.10 <= price / raw_book_value <= 30.0:
                book_value = raw_book_value
            else:
                book_value = None
            if forward_pe is None and forward_eps:
                forward_pe = self._valid_multiple(price / forward_eps, 1.5, 80.0)
            if forward_eps is None and eps and earnings_growth is not None:
                forward_eps = positive(eps * (1 + clamp(earnings_growth, -0.35, 0.35)))
                if forward_eps:
                    forward_pe = self._valid_multiple(price / forward_eps, 1.5, 80.0)
            if peg is None and pe and earnings_growth is not None and earnings_growth > 0.02:
                peg = self._valid_multiple(pe / (earnings_growth * 100), 0.10, 10.0)

            raw_fcf = number(eod.get("freeCashflow")) if official_fundamentals else number(finance.get("freeCashflow"))
            if raw_fcf is None:
                raw_fcf = number(eod.get("freeCashflow"))
            brapi_analysts = int(number(finance.get("numberOfAnalystOpinions")) or 0)
            eodhd_analysts = int(number(eod.get("numberOfAnalystOpinions")) or 0)
            brapi_consensus_tp = self._valid_target(finance.get("targetMeanPrice"), price, brapi_analysts)
            eodhd_consensus_tp = self._valid_target(eod.get("targetMeanPrice"), price, eodhd_analysts)
            dividend_yield = self._reconcile_dividend_yield(
                number(stat.get("dividendYield")) or number(stat.get("yield")),
                number(eod.get("dividendYield")),
            )
            source_agreement, comparison_count = self._source_confirmation_score(
                {
                    "market_cap": positive(quote.market_cap) or positive(stat.get("marketCap")),
                    "pe": brapi_pe,
                    "forward_pe": brapi_forward_pe,
                    "ev_ebitda": self._valid_multiple(stat.get("enterpriseToEbitda"), 1.0, 50.0),
                    "price_to_book": self._valid_multiple(stat.get("priceToBook"), 0.10, 30.0),
                    "eps": positive(stat.get("trailingEps")) or positive(stat.get("earningsPerShare")),
                    "dividend_yield": self._valid_dividend_yield(number(stat.get("dividendYield")) or number(stat.get("yield"))),
                },
                {
                    "market_cap": positive(eod.get("marketCap")),
                    "pe": eodhd_pe,
                    "forward_pe": eodhd_forward_pe,
                    "ev_ebitda": self._valid_multiple(eod.get("enterpriseToEbitda"), 1.0, 50.0),
                    "price_to_book": self._valid_multiple(eod.get("priceToBook"), 0.10, 30.0),
                    "eps": positive(eod.get("trailingEps")),
                    "dividend_yield": self._valid_dividend_yield(number(eod.get("dividendYield"))),
                },
            )
            row = {
                "symbol": symbol,
                "issuer": re.match(r"^[A-Z]+", symbol).group(0) if re.match(r"^[A-Z]+", symbol) else symbol,
                "name": name,
                "logo_url": item.get("logoUrl") or item.get("logourl"),
                "sector": sector,
                "subsector": subsector,
                "peer_group": classification.peer_group,
                "valuation_profile": profile,
                "valuation_profile_source": classification.valuation_profile_source,
                "sector_source": classification.source,
                "sector_confidence": classification.confidence,
                "sector_conflict": classification.conflict,
                "brapi_sector": classification.brapi_sector,
                "brapi_subsector": classification.brapi_subsector,
                "eodhd_sector": classification.eodhd_sector,
                "eodhd_industry": classification.eodhd_industry,
                "price": price,
                "change_percent": number(quote.change_percent),
                "volume": positive(quote.volume),
                "adtv_90d": adtv_90d,
                "volatility_90d": positive(historical.get("volatility_90d")),
                "support_60d": positive(historical.get("support_60d")),
                "median_20d": positive(historical.get("median_20d")),
                "low_20d": positive(historical.get("low_20d")),
                "last_close": positive(historical.get("last_close")),
                "market_cap": market_cap,
                "as_of": quote.as_of,
                "quote_quality": quote.quality_score,
                "pe": pe,
                "forward_pe": forward_pe,
                "ev_ebitda": ev_ebitda,
                "peg": peg,
                "price_to_book": price_to_book,
                "book_value": book_value,
                "beta": self._valid_multiple(stat.get("beta"), 0.05, 4.0) or self._valid_multiple(eod.get("beta"), 0.05, 4.0),
                "shares": shares,
                "eps": eps,
                "forward_eps": forward_eps,
                "dividend_yield": dividend_yield,
                "debt_to_equity": positive(eod.get("debtToEquity")) if official_fundamentals else positive(finance.get("debtToEquity")) or positive(eod.get("debtToEquity")),
                "roe": roe,
                "roa": roa,
                "profit_margin": profit_margin,
                "operating_margin": operating_margin,
                "ebitda_margin": number(eod.get("ebitdaMargins")) if official_fundamentals else number(finance.get("ebitdaMargins")) or number(eod.get("ebitdaMargins")),
                "revenue_growth": revenue_growth,
                "earnings_growth": earnings_growth,
                "fcf": positive(raw_fcf),
                "fcf_raw": raw_fcf,
                "operating_cashflow": positive(eod.get("operatingCashflow")) if official_fundamentals else positive(finance.get("operatingCashflow")) or positive(eod.get("operatingCashflow")),
                "ebitda": positive(eod.get("ebitda")) if official_fundamentals else positive(finance.get("ebitda")) or positive(eod.get("ebitda")),
                "revenue": positive(eod.get("totalRevenue")) if official_fundamentals else positive(finance.get("totalRevenue")) or positive(eod.get("totalRevenue")),
                "cash": (positive(eod.get("totalCash")) if official_fundamentals else positive(finance.get("totalCash")) or positive(eod.get("totalCash"))) or 0.0,
                "debt": (positive(eod.get("totalDebt")) if official_fundamentals else positive(finance.get("totalDebt")) or positive(eod.get("totalDebt"))) or 0.0,
                "brapi_consensus_tp": brapi_consensus_tp,
                "brapi_analysts": brapi_analysts,
                "eodhd_consensus_tp": eodhd_consensus_tp,
                "eodhd_analysts": eodhd_analysts,
                "public_consensus_tp": None,
                "analyst_count": 0,
                "consensus_origin_symbol": None,
                "data_source_count": 2 if eod else 1,
                "source_agreement_percent": source_agreement,
                "source_comparison_count": comparison_count,
                "fundamentals_as_of": eod.get("financialsAsOf") or eod.get("updated_at"),
                **cycle_metrics,
                **(ir_freshness := self._ir_freshness(
                    eod.get("financialsAsOf") or eod.get("updated_at"),
                    ir_events.get(symbol),
                )),
                "pending_disclosure_risk": self._disclosure_risk_signal(
                    ir_freshness["ir_status"], (ir_events.get(symbol) or {}).get("materiality")
                ),
                "insider_net_signal": self._insider_net_signal(insider_activity.get(symbol)),
                "history_source": "eodhd" if symbol in self._eodhd_history else "brapi",
                **annual_growth_metrics,
            }
            row["valuation_profile"] = self._refine_valuation_profile(row)
            if row["valuation_profile"] == "cyclical":
                row.update(self._cyclical_market_multiples(row))
            row["completeness"] = self._completeness(row)
            quality_reasons = self._quality_gate_reasons(row)
            row["fundamental_quality_status"] = "passed" if not quality_reasons else "review_required"
            row["fundamental_quality_reasons"] = quality_reasons
            if not quality_reasons or not enforce_quality_gate:
                rows.append(row)
            else:
                reject("fundamental_quality_gate")

        self._reconcile_issuer_consensus(rows, consensus_references)
        self._apply_official_consensus(rows)
        sector_medians = self._sector_medians(rows)
        for row in rows:
            self._value_row(row, sector_medians, macro)
        if coverage_audit is not None:
            coverage_audit["quality_eligible"] = len(rows)
            coverage_audit["calculated_tp"] = sum(1 for row in rows if positive(row.get("our_tp")))
            coverage_audit["validated"] = sum(1 for row in rows if row.get("tp_validation_status") == "validated")
            coverage_audit["provisional"] = sum(
                1 for row in rows
                if row.get("tp_validation_status") != "validated" and self._provisional_eligibility(row)[0]
            )
        return rows

    @staticmethod
    def _valid_multiple(value: Any, low: float, high: float) -> float | None:
        parsed = positive(value)
        return parsed if parsed is not None and low <= parsed <= high else None

    @staticmethod
    def _valid_target(value: Any, price: float, analyst_count: Any) -> float | None:
        target = positive(value)
        analysts = number(analyst_count) or 0
        return target if target and analysts > 0 and price * 0.20 <= target <= price * 5.0 else None

    @classmethod
    def _validated_forward_pe(
        cls,
        value: Any,
        trailing_pe: float | None,
        forward_eps: Any,
        price: float,
    ) -> float | None:
        forward_pe = cls._valid_multiple(value, 1.5, 80.0)
        if forward_pe is None:
            return None

        reported_forward_eps = positive(forward_eps)
        implied_forward_eps = price / forward_pe
        if reported_forward_eps:
            eps_gap = abs(reported_forward_eps - implied_forward_eps) / max(reported_forward_eps, implied_forward_eps)
            if eps_gap > 0.25:
                return None

        # A collapse to less than 35% of trailing P/E needs a matching forward EPS.
        # This blocks share/unit denominator mismatches such as SAPR3/SAPR4/SAPR11.
        if trailing_pe and forward_pe < trailing_pe * 0.35 and reported_forward_eps is None:
            return None
        return forward_pe

    @staticmethod
    def _valid_dividend_yield(value: Any) -> float | None:
        dividend_yield = number(value)
        return dividend_yield if dividend_yield is not None and 0 < dividend_yield <= 0.20 else None

    @classmethod
    def _reconcile_dividend_yield(cls, primary: Any, secondary: Any) -> float | None:
        first = cls._valid_dividend_yield(primary)
        second = cls._valid_dividend_yield(secondary)
        if first is None:
            return second
        if second is None:
            return first
        if max(first, second) / min(first, second) > 1.75:
            return min(first, second)
        return first * 0.60 + second * 0.40

    @staticmethod
    def _weighted_median_observation(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not observations:
            return None
        ordered = sorted(observations, key=lambda observation: observation["ratio"])
        total_weight = sum(observation["weight"] for observation in ordered)
        threshold = total_weight / 2
        cumulative = 0.0
        for observation in ordered:
            cumulative += observation["weight"]
            if cumulative >= threshold:
                return observation
        return ordered[-1]

    @classmethod
    def _reconcile_issuer_consensus(
        cls,
        rows: list[dict[str, Any]],
        references: list[dict[str, Any]] | None = None,
    ) -> None:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in [*rows, *(references or [])]:
            price = positive(row.get("price"))
            observations: list[dict[str, Any]] = []
            if price:
                for source in ("brapi", "eodhd"):
                    target = positive(row.get(f"{source}_consensus_tp"))
                    analysts = int(number(row.get(f"{source}_analysts")) or 0)
                    ratio = target / price if target else None
                    if target and analysts > 0 and ratio is not None and 0.50 <= ratio <= 2.50:
                        observations.append({
                            "symbol": row["symbol"],
                            "source": source,
                            "target": target,
                            "ratio": ratio,
                            "analysts": analysts,
                            "weight": max(analysts, 1) * (1.15 if str(row["symbol"]).endswith("11") else 1.0),
                        })
            row["_direct_consensus_observations"] = observations
            groups.setdefault(str(row.get("issuer") or row["symbol"]), []).append(row)

        for issuer_rows in groups.values():
            issuer_observations = [
                observation
                for row in issuer_rows
                for observation in row["_direct_consensus_observations"]
            ]
            canonical = cls._weighted_median_observation(issuer_observations)
            canonical_ratio = canonical["ratio"] if canonical else None

            for row in issuer_rows:
                direct = row.pop("_direct_consensus_observations")
                selected_ratio: float | None = None
                selected_analysts = 0
                selected_symbol: str | None = None
                selected_source: str | None = None

                if direct:
                    direct_center = cls._weighted_median_observation(direct)
                    if direct_center:
                        selected_ratio = direct_center["ratio"]
                        selected_analysts = max(observation["analysts"] for observation in direct)
                        selected_symbol = row["symbol"]
                        selected_source = direct_center["source"]

                    # A better-covered issuer class can override a lone outlying direct
                    # target while preserving the implied upside, not its nominal price.
                    if (
                        canonical
                        and selected_ratio
                        and abs(selected_ratio - canonical_ratio) / canonical_ratio > 0.35
                        and canonical["analysts"] >= selected_analysts
                    ):
                        selected_ratio = canonical_ratio
                        selected_analysts = canonical["analysts"]
                        selected_symbol = canonical["symbol"]
                        selected_source = canonical["source"]
                elif canonical:
                    selected_ratio = canonical_ratio
                    selected_analysts = canonical["analysts"]
                    selected_symbol = canonical["symbol"]
                    selected_source = canonical["source"]

                row["public_consensus_tp"] = row["price"] * selected_ratio if selected_ratio else None
                row["analyst_count"] = selected_analysts
                row["consensus_origin_symbol"] = selected_symbol
                row["consensus_origin_source"] = selected_source
                row["consensus_source_count"] = sum(
                    1 for observation in issuer_observations
                    if observation["symbol"] == selected_symbol
                ) if selected_symbol else 0
                row["consensus_implied_upside_percent"] = (selected_ratio - 1) * 100 if selected_ratio else None

    @staticmethod
    def _apply_official_consensus(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            official = OFFICIAL_CONSENSUS_OVERRIDES.get(str(row.get("symbol") or ""))
            price = positive(row.get("price"))
            target = positive(official.get("target_price")) if official else None
            analysts = int(number(official.get("analyst_count")) or 0) if official else 0
            if not official or not price or not target or analysts <= 0:
                continue
            try:
                consensus_date = date.fromisoformat(official["as_of"])
                consensus_age = (
                    datetime.now(ZoneInfo("America/Sao_Paulo")).date() - consensus_date
                ).days
            except (TypeError, ValueError):
                continue
            if consensus_age > int(official.get("max_age_days") or 180):
                continue
            if analysts < int(row.get("analyst_count") or 0):
                continue
            row["public_consensus_tp"] = target
            row["analyst_count"] = analysts
            row["consensus_origin_symbol"] = row["symbol"]
            row["consensus_origin_source"] = official["source"]
            row["consensus_source_count"] = max(int(row.get("consensus_source_count") or 0), 1)
            row["consensus_implied_upside_percent"] = (target / price - 1) * 100
            row["consensus_as_of"] = official["as_of"]
            row["consensus_source_url"] = official["source_url"]

    @staticmethod
    def _consensus_weight(row: dict[str, Any]) -> float:
        if not row.get("public_consensus_tp") or (row.get("analyst_count") or 0) <= 0:
            return 0.0
        analyst_breadth = clamp((row.get("analyst_count") or 0) / 10, 0, 1)
        independent_confirmation = 0.05 if (row.get("consensus_source_count") or 0) >= 2 else 0.0
        weight = 0.20 + analyst_breadth * 0.10 + independent_confirmation
        if row.get("consensus_origin_symbol") != row.get("symbol"):
            weight = min(weight, 0.30)
        return clamp(weight, 0.20, 0.35)

    @staticmethod
    def _source_confirmation_score(
        primary: dict[str, float | None],
        secondary: dict[str, float | None],
    ) -> tuple[float, int]:
        if not secondary or not any(positive(value) for value in secondary.values()):
            return 30.0, 0

        scores: list[float] = []
        for key in primary.keys() & secondary.keys():
            first = positive(primary.get(key))
            second = positive(secondary.get(key))
            if first is None or second is None:
                continue
            relative_gap = abs(first - second) / max(abs(first), abs(second))
            if relative_gap <= 0.10:
                score = 100.0
            elif relative_gap <= 0.20:
                score = 80.0
            elif relative_gap <= 0.35:
                score = 50.0
            else:
                score = clamp(100 - relative_gap * 150, 0, 40)
            scores.append(score)

        if not scores:
            return 45.0, 0
        evidence_penalty = min(len(scores) / 3, 1.0)
        evidence_adjusted = statistics.mean(scores) * evidence_penalty + 45.0 * (1 - evidence_penalty)
        return clamp(evidence_adjusted, 0, 100), len(scores)

    @staticmethod
    def _sector_coverage_audit(
        catalog: list[dict[str, Any]],
        eodhd: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        details: list[dict[str, Any]] = []
        for item in catalog:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            classification = resolve_b3_sector(
                symbol=symbol,
                name=str(item.get("longName") or item.get("name") or symbol),
                brapi_sector=item.get("sector"),
                brapi_subsector=item.get("subsector"),
                eodhd=eodhd.get(symbol),
            )
            details.append({"symbol": symbol, **classification.as_dict()})
        counts = {
            "sector_audited": len(details),
            "sector_high_confidence": sum(item["sector_confidence"] >= 90 for item in details),
            "sector_provider_only": sum(65 <= item["sector_confidence"] < 90 for item in details),
            "sector_inferred": sum(item["sector_source"].startswith("C3PO inferred") or item["sector_source"] == "C3PO business-name inference" for item in details),
            "sector_conflicts": sum(bool(item["sector_conflict"]) for item in details),
            "sector_reviewed_overrides": sum(item["sector_source"] == "C3PO reviewed override" for item in details),
            "valuation_profile_overrides": sum(item["valuation_profile_source"] == "C3PO reviewed business model" for item in details),
            "sector_low_confidence": sum(item["sector_confidence"] < 65 for item in details),
        }
        return details, counts

    @staticmethod
    def _refine_valuation_profile(row: dict[str, Any]) -> str:
        profile = row["valuation_profile"]
        if profile not in ("general", "growth"):
            return profile
        debt_equity = row.get("debt_to_equity")
        revenue_trend = row.get("revenue_cagr_5y")
        earnings_trend = row.get("earnings_cagr_5y")
        has_durable_growth = (
            revenue_trend is not None
            and earnings_trend is not None
            and revenue_trend >= 0.05
            and earnings_trend >= 0.05
        )
        current_growth_is_stable = (
            (row.get("revenue_growth") if row.get("revenue_growth") is not None else -1.0) >= -0.10
            and (row.get("earnings_growth") if row.get("earnings_growth") is not None else -1.0) >= -0.10
        )
        is_quality_compounder = (
            (row.get("roe") or 0.0) >= 0.22
            and (row.get("profit_margin") or 0.0) >= 0.10
            and (row.get("ebitda_margin") or 0.0) >= 0.15
            and debt_equity is not None
            and debt_equity <= 1.0
            and has_durable_growth
            and current_growth_is_stable
            and (row.get("fcf_raw") or 0.0) > 0.0
        )
        return "quality_compounder" if is_quality_compounder else profile

    @staticmethod
    def _annual_growth_profile(fundamentals: dict[str, Any]) -> dict[str, float | int]:
        """Calculate durable growth from up to six annual income statements."""

        rows = fundamentals.get("annualIncome")
        if not isinstance(rows, list):
            return {}
        clean = [
            row for row in rows[:6]
            if isinstance(row, dict) and B3ScreenerService._statement_year(row) is not None
        ]
        if len(clean) < 4:
            return {}

        def cagr(field: str) -> float | None:
            observations = [
                (B3ScreenerService._statement_year(row), positive(row.get(field)))
                for row in clean
            ]
            usable = [(year, value) for year, value in observations if year is not None and value is not None]
            if len(usable) < 4:
                return None
            newest_year, newest_value = max(usable, key=lambda item: item[0])
            oldest_year, oldest_value = min(usable, key=lambda item: item[0])
            years = newest_year - oldest_year
            if years < 3 or newest_value <= 0 or oldest_value <= 0:
                return None
            return (newest_value / oldest_value) ** (1 / years) - 1

        output: dict[str, float | int] = {"annual_growth_observation_count": len(clean)}
        revenue_cagr = cagr("totalRevenue")
        earnings_cagr = cagr("netIncome")
        if revenue_cagr is not None:
            output["revenue_cagr_5y"] = clamp(revenue_cagr, -0.20, 0.30)
        if earnings_cagr is not None:
            output["earnings_cagr_5y"] = clamp(earnings_cagr, -0.30, 0.40)
        return output

    @staticmethod
    def _statement_year(row: dict[str, Any]) -> int | None:
        try:
            return date.fromisoformat(str(row.get("date") or "")[:10]).year
        except ValueError:
            return None

    @staticmethod
    def _completeness(row: dict[str, Any]) -> float:
        if row["valuation_profile"] in ("financial", "real_estate"):
            fields = ("pe", "price_to_book", "book_value", "eps", "roe", "profit_margin", "earnings_growth", "dividend_yield")
        else:
            fields = ("pe", "forward_pe", "ev_ebitda", "price_to_book", "roe", "profit_margin", "revenue_growth", "earnings_growth", "fcf", "ebitda", "shares")
        return sum(row.get(field) is not None for field in fields) / len(fields)

    @staticmethod
    def _passes_quality_gate(row: dict[str, Any]) -> bool:
        return not B3ScreenerService._quality_gate_reasons(row)

    @staticmethod
    def _quality_gate_reasons(row: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        if row["completeness"] < 0.60:
            reasons.append("Fundamental completeness below 60%")
        roe = row.get("roe") or 0.0
        margin = row.get("profit_margin") or 0.0
        if row["valuation_profile"] in ("financial", "real_estate"):
            if roe <= 0.08:
                reasons.append("ROE below the screening quality threshold")
            if row.get("book_value") is None:
                reasons.append("Book value is unavailable")
            if row.get("eps") is None:
                reasons.append("EPS is unavailable")
            return reasons
        positive_signals = sum((row.get("fcf") is not None, roe > 0.0, margin > 0.0, row.get("ebitda") is not None))
        if row["valuation_profile"] in ("general", "growth") and (row.get("fcf_raw") is None or row["fcf_raw"] <= 0):
            reasons.append("Positive free cash flow is unavailable")
        if positive_signals < 3:
            reasons.append("Fewer than three positive operating signals")
        return reasons

    @staticmethod
    def _sector_medians(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        output: dict[str, dict[str, float]] = {}
        fallbacks = {
            "pe": 12.0,
            "forward_pe": 10.0,
            "ev_ebitda": 8.0,
            "cycle_pe": 7.0,
            "cycle_ev_ebitda": 5.0,
            "price_to_book": 1.8,
            "roe": 0.15,
            "growth": 0.05,
            "profit_margin": 0.08,
            "ebitda_margin": 0.15,
        }
        def metrics(group_rows: list[dict[str, Any]]) -> dict[str, float]:
            return {
                "pe": median([row["pe"] for row in group_rows if row.get("pe")], fallbacks["pe"]),
                "forward_pe": median([row["forward_pe"] for row in group_rows if row.get("forward_pe")], fallbacks["forward_pe"]),
                "ev_ebitda": median([row["ev_ebitda"] for row in group_rows if row.get("ev_ebitda")], fallbacks["ev_ebitda"]),
                "cycle_pe": median([row["cycle_implied_pe"] for row in group_rows if row.get("cycle_implied_pe")], fallbacks["cycle_pe"]),
                "cycle_ev_ebitda": median([row["cycle_implied_ev_ebitda"] for row in group_rows if row.get("cycle_implied_ev_ebitda")], fallbacks["cycle_ev_ebitda"]),
                "price_to_book": median([row["price_to_book"] for row in group_rows if row.get("price_to_book")], fallbacks["price_to_book"]),
                "roe": median([row["roe"] for row in group_rows if (row.get("roe") or 0) > 0], fallbacks["roe"]),
                "growth": median([row["earnings_growth"] for row in group_rows if (row.get("earnings_growth") or 0) > 0], fallbacks["growth"]),
                "profit_margin": median([row["profit_margin"] for row in group_rows if (row.get("profit_margin") or 0) > 0], fallbacks["profit_margin"]),
                "ebitda_margin": median([row["ebitda_margin"] for row in group_rows if (row.get("ebitda_margin") or 0) > 0], fallbacks["ebitda_margin"]),
            }

        for profile in {row["valuation_profile"] for row in rows}:
            group_rows = [row for row in rows if row["valuation_profile"] == profile]
            output[f"profile:{profile}"] = metrics(group_rows)
        for sector in {str(row.get("sector") or "") for row in rows}:
            group_rows = [row for row in rows if row.get("sector") == sector]
            if len(group_rows) >= 4:
                output[f"sector:{sector}"] = metrics(group_rows)
        for peer_group in {str(row.get("peer_group") or "") for row in rows}:
            group_rows = [row for row in rows if row.get("peer_group") == peer_group]
            if len(group_rows) >= 4:
                output[f"peer:{peer_group}"] = metrics(group_rows)
        return output

    @staticmethod
    def _cyclical_market_multiples(row: dict[str, Any]) -> dict[str, float]:
        """Reconcile cyclical multiples with the normalized margins used in valuation."""

        revenue = positive(row.get("revenue"))
        market_cap = positive(row.get("market_cap"))
        price = positive(row.get("price"))
        shares = positive(row.get("shares"))
        profit_margin = positive(row.get("cycle_profit_margin"))
        ebitda_margin = positive(row.get("cycle_ebitda_margin"))
        if not revenue or not market_cap:
            return {}

        output: dict[str, float] = {}
        normalized_earnings = revenue * profit_margin if profit_margin else None
        if normalized_earnings:
            implied_pe = (
                price / (normalized_earnings / shares)
                if price and shares
                else market_cap / normalized_earnings
            )
            if 1.5 <= implied_pe <= 30.0:
                output["cycle_implied_pe"] = implied_pe

        normalized_ebitda = revenue * ebitda_margin if ebitda_margin else None
        if normalized_ebitda:
            enterprise_value = market_cap + max(number(row.get("debt")) or 0.0, 0.0) - max(
                number(row.get("cash")) or 0.0,
                0.0,
            )
            implied_ev_ebitda = enterprise_value / normalized_ebitda
            if 1.0 <= implied_ev_ebitda <= 20.0:
                output["cycle_implied_ev_ebitda"] = implied_ev_ebitda
        return output

    @staticmethod
    def _cyclical_margin_profile(fundamentals: dict[str, Any]) -> dict[str, float | int]:
        """Build a company-specific mid-cycle margin profile from up to eight quarters."""

        income_rows = fundamentals.get("quarterlyIncome")
        cash_flow_rows = fundamentals.get("quarterlyCashFlow")
        if not isinstance(income_rows, list):
            return {}

        clean_income = [
            row for row in income_rows[:8]
            if isinstance(row, dict) and positive(row.get("totalRevenue"))
        ]
        if len(clean_income) < 4:
            return {}

        def robust_margin(field: str, *, lower: float, upper: float) -> float | None:
            observations: list[tuple[float, float]] = []
            for item in clean_income:
                revenue = positive(item.get("totalRevenue"))
                numerator = number(item.get(field))
                if revenue and numerator is not None:
                    margin = numerator / revenue
                    if lower <= margin <= upper:
                        observations.append((numerator, revenue))
            if len(observations) < 4:
                return None
            margins = [numerator / revenue for numerator, revenue in observations]
            aggregate = sum(numerator for numerator, _ in observations) / sum(
                revenue for _, revenue in observations
            )
            return statistics.median(margins) * 0.55 + aggregate * 0.45

        profit_margin = robust_margin("netIncome", lower=-0.50, upper=0.60)
        ebitda_margin = robust_margin("ebitda", lower=-0.20, upper=0.80)

        revenue_by_period = {
            str(item.get("date") or "")[:10]: positive(item.get("totalRevenue"))
            for item in clean_income
        }
        fcf_observations: list[tuple[float, float]] = []
        if isinstance(cash_flow_rows, list):
            for item in cash_flow_rows[:8]:
                if not isinstance(item, dict):
                    continue
                revenue = revenue_by_period.get(str(item.get("date") or "")[:10])
                free_cash_flow = number(item.get("freeCashFlow"))
                if revenue and free_cash_flow is not None:
                    margin = free_cash_flow / revenue
                    if -0.50 <= margin <= 0.60:
                        fcf_observations.append((free_cash_flow, revenue))

        fcf_margin: float | None = None
        if len(fcf_observations) >= 4:
            fcf_margins = [value / revenue for value, revenue in fcf_observations]
            aggregate_fcf_margin = sum(value for value, _ in fcf_observations) / sum(
                revenue for _, revenue in fcf_observations
            )
            fcf_margin = statistics.median(fcf_margins) * 0.55 + aggregate_fcf_margin * 0.45

        output: dict[str, float | int] = {
            "cycle_observation_count": len(clean_income),
        }
        if profit_margin is not None:
            output["cycle_profit_margin"] = clamp(profit_margin, 0.02, 0.25)
        if ebitda_margin is not None:
            output["cycle_ebitda_margin"] = clamp(ebitda_margin, 0.06, 0.45)
        if fcf_margin is not None:
            output["cycle_fcf_margin"] = clamp(fcf_margin, 0.01, 0.25)
        return output

    @staticmethod
    def _cyclical_target_multiples(
        row: dict[str, Any],
        benchmark: dict[str, float],
        *,
        growth: float,
        risk_penalty: float,
    ) -> tuple[float, float]:
        """Set mid-cycle multiples without combining normalized results with spot TTM denominators."""

        roe = number(row.get("roe")) or 0.0
        peer_roe = number(benchmark.get("roe")) or 0.0
        base_pe = (
            positive(benchmark.get("cycle_pe"))
            or positive(benchmark.get("forward_pe"))
            or positive(benchmark.get("pe"))
            or 7.0
        )
        base_ev = (
            positive(benchmark.get("cycle_ev_ebitda"))
            or positive(benchmark.get("ev_ebitda"))
            or 5.0
        )
        target_pe = clamp(
            base_pe * (1 + growth * 0.30 + (roe - peer_roe) * 0.35 - risk_penalty * 0.20),
            4.0,
            11.0,
        )
        target_ev = clamp(
            base_ev * (1 + growth * 0.30 - risk_penalty * 0.30),
            3.0,
            10.0,
        )
        return target_pe, target_ev

    def _value_row(self, row: dict[str, Any], medians: dict[str, dict[str, float]], macro: dict[str, float]) -> None:
        profile = row["valuation_profile"]
        benchmark_key = f"peer:{row.get('peer_group')}"
        if benchmark_key not in medians:
            benchmark_key = f"sector:{row.get('sector')}"
        if benchmark_key not in medians:
            benchmark_key = f"profile:{profile}"
        sector = medians[benchmark_key]
        row["valuation_benchmark"] = benchmark_key.removeprefix("peer:").removeprefix("sector:").removeprefix("profile:")
        current_growth = statistics.mean([row.get("revenue_growth") or 0.0, row.get("earnings_growth") or 0.0])
        durable_growth_inputs = [
            value for value in (row.get("revenue_cagr_5y"), row.get("earnings_cagr_5y"))
            if value is not None
        ]
        if profile == "quality_compounder" and durable_growth_inputs:
            durable_growth = statistics.mean(durable_growth_inputs)
            growth = clamp(durable_growth * 0.65 + current_growth * 0.35, -0.03, 0.16)
        else:
            growth = clamp(current_growth, -0.08, 0.16)
        roe = row.get("roe") or 0.0
        margin = row.get("profit_margin") or 0.0
        beta = row.get("beta") or 1.15
        debt_equity = row.get("debt_to_equity")
        fcf_yield = (row.get("fcf") or 0.0) / row["market_cap"]
        missing_risk = 0.025 * sum(row.get(field) is None for field in ("beta", "roe", "earnings_growth"))
        leverage_risk = 0.0 if profile == "financial" else max(0.0, (debt_equity if debt_equity is not None else 2.0) - 1.5) * 0.025
        risk_penalty = clamp(max(0.0, beta - 1.0) * 0.07 + leverage_risk + missing_risk, 0.0, 0.28)
        risk_score = self._matrix_risk_score(row)
        quality = clamp(50 + roe * 90 + margin * 45 + fcf_yield * 100 + growth * 40 - risk_penalty * 100, 0, 100)

        risk_free = clamp(macro.get("selic", 0.145), 0.07, 0.20)
        inflation = clamp(macro.get("ipca12m", 0.045), 0.025, 0.09)
        cost_equity = clamp(risk_free + beta * 0.055 + risk_penalty * 0.20, 0.13, 0.29)
        wacc = clamp(risk_free + beta * 0.040 + risk_penalty * 0.18, 0.12, 0.26)
        terminal_growth = clamp(inflation + 0.005, 0.035, 0.065)

        methods: dict[str, float] = {}
        shares = row.get("shares")
        target_pe_bounds = {
            "financial": (6.0, 14.0),
            "real_estate": (5.0, 13.0),
            "utilities": (7.0, 16.0),
            "cyclical": (5.0, 13.0),
            "growth": (12.0, 30.0),
            "quality_compounder": (18.0, 34.0),
            "general": (7.0, 20.0),
        }[profile]
        cyclical_target_ev: float | None = None
        if profile == "quality_compounder":
            target_pe = clamp(
                18.0 + roe * 35.0 + max(0.0, growth) * 35.0 - risk_free * 25.0,
                *target_pe_bounds,
            )
        elif profile == "cyclical":
            target_pe, cyclical_target_ev = self._cyclical_target_multiples(
                row,
                sector,
                growth=growth,
                risk_penalty=risk_penalty,
            )
        else:
            target_pe = clamp(sector["pe"] * (1 + growth * 0.8 + (roe - sector["roe"]) * 0.7), *target_pe_bounds)
        normalized_eps = row.get("forward_eps") or row.get("eps")
        if profile != "financial" and normalized_eps and row.get("operating_cashflow") and row.get("shares"):
            cash_backed_eps = row["operating_cashflow"] * 0.85 / row["shares"]
            normalized_eps = min(normalized_eps, cash_backed_eps)
        # Spot earnings and spot EBITDA are diagnostics for cyclicals. Their
        # mid-cycle counterparts below are the valuation anchors.
        if normalized_eps and profile != "cyclical":
            methods["earnings"] = normalized_eps * target_pe

        if profile == "cyclical" and shares and row.get("revenue"):
            cycle_margin = row.get("cycle_profit_margin") or clamp(sector["profit_margin"], 0.035, 0.14)
            cycle_eps = row["revenue"] * cycle_margin / shares
            if cycle_eps > 0:
                methods["cycle_earnings"] = cycle_eps * target_pe

        if profile in ("financial", "real_estate"):
            book_value = row.get("book_value")
            if book_value:
                justified_pb = clamp(0.65 + max(0.0, roe - 0.08) * 6.0 + max(0.0, growth) * 1.2, 0.55, 2.8)
                methods["book"] = book_value * justified_pb
                excess_return = max(-0.03, roe - cost_equity)
                methods["residual"] = book_value + book_value * excess_return * 4.5
        else:
            dcf_row = row
            if profile == "cyclical" and row.get("cycle_fcf_margin") and row.get("revenue"):
                dcf_row = {
                    **row,
                    "fcf": row["revenue"] * row["cycle_fcf_margin"],
                }
            dcf = self._dcf_value(dcf_row, growth, wacc, terminal_growth, profile)
            if dcf:
                methods["dcf"] = dcf
            if shares and row.get("ebitda"):
                if profile == "quality_compounder":
                    target_ev = clamp(
                        12.0 + margin * 20.0 + max(0.0, growth) * 30.0 + max(0.0, roe - 0.20) * 15.0 - risk_free * 15.0,
                        12.0,
                        26.0,
                    )
                elif profile == "cyclical" and cyclical_target_ev is not None:
                    target_ev = cyclical_target_ev
                else:
                    target_ev = clamp(sector["ev_ebitda"] * (1 + growth * 0.7 - risk_penalty * 0.5), 3.0, 18.0)
                equity_value = row["ebitda"] * target_ev + row.get("cash", 0.0) - row.get("debt", 0.0)
                ev_value = positive(equity_value / shares)
                if ev_value and profile != "cyclical":
                    methods["enterprise"] = ev_value
                if profile == "cyclical" and row.get("revenue"):
                    cycle_ebitda_margin = row.get("cycle_ebitda_margin") or clamp(sector["ebitda_margin"], 0.08, 0.24)
                    cycle_ebitda = row["revenue"] * cycle_ebitda_margin
                    cycle_equity = cycle_ebitda * target_ev + row.get("cash", 0.0) - row.get("debt", 0.0)
                    cycle_ev_value = positive(cycle_equity / shares)
                    if cycle_ev_value:
                        methods["cycle_enterprise"] = cycle_ev_value
            if row.get("book_value"):
                if profile == "quality_compounder":
                    target_pb = clamp(2.0 + max(0.0, roe - cost_equity) * 25.0 + max(0.0, growth) * 12.0, 2.0, 12.0)
                else:
                    target_pb = clamp(sector["price_to_book"] * (1 + (roe - sector["roe"]) * 1.5), 0.45, 6.0)
                methods["book"] = row["book_value"] * target_pb

        dividend_yield = row.get("dividend_yield")
        if profile not in ("quality_compounder", "cyclical") and dividend_yield and 0.03 <= dividend_yield <= 0.20:
            implied_dividend = row["price"] * dividend_yield
            required_yield = clamp(cost_equity * (0.42 if profile in ("financial", "utilities") else 0.55), 0.055, 0.12)
            methods["dividend"] = implied_dividend / required_yield

        consensus = row.get("public_consensus_tp")
        if consensus and row.get("analyst_count", 0) > 0:
            methods["consensus"] = consensus

        if len(methods) < 3:
            row.update({
                "our_tp": 0.0,
                "upside_percent": -100.0,
                "expected_total_return_percent": -100.0,
                "status": "watchlist",
                "methods": methods,
                "risk_score": risk_score,
                "valuation_confidence": 0.0,
                "method_dispersion_percent": 100.0,
                "buy_in_models": {},
                "tp_validation_status": "review_required",
                "tp_validation_score": 0.0,
                "tp_validation_reasons": ["Insufficient valuation methods"],
                "consensus_gap_percent": None,
                "valuation_method_count": len(methods),
                "internal_method_count": len([name for name in methods if name != "consensus"]),
            })
            return

        raw_internal_values = [value for name, value in methods.items() if name != "consensus"]
        method_median = statistics.median(raw_internal_values or list(methods.values()))
        lower_bound, upper_bound = (0.35, 2.50) if profile == "quality_compounder" else (0.55, 1.80)
        normalized_methods = {name: clamp(value, method_median * lower_bound, method_median * upper_bound) for name, value in methods.items()}
        # Public consensus is an external cross-check with its own gap rule;
        # including it here would count the same disagreement twice.
        dispersion_values = [
            value for name, value in normalized_methods.items() if name != "consensus"
        ] or list(normalized_methods.values())
        method_dispersion = (
            (percentile(dispersion_values, 0.75) - percentile(dispersion_values, 0.25))
            / statistics.median(dispersion_values) * 100
            if method_median > 0 else 100.0
        )
        agreement_score = clamp(100 - method_dispersion * 2.0, 0, 100)
        model_coverage_score = clamp(len(normalized_methods) / 5 * 100, 0, 100)
        analyst_breadth_score = clamp((row.get("analyst_count") or 0) / 10 * 100, 0, 100)
        valuation_confidence = clamp(
            row["completeness"] * 100 * 0.25
            + model_coverage_score * 0.20
            + agreement_score * 0.20
            + analyst_breadth_score * 0.15
            + row.get("source_agreement_percent", 30.0) * 0.15
            + row["quote_quality"] * 0.05,
            0,
            100,
        )
        weights = self._method_weights(profile)
        internal_methods = {name: value for name, value in normalized_methods.items() if name != "consensus"}
        available_weight = sum(weights.get(name, 0.0) for name in internal_methods)
        if available_weight <= 0:
            available_weight = float(len(internal_methods))
            weights = {name: 1.0 for name in internal_methods}
        internal_tp = sum(value * weights.get(name, 0.0) for name, value in internal_methods.items()) / available_weight
        calibration_factor = self._calibration_factors.get(profile, self._calibration_factors.get("global", 1.0))
        calibration_factor = clamp(calibration_factor, 1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT)
        internal_tp *= calibration_factor
        consensus_for_blend = consensus if consensus and row.get("analyst_count", 0) > 0 else None
        consensus_weight = self._consensus_weight(row) if consensus_for_blend else 0.0
        our_tp = internal_tp * (1 - consensus_weight) + (consensus_for_blend or 0.0) * consensus_weight
        tp_validation = self._validate_target_price(
            row=row,
            methods=normalized_methods,
            internal_tp=internal_tp,
            consensus_tp=consensus_for_blend,
            our_tp=our_tp,
            valuation_confidence=valuation_confidence,
            method_dispersion=method_dispersion,
        )

        dynamic_required_return = clamp(macro.get("selic", 0.145), 0.07, 0.20) + 0.02
        expected_dividend = row["price"] * dividend_yield if dividend_yield and 0 < dividend_yield <= 0.20 else 0.0
        risk_premium = clamp(risk_score / 100 * 0.08, 0.0, 0.08)
        confidence_penalty = clamp((100 - valuation_confidence) / 100 * 0.06, 0.0, 0.06)
        valuation_discount = 1 + dynamic_required_return + risk_premium + confidence_penalty
        earnings_base = normalized_methods.get("earnings") or normalized_methods.get("cycle_earnings")
        enterprise_base = normalized_methods.get("enterprise") or normalized_methods.get("cycle_enterprise")
        goldman_base = enterprise_base or normalized_methods.get("book") or earnings_base
        buy_in_models: dict[str, float] = {}
        if normalized_methods.get("dcf"):
            buy_in_models["Morgan Stanley"] = normalized_methods["dcf"] / valuation_discount
        if earnings_base:
            buy_in_models["JPMorgan"] = earnings_base / valuation_discount
        if goldman_base:
            buy_in_models["Goldman Sachs"] = goldman_base / valuation_discount
        buy_in_models["Bridgewater"] = our_tp / (
            1 + dynamic_required_return + risk_premium * 1.50 + confidence_penalty
        )
        buy_in_models["BlackRock"] = (our_tp + expected_dividend) / (
            1 + dynamic_required_return + risk_premium * 0.50 + confidence_penalty * 0.50
        )
        framework_weights = {
            "Morgan Stanley": 0.30,
            "JPMorgan": 0.25,
            "Goldman Sachs": 0.20,
            "Bridgewater": 0.15,
            "BlackRock": 0.10,
        }
        framework_entry = robust_weighted_mean(buy_in_models, framework_weights)
        entry_return_hurdle = self._entry_return_hurdle_percent(macro)
        sustainable_growth = self._sustainable_growth(profile, growth)
        convergence_years = 3.0 if valuation_confidence >= MIN_VALUATION_CONFIDENCE and method_dispersion <= MAX_METHOD_DISPERSION else 5.0
        forward_tp = our_tp * (1 + sustainable_growth)
        hurdle_entry = (forward_tp + expected_dividend) / (1 + entry_return_hurdle / 100)
        annual_volatility = row.get("volatility_90d") or 0.35
        swing_buffer = clamp(annual_volatility * math.sqrt(10 / 252), 0.025, 0.12)
        raw_technical_entry = median([
            row.get("support_60d") or 0.0,
            (row.get("median_20d") or 0.0) * (1 - swing_buffer * 0.50),
            (row.get("low_20d") or 0.0) * (1 + swing_buffer * 0.25),
        ], row["price"] * (1 - swing_buffer))
        quarterly_drawdown = clamp(annual_volatility * math.sqrt(63 / 252), 0.10, 0.30)
        technical_floor = (row.get("last_close") or row["price"]) * (1 - quarterly_drawdown)
        technical_entry = max(raw_technical_entry, technical_floor)
        buy_in_models["Market Structure"] = technical_entry
        buy_in_models["Return Hurdle"] = hurdle_entry
        buy_in = min(framework_entry, hurdle_entry, technical_entry)
        upside = (our_tp / row["price"] - 1) * 100
        total_return = self._expected_12m_return(
            row["price"],
            our_tp,
            expected_dividend,
            sustainable_growth,
            convergence_years,
            valuation_confidence,
            method_dispersion,
            consensus_weight * 100,
        )
        distance = (row["price"] / buy_in - 1) * 100 if buy_in > 0 else 999.0

        relative_discount = median([
            sector["pe"] / row["pe"] if row.get("pe") else 0.0,
            sector["ev_ebitda"] / row["ev_ebitda"] if row.get("ev_ebitda") else 0.0,
            sector["price_to_book"] / row["price_to_book"] if row.get("price_to_book") else 0.0,
        ], 1.0)
        power_score = self._power_score(upside, risk_score, quality, valuation_confidence, distance)

        tp_upside_cutoff = self._tp_upside_cutoff_percent(macro)

        if (
            upside >= tp_upside_cutoff
            and distance <= MAX_ENTRY_DISTANCE
            and valuation_confidence >= MIN_VALUATION_CONFIDENCE
            and method_dispersion <= MAX_METHOD_DISPERSION
            and tp_validation["status"] == "validated"
        ):
            status = "full_match"
        elif upside >= max(tp_upside_cutoff - 5, 0) and distance <= 25 and valuation_confidence >= 60:
            status = "near_buy"
        else:
            status = "watchlist"

        row.update({
            "methods": normalized_methods,
            "internal_tp": internal_tp,
            "calibration_factor": calibration_factor,
            "consensus_weight_percent": consensus_weight * 100,
            "our_tp": our_tp,
            "upside_percent": upside,
            "expected_total_return_percent": total_return,
            "sustainable_growth": sustainable_growth,
            "convergence_years": convergence_years,
            "convergence_weight": self._convergence_weight(
                valuation_confidence,
                method_dispersion,
                consensus_weight * 100,
            ),
            "buy_in": buy_in,
            "buy_in_models": buy_in_models,
            "expected_dividend": expected_dividend,
            "price_vs_buy_in_percent": distance,
            "fcf_yield_percent": fcf_yield * 100 if row.get("fcf") else None,
            "score": power_score,
            "risk_score": risk_score,
            "operating_quality": quality,
            "valuation_confidence": valuation_confidence,
            "method_dispersion_percent": method_dispersion,
            "tp_validation_status": tp_validation["status"],
            "tp_validation_score": tp_validation["score"],
            "tp_validation_reasons": tp_validation["reasons"],
            "consensus_gap_percent": tp_validation["consensus_gap_percent"],
            "valuation_method_count": tp_validation["valuation_method_count"],
            "internal_method_count": tp_validation["internal_method_count"],
            "quality_score": round((row["quote_quality"] * 0.30) + (row["completeness"] * 100 * 0.70)),
            "status": status,
            "thesis": self._thesis(row, relative_discount, growth, fcf_yield),
            "risk": self._risk(row, risk_penalty),
        })

    @staticmethod
    def _validate_target_price(
        *,
        row: dict[str, Any],
        methods: dict[str, float],
        internal_tp: float,
        consensus_tp: float | None,
        our_tp: float,
        valuation_confidence: float,
        method_dispersion: float,
    ) -> dict[str, Any]:
        internal_method_count = len([name for name in methods if name != "consensus"])
        valuation_method_count = len(methods)
        analyst_count = int(row.get("analyst_count") or 0)
        source_count = int(row.get("data_source_count") or 0)
        source_comparisons = int(row.get("source_comparison_count") or 0)
        source_agreement = float(row.get("source_agreement_percent") or 0.0)
        consensus_gap = (
            abs(internal_tp / consensus_tp - 1) * 100
            if internal_tp > 0 and consensus_tp and consensus_tp > 0
            else None
        )
        tp_upside = (our_tp / row["price"] - 1) * 100 if row.get("price") else math.inf

        fundamentals_age = B3ScreenerService._fundamentals_age_days(row.get("fundamentals_as_of"))

        model_score = clamp(internal_method_count / 4 * 100, 0, 100)
        dispersion_score = clamp(100 - method_dispersion * 2, 0, 100)
        source_evidence_score = clamp(source_comparisons / 5 * 100, 0, 100)
        analyst_score = clamp(analyst_count / 8 * 100, 0, 100)
        convergence_score = clamp(100 - (consensus_gap if consensus_gap is not None else 100) * 2.5, 0, 100)
        freshness_score = (
            clamp(100 - max(fundamentals_age - 7, 0) / max(MAX_FUNDAMENTALS_AGE_DAYS - 7, 1) * 100, 0, 100)
            if fundamentals_age is not None else 0.0
        )
        validation_score = clamp(
            valuation_confidence * 0.20
            + model_score * 0.15
            + dispersion_score * 0.15
            + source_agreement * 0.15
            + source_evidence_score * 0.10
            + analyst_score * 0.10
            + convergence_score * 0.10
            + freshness_score * 0.05,
            0,
            100,
        )

        reasons: list[str] = []
        if valuation_method_count < 4 or internal_method_count < 3:
            reasons.append("Fewer than three independent internal methods")
        if valuation_confidence < MIN_VALUATION_CONFIDENCE:
            reasons.append("Valuation confidence below minimum")
        if method_dispersion > MAX_METHOD_DISPERSION:
            reasons.append("Valuation methods do not converge")
        if source_count < 2 or source_comparisons < MIN_TP_SOURCE_COMPARISONS:
            reasons.append("Insufficient independent source evidence")
        if source_agreement < MIN_TP_SOURCE_AGREEMENT:
            reasons.append("Brapi and EODHD fundamentals diverge")
        if consensus_tp is None or analyst_count < MIN_TP_ANALYSTS:
            reasons.append("Insufficient public analyst consensus")
        if consensus_gap is None or consensus_gap > MAX_TP_CONSENSUS_GAP:
            reasons.append("Internal model is too far from public consensus")
        if fundamentals_age is None or fundamentals_age > MAX_FUNDAMENTALS_AGE_DAYS:
            reasons.append("Fundamentals are missing or stale")
        if not -60.0 <= tp_upside <= MAX_VALIDATED_TP_UPSIDE:
            reasons.append("Target price is outside the plausibility range")
        if validation_score < MIN_TP_VALIDATION_SCORE:
            reasons.append("Composite TP validation score below minimum")

        return {
            "status": "validated" if not reasons else "review_required",
            "score": round(validation_score, 2),
            "reasons": reasons,
            "consensus_gap_percent": round(consensus_gap, 2) if consensus_gap is not None else None,
            "valuation_method_count": valuation_method_count,
            "internal_method_count": internal_method_count,
        }

    @staticmethod
    def _fundamentals_age_days(value: Any) -> int | None:
        if not value:
            return None
        try:
            fundamentals_date = date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
        return max((datetime.now(ZoneInfo("America/Sao_Paulo")).date() - fundamentals_date).days, 0)

    @staticmethod
    def _ir_freshness(fundamentals_as_of: Any, event: dict[str, Any] | None) -> dict[str, Any]:
        if not event:
            return {
                "ir_status": "unavailable",
                "latest_ir_event_at": None,
                "latest_ir_event_type": None,
            }
        current = bool(event.get("reviewed_at") or event.get("valuation_status") == "incorporated")
        reference_date = event.get("reference_date")
        if (
            not current
            and event.get("event_type") == "Financial Results"
            and reference_date
            and fundamentals_as_of
        ):
            current = str(fundamentals_as_of)[:10] >= str(reference_date)[:10]
        return {
            "ir_status": "current" if current else "pending_review",
            "latest_ir_event_at": event.get("published_at"),
            "latest_ir_event_type": event.get("event_type"),
        }

    @staticmethod
    def _insider_net_signal(activity: dict[str, Any] | None) -> float:
        """-1..1: net insider selling to net insider buying over the lookback
        window (Tatooine Updates: CVM VLMO art. 11 ICVM 44), scaled down when
        the sample is thin so one lone filing can't swing it to the full
        extent. 0.0 (neutral) when there's no recent activity."""
        if not activity:
            return 0.0
        total = int(activity.get("total_count") or 0)
        if total <= 0:
            return 0.0
        net_ratio = (int(activity.get("buy_count") or 0) - int(activity.get("sell_count") or 0)) / total
        confidence = min(1.0, total / INSIDER_SIGNAL_MIN_TRANSACTIONS_FOR_FULL_WEIGHT)
        return net_ratio * confidence

    @staticmethod
    def _disclosure_risk_signal(ir_status: str, materiality: str | None) -> float:
        """0..1 governance risk weight for a disclosure still pending review
        (Tatooine Updates: CVM/RI), scaled by the filing's own materiality so
        a high-materiality item (restatement, M&A) pressures governance_risk
        harder than a routine low-materiality one. 0.0 once the disclosure is
        current/incorporated."""
        if ir_status != "pending_review":
            return 0.0
        return DISCLOSURE_MATERIALITY_WEIGHTS.get(materiality or "medium", 0.5)

    @classmethod
    def _provisional_eligibility(cls, row: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not positive(row.get("our_tp")) or not positive(row.get("buy_in")):
            reasons.append("Target price or buy-in is unavailable")
        if int(row.get("internal_method_count") or 0) < 3:
            reasons.append("Fewer than three internal valuation methods")
        if float(row.get("valuation_confidence") or 0.0) < PROVISIONAL_MIN_VALUATION_CONFIDENCE:
            reasons.append("Provisional confidence below minimum")
        if float(row.get("method_dispersion_percent") or 100.0) > PROVISIONAL_MAX_METHOD_DISPERSION:
            reasons.append("Provisional valuation methods do not converge")
        if int(row.get("data_source_count") or 0) < 2:
            reasons.append("A second fundamental source is unavailable")
        if int(row.get("source_comparison_count") or 0) < PROVISIONAL_MIN_SOURCE_COMPARISONS:
            reasons.append("Too few cross-source comparisons")
        if float(row.get("source_agreement_percent") or 0.0) < PROVISIONAL_MIN_SOURCE_AGREEMENT:
            reasons.append("Cross-source agreement is too low")
        fundamentals_age = cls._fundamentals_age_days(row.get("fundamentals_as_of"))
        if fundamentals_age is None or fundamentals_age > PROVISIONAL_MAX_FUNDAMENTALS_AGE_DAYS:
            reasons.append(f"Fundamentals are missing or older than {PROVISIONAL_MAX_FUNDAMENTALS_AGE_DAYS} days")
        price = positive(row.get("price"))
        target = positive(row.get("our_tp"))
        tp_upside = (target / price - 1) * 100 if price and target else math.inf
        if not -60.0 <= tp_upside <= MAX_VALIDATED_TP_UPSIDE:
            reasons.append("Target price is outside the plausibility range")
        return not reasons, reasons

    @staticmethod
    def _matrix_risk_score(row: dict[str, Any]) -> float:
        beta = row.get("beta") if row.get("beta") is not None else 1.15
        volatility = row.get("volatility_90d") if row.get("volatility_90d") is not None else 0.35
        beta_score = clamp((beta - 0.60) / 1.40 * 100, 0, 100)
        volatility_score = clamp((volatility - 0.12) / 0.48 * 100, 0, 100)
        market_risk = volatility_score * 0.60 + beta_score * 0.40

        if row["valuation_profile"] == "financial":
            roe = row.get("roe") if row.get("roe") is not None else 0.08
            balance_sheet_score = clamp(55 - (roe - 0.12) * 180, 30, 75)
        else:
            debt_equity = row.get("debt_to_equity") if row.get("debt_to_equity") is not None else 2.0
            balance_sheet_score = clamp((debt_equity - 0.50) / 2.50 * 100, 0, 100)

        earnings_growth = row.get("earnings_growth")
        margin = row.get("profit_margin")
        trend_risk = 55.0 if earnings_growth is None else clamp((0.10 - earnings_growth) / 0.25 * 100, 0, 100)
        margin_risk = 55.0 if margin is None else clamp((0.08 - margin) / 0.18 * 100, 0, 100)
        earnings_risk = trend_risk * 0.70 + margin_risk * 0.30
        liquidity_risk = clamp((7.8 - math.log10(max(row.get("adtv_90d") or MIN_ADTV_90D, 1))) * 55, 0, 100)
        insider_net_signal = row.get("insider_net_signal") or 0.0
        pending_disclosure_risk = row.get("pending_disclosure_risk") or 0.0
        governance_risk = clamp(
            50.0
            - insider_net_signal * INSIDER_GOVERNANCE_MAX_SWING
            + pending_disclosure_risk * DISCLOSURE_GOVERNANCE_MAX_SWING,
            30.0,
            70.0,
        )
        macro_risk = {
            "financial": 52.0,
            "real_estate": 62.0,
            "utilities": 35.0,
            "cyclical": 65.0,
            "growth": 50.0,
            "quality_compounder": 35.0,
            "general": 45.0,
        }[row["valuation_profile"]]
        return clamp(
            market_risk * 0.25
            + balance_sheet_score * 0.25
            + earnings_risk * 0.20
            + liquidity_risk * 0.10
            + governance_risk * 0.10
            + macro_risk * 0.10,
            0,
            100,
        )

    @staticmethod
    def _power_score(
        tp_upside: float,
        risk_score: float,
        operating_quality: float,
        valuation_confidence: float,
        price_vs_buy_in: float,
    ) -> float:
        return_score = clamp(tp_upside, 0, 100)
        entry_score = 100 if price_vs_buy_in <= 0 else clamp(100 - price_vs_buy_in / MAX_ENTRY_DISTANCE * 100, 0, 100)
        return clamp(
            return_score * 0.35
            + (100 - risk_score) * 0.25
            + operating_quality * 0.15
            + valuation_confidence * 0.15
            + entry_score * 0.10,
            0,
            100,
        )

    @staticmethod
    def _sustainable_growth(profile: str, observed_growth: float) -> float:
        if profile == "cyclical":
            return clamp(observed_growth, -0.01, 0.04)
        if profile in ("financial", "utilities", "real_estate"):
            return clamp(observed_growth, 0.00, 0.07)
        if profile == "quality_compounder":
            return clamp(observed_growth, 0.04, 0.10)
        return clamp(observed_growth, -0.02, 0.09)

    @staticmethod
    def _expected_12m_return(
        price: float,
        target_price: float,
        expected_dividend: float,
        sustainable_growth: float,
        convergence_years: float,
        valuation_confidence: float = 50.0,
        method_dispersion_percent: float = 100.0,
        consensus_weight_percent: float = 0.0,
    ) -> float:
        if price <= 0 or target_price <= 0:
            return -100.0
        shareholder_yield = expected_dividend / price
        fundamental_carry = sustainable_growth + shareholder_yield
        annualized_valuation_reversion = (target_price / price) ** (1 / max(convergence_years, 1.0)) - 1
        convergence_weight = B3ScreenerService._convergence_weight(
            valuation_confidence,
            method_dispersion_percent,
            consensus_weight_percent,
        )
        return (fundamental_carry + annualized_valuation_reversion * convergence_weight) * 100

    @staticmethod
    def _convergence_weight(
        valuation_confidence: float,
        method_dispersion_percent: float,
        consensus_weight_percent: float,
    ) -> float:
        confidence = clamp(valuation_confidence / 100, 0, 1)
        agreement = clamp(1 - method_dispersion_percent / 100, 0, 1)
        public_confirmation = clamp(consensus_weight_percent / 100, 0, CONSENSUS_WEIGHT) * 0.75
        return clamp(0.15 + 0.35 * confidence * agreement + public_confirmation, 0.15, 0.65)

    @staticmethod
    def _tp_upside_cutoff_percent(macro: dict[str, float]) -> float:
        dynamic_hurdle = (clamp(macro.get("selic", 0.145), 0.07, 0.20) + TP_UPSIDE_PREMIUM) * 100
        return dynamic_hurdle

    @staticmethod
    def _entry_return_hurdle_percent(macro: dict[str, float]) -> float:
        return (clamp(macro.get("selic", 0.145), 0.07, 0.20) + 0.02) * 100

    @staticmethod
    def _risk_cutoff(rows: list[dict[str, Any]]) -> float:
        relative_cutoff = signed_percentile([row.get("risk_score", 50.0) for row in rows], 0.50, 50.0)
        return min(ABSOLUTE_LOW_RISK_LIMIT, relative_cutoff)

    @staticmethod
    def _quadrant(expected_return: float, risk_score: float, return_cutoff: float, risk_cutoff: float) -> str:
        high_return = expected_return >= return_cutoff
        high_risk = risk_score >= risk_cutoff
        return (
            "high_return_high_risk" if high_return and high_risk
            else "high_return_low_risk" if high_return
            else "low_return_high_risk" if high_risk
            else "low_return_low_risk"
        )

    @staticmethod
    def _matrix_axis_position(value: float, cutoff: float, low: float, high: float) -> float:
        if value < cutoff:
            denominator = max(cutoff - low, 0.01)
            return clamp(4 + (value - low) / denominator * 44, 4, 48)
        denominator = max(high - cutoff, 0.01)
        return clamp(52 + (value - cutoff) / denominator * 44, 52, 96)

    def _build_matrix(self, generated_at: datetime) -> MatrixPowerResponse:
        eligible_rows: list[dict[str, Any]] = []
        for source_row in self._matrix_rows:
            row = dict(source_row)
            if not positive(row.get("our_tp")) or not positive(row.get("buy_in")):
                continue
            if row.get("tp_validation_status") == "validated":
                row["signal_quality"] = "validated"
                eligible_rows.append(row)
                continue
            provisional, provisional_reasons = self._provisional_eligibility(row)
            if provisional:
                row["signal_quality"] = "provisional"
                row["provisional_reasons"] = provisional_reasons
                eligible_rows.append(row)
        deduped: dict[str, dict[str, Any]] = {}
        for row in sorted(
            eligible_rows,
            key=lambda item: (
                item.get("signal_quality") == "validated",
                item.get("adtv_90d") or 0.0,
            ),
            reverse=True,
        ):
            deduped.setdefault(row["issuer"], row)
        rows = list(deduped.values())
        try:
            latest_quotes = self._quotes([row["symbol"] for row in rows]) if rows else {}
        except Exception:
            # Live prices improve placement but must never erase a valid matrix.
            latest_quotes = {}

        tp_upside_cutoff = self._tp_upside_cutoff_percent(self._matrix_macro)
        risk_cutoff = self._risk_cutoff(rows)
        raw_items: list[dict[str, Any]] = []
        for row in rows:
            quote = latest_quotes.get(row["symbol"])
            price = positive(quote.price) if quote else positive(row.get("price"))
            if not price:
                continue
            expected_return = self._expected_12m_return(
                price,
                row["our_tp"],
                row.get("expected_dividend", 0.0),
                row.get("sustainable_growth", 0.0),
                row.get("convergence_years", 5.0),
                row.get("valuation_confidence", 0.0),
                row.get("method_dispersion_percent", 100.0),
                row.get("consensus_weight_percent", 0.0),
            )
            tp_upside = (row["our_tp"] / price - 1) * 100
            price_vs_buy_in = (price / row["buy_in"] - 1) * 100
            risk_score = row.get("risk_score", 50.0)
            power_score = self._power_score(
                tp_upside,
                risk_score,
                row.get("operating_quality", 50.0),
                row.get("valuation_confidence", 0.0),
                price_vs_buy_in,
            )
            quadrant = self._quadrant(tp_upside, risk_score, tp_upside_cutoff, risk_cutoff)
            raw_items.append({
                "row": row,
                "quote": quote,
                "price": price,
                "expected_return": expected_return,
                "tp_upside": tp_upside,
                "price_vs_buy_in": price_vs_buy_in,
                "risk_score": risk_score,
                "power_score": power_score,
                "quadrant": quadrant,
            })

        returns = [item["tp_upside"] for item in raw_items]
        risks = [item["risk_score"] for item in raw_items]
        return_low = min(signed_percentile(returns, 0.05, tp_upside_cutoff - 20), tp_upside_cutoff - 1)
        return_high = max(signed_percentile(returns, 0.95, tp_upside_cutoff + 20), tp_upside_cutoff + 1)
        risk_low = min(signed_percentile(risks, 0.05, risk_cutoff - 20), risk_cutoff - 1)
        risk_high = max(signed_percentile(risks, 0.95, risk_cutoff + 20), risk_cutoff + 1)

        items: list[MatrixPowerItem] = []
        for item in sorted(raw_items, key=lambda value: value["tp_upside"], reverse=True):
            row = item["row"]
            quote = item["quote"]
            symbol_hash = sum((index + 1) * ord(character) for index, character in enumerate(row["symbol"]))
            jitter_x = ((symbol_hash % 7) - 3) * 0.35
            jitter_y = (((symbol_hash // 7) % 7) - 3) * 0.35
            x_position = self._matrix_axis_position(item["risk_score"], risk_cutoff, risk_low, risk_high)
            y_position = self._matrix_axis_position(item["tp_upside"], tp_upside_cutoff, return_low, return_high)
            x_position = clamp(x_position + jitter_x, 4, 48) if x_position < 50 else clamp(x_position + jitter_x, 52, 96)
            y_position = clamp(y_position + jitter_y, 4, 48) if y_position < 50 else clamp(y_position + jitter_y, 52, 96)
            items.append(MatrixPowerItem(
                symbol=row["symbol"],
                name=row["name"],
                logo_url=row.get("logo_url"),
                sector=row["sector"],
                industry=row.get("subsector"),
                peer_group=row.get("peer_group"),
                sector_source=row.get("sector_source"),
                sector_confidence=row.get("sector_confidence"),
                valuation_profile=row["valuation_profile"],
                price=round(item["price"], 2),
                change_percent=round(quote.change_percent, 2) if quote and quote.change_percent is not None else row.get("change_percent"),
                our_tp=round(row["our_tp"], 2),
                internal_tp=round(row.get("internal_tp", row["our_tp"]), 2),
                public_consensus_tp=round(row["public_consensus_tp"], 2) if row.get("public_consensus_tp") else None,
                analyst_count=row.get("analyst_count") or None,
                consensus_weight_percent=round(row.get("consensus_weight_percent", 0.0), 1),
                expected_return_percent=round(item["expected_return"], 2),
                tp_upside_percent=round(item["tp_upside"], 2),
                buy_in=round(row["buy_in"], 2),
                price_vs_buy_in_percent=round(item["price_vs_buy_in"], 2),
                risk_score=round(item["risk_score"], 2),
                power_score=round(item["power_score"], 2),
                valuation_confidence=round(row.get("valuation_confidence", 0.0), 2),
                method_dispersion_percent=round(row.get("method_dispersion_percent", 100.0), 2),
                data_source_count=row.get("data_source_count", 1),
                source_agreement_percent=round(row.get("source_agreement_percent", 30.0), 2),
                fundamentals_as_of=row.get("fundamentals_as_of"),
                ir_status=row.get("ir_status", "unavailable"),
                latest_ir_event_at=row.get("latest_ir_event_at"),
                latest_ir_event_type=row.get("latest_ir_event_type"),
                tp_validation_score=round(row.get("tp_validation_score", 0.0), 2),
                tp_validation_reasons=row.get("tp_validation_reasons", []),
                consensus_gap_percent=row.get("consensus_gap_percent"),
                valuation_method_count=row.get("valuation_method_count", 0),
                internal_method_count=row.get("internal_method_count", 0),
                signal_quality=row.get("signal_quality", "provisional"),
                beta=round(row["beta"], 2) if row.get("beta") is not None else None,
                volatility_90d_percent=round(row["volatility_90d"] * 100, 2) if row.get("volatility_90d") is not None else None,
                quadrant=item["quadrant"],
                x_percent=round(x_position, 2),
                y_percent=round(y_position, 2),
                as_of=quote.as_of if quote else row["as_of"],
            ))

        validated_count = sum(item.signal_quality == "validated" for item in items)
        provisional_count = sum(item.signal_quality == "provisional" for item in items)
        coverage_audit = dict(self._matrix_coverage_audit)
        coverage_audit["plotted"] = len(items)
        coverage_audit["validated_plotted"] = validated_count
        coverage_audit["provisional_plotted"] = provisional_count
        coverage_audit["valuation_review"] = max(
            coverage_audit.get("calculated_tp", 0) - validated_count - provisional_count,
            0,
        )

        return MatrixPowerResponse(
            source=self._source_label(),
            methodology_name=METHODOLOGY_NAME,
            methodology_version=METHODOLOGY_VERSION,
            universe_size=self._matrix_universe_size or UNIVERSE_LIMIT,
            source_eligible_count=len(self._matrix_rows),
            item_count=len(items),
            validated_count=validated_count,
            provisional_count=provisional_count,
            coverage_audit=coverage_audit,
            tp_upside_cutoff_percent=round(tp_upside_cutoff, 2),
            risk_cutoff=round(risk_cutoff, 2),
            quote_refresh_seconds=MATRIX_REFRESH_SECONDS,
            provider_delay_minutes=MATRIX_PROVIDER_DELAY_MINUTES,
            basis_generated_at=self._matrix_basis_at or generated_at,
            generated_at=generated_at,
            items=items,
            methodology={
                "return": "Dark Side and Last Jedi use raw C3PO TP upside as the return axis and require it to exceed live Selic + 6 p.p. Expected Return 12M remains an analytical estimate, not an eligibility gate.",
                "risk": "25% market, 25% balance sheet, 20% earnings, 10% liquidity, 10% governance proxy and 10% macro/event risk; low risk also has an absolute 40/100 ceiling.",
                "power": "Power Score combines 35% C3PO TP upside, 25% inverse risk, 15% operating quality, 15% valuation confidence and 10% entry discipline.",
                "universe": "B3 issuers that passed liquidity, size, history and fundamental quality gates; EODHD All-In-One now fills missing fundamentals and price history before exclusion.",
                "confidence": f"Validated signals retain every existing gate. Provisional signals require three internal methods, two providers, at least {PROVISIONAL_MIN_SOURCE_COMPARISONS} cross-source comparisons, confidence >= {PROVISIONAL_MIN_VALUATION_CONFIDENCE:.0f}, dispersion <= {PROVISIONAL_MAX_METHOD_DISPERSION:.0f}% and fundamentals no older than {PROVISIONAL_MAX_FUNDAMENTALS_AGE_DAYS} days; they never enter Candidate Stocks.",
                "refresh": "Quotes refresh automatically every 60 seconds; Brapi prices are delayed about five minutes.",
            },
        )

    @staticmethod
    def _score_weights(_: dict[str, float]) -> dict[str, float]:
        return dict(C3PO_VALUATION_POLICY.score_weights)

    @staticmethod
    def _method_weights(profile: str) -> dict[str, float]:
        return {
            "financial": {"dcf": 0.05, "earnings": 0.20, "book": 0.15, "residual": 0.30, "dividend": 0.20},
            "real_estate": {"dcf": 0.05, "earnings": 0.20, "book": 0.30, "residual": 0.20, "dividend": 0.15},
            "utilities": {"dcf": 0.30, "enterprise": 0.15, "earnings": 0.15, "dividend": 0.25, "book": 0.05},
            "cyclical": {"dcf": 0.15, "cycle_enterprise": 0.40, "cycle_earnings": 0.35, "book": 0.10},
            "growth": {"dcf": 0.35, "enterprise": 0.20, "earnings": 0.25, "book": 0.05, "dividend": 0.05},
            "quality_compounder": {"dcf": 0.15, "enterprise": 0.30, "earnings": 0.35, "book": 0.10},
            "general": {"dcf": 0.30, "enterprise": 0.20, "earnings": 0.25, "book": 0.10, "dividend": 0.05},
        }[profile]

    @staticmethod
    def _dcf_value(row: dict[str, Any], growth: float, wacc: float, terminal_growth: float, profile: str) -> float | None:
        fcf = row.get("fcf")
        shares = row.get("shares")
        if not fcf or not shares or wacc <= terminal_growth:
            return None
        operating_cashflow = row.get("operating_cashflow")
        normalizers = [fcf]
        if operating_cashflow:
            normalizers.append(operating_cashflow * 0.75)
        if row.get("ebitda"):
            normalizers.append(row["ebitda"] * 0.60)
        normalized_fcf = statistics.median(normalizers) if profile == "quality_compounder" else min(normalizers)
        if profile == "cyclical":
            normalized_fcf *= 0.82
        forecast_growth = clamp(growth, -0.03, 0.11 if profile != "growth" else 0.14)
        present_value = 0.0
        projected = normalized_fcf
        for year in range(1, 6):
            fade = 1 - (year - 1) / 8
            projected *= 1 + forecast_growth * fade
            present_value += projected / ((1 + wacc) ** year)
        terminal = projected * (1 + terminal_growth) / (wacc - terminal_growth)
        enterprise_value = present_value + terminal / ((1 + wacc) ** 5)
        equity_value = enterprise_value + row.get("cash", 0.0) - row.get("debt", 0.0)
        return positive(equity_value / shares)

    @staticmethod
    def _thesis(row: dict[str, Any], relative_discount: float, growth: float, fcf_yield: float) -> str:
        drivers: list[str] = []
        if relative_discount >= 1.20:
            drivers.append("discount to profile peers")
        if growth >= 0.08:
            drivers.append("positive operating trend")
        if fcf_yield >= 0.06:
            drivers.append("strong free-cash-flow yield")
        if (row.get("roe") or 0) >= 0.18:
            drivers.append("high return on equity")
        if not drivers:
            drivers.append("balanced valuation and operating quality")
        return f"{row['valuation_profile'].title()} model: " + "; ".join(drivers[:2]) + "."

    @staticmethod
    def _risk(row: dict[str, Any], risk_penalty: float) -> str:
        risks: list[str] = []
        if row["valuation_profile"] != "financial" and (row.get("debt_to_equity") or 0) > 2.0:
            risks.append("leverage")
        if (row.get("beta") or 1.15) > 1.25:
            risks.append("market sensitivity")
        if (row.get("earnings_growth") or 0) < 0:
            risks.append("negative earnings trend")
        if risk_penalty < 0.04 and not risks:
            risks.append("sector cycle and execution")
        return "Monitor " + ", ".join(risks[:2]) + "."

    @classmethod
    def _rank(cls, rows: list[dict[str, Any]], macro: dict[str, float]) -> tuple[list[B3Candidate], float, float]:
        valued_rows = [
            row for row in rows
            if positive(row.get("our_tp"))
            and positive(row.get("buy_in"))
            and row.get("tp_validation_status") == "validated"
        ]
        issuer_rows: dict[str, dict[str, Any]] = {}
        for row in sorted(valued_rows, key=lambda item: item.get("adtv_90d") or 0.0, reverse=True):
            issuer_rows.setdefault(row["issuer"], row)
        valued_issuers = list(issuer_rows.values())
        tp_upside_cutoff = cls._tp_upside_cutoff_percent(macro)
        risk_cutoff = cls._risk_cutoff(valued_issuers)
        strict_matches = [row for row in rows if row.get("status") == "full_match"]
        power_zone_matches = [
            row for row in strict_matches
            if cls._quadrant(row["upside_percent"], row.get("risk_score", 100.0), tp_upside_cutoff, risk_cutoff)
            == "high_return_low_risk"
        ]
        deduped: dict[str, dict[str, Any]] = {}
        for row in sorted(power_zone_matches, key=lambda item: (item["upside_percent"], item["score"]), reverse=True):
            deduped.setdefault(row["issuer"], row)
        selected = sorted(
            deduped.values(),
            key=lambda item: (item["upside_percent"], item["score"]),
            reverse=True,
        )[:10]
        output: list[B3Candidate] = []
        for rank, row in enumerate(selected, 1):
            output.append(B3Candidate(
                rank=rank,
                symbol=row["symbol"],
                name=row["name"],
                logo_url=row["logo_url"],
                sector=row["sector"],
                industry=row.get("subsector"),
                peer_group=row.get("peer_group"),
                sector_source=row.get("sector_source"),
                sector_confidence=row.get("sector_confidence"),
                valuation_profile=row["valuation_profile"],
                price=round(row["price"], 2),
                change_percent=round(row["change_percent"], 2) if row.get("change_percent") is not None else None,
                volume=row["volume"],
                average_daily_value_90d=round(row["adtv_90d"], 2),
                market_cap=row["market_cap"],
                our_tp=round(row["our_tp"], 2),
                internal_tp=round(row.get("internal_tp", row["our_tp"]), 2),
                consensus_weight_percent=round(row.get("consensus_weight_percent", 0.0), 1),
                upside_percent=round(row["upside_percent"], 2),
                expected_total_return_percent=round(row["expected_total_return_percent"], 2),
                buy_in=round(row["buy_in"], 2),
                price_vs_buy_in_percent=round(row["price_vs_buy_in_percent"], 2),
                buy_in_models={name: round(value, 2) for name, value in row["buy_in_models"].items()},
                public_consensus_tp=round(row["public_consensus_tp"], 2) if row.get("public_consensus_tp") else None,
                analyst_count=row.get("analyst_count") or None,
                pe=round(row["pe"], 2) if row.get("pe") else None,
                forward_pe=round(row["forward_pe"], 2) if row.get("forward_pe") else None,
                ev_ebitda=round(row["ev_ebitda"], 2) if row.get("ev_ebitda") else None,
                peg=round(row["peg"], 2) if row.get("peg") else None,
                price_to_book=round(row["price_to_book"], 2) if row.get("price_to_book") else None,
                roe_percent=round(row["roe"] * 100, 2) if row.get("roe") is not None else None,
                fcf_yield_percent=round(row["fcf_yield_percent"], 2) if row.get("fcf_yield_percent") is not None else None,
                score=round(row["score"], 1),
                risk_score=round(row["risk_score"], 1),
                valuation_confidence=round(row["valuation_confidence"], 1),
                method_dispersion_percent=round(row["method_dispersion_percent"], 1),
                data_source_count=row.get("data_source_count", 1),
                source_agreement_percent=round(row.get("source_agreement_percent", 30.0), 1),
                fundamentals_as_of=row.get("fundamentals_as_of"),
                ir_status=row.get("ir_status", "unavailable"),
                latest_ir_event_at=row.get("latest_ir_event_at"),
                latest_ir_event_type=row.get("latest_ir_event_type"),
                tp_validation_score=round(row.get("tp_validation_score", 0.0), 1),
                tp_validation_reasons=row.get("tp_validation_reasons", []),
                consensus_gap_percent=row.get("consensus_gap_percent"),
                valuation_method_count=row.get("valuation_method_count", 0),
                internal_method_count=row.get("internal_method_count", 0),
                quality_score=row["quality_score"],
                status=row["status"],
                thesis=row["thesis"],
                risk=row["risk"],
                as_of=row["as_of"],
            ))
        return output, tp_upside_cutoff, risk_cutoff

    def _persist_snapshot(self, response: B3CandidateResponse, macro: dict[str, float]) -> None:
        score_weights = self._score_weights(macro)
        parameters = {
            "universe_limit": UNIVERSE_LIMIT,
            "ranking": "c3po_tp_upside_desc_inside_matrix_power_zone",
            "minimum_price": MIN_PRICE,
            "minimum_market_cap": MIN_MARKET_CAP,
            "minimum_adtv_90d": MIN_ADTV_90D,
            "minimum_history_days": MIN_HISTORY_DAYS,
            "tp_upside_hurdle": "Raw C3PO TP upside above live Selic + 6 percentage points",
            "expected_return_role": "Analytical estimate only; not an eligibility gate",
            "maximum_buy_in_distance_percent": MAX_ENTRY_DISTANCE,
            "maximum_risk": "strictly below both 40/100 and the eligible-universe median risk score",
            "minimum_valuation_confidence": MIN_VALUATION_CONFIDENCE,
            "maximum_method_dispersion_percent": MAX_METHOD_DISPERSION,
            "minimum_tp_validation_score": MIN_TP_VALIDATION_SCORE,
            "maximum_internal_consensus_gap_percent": MAX_TP_CONSENSUS_GAP,
            "minimum_tp_source_agreement_percent": MIN_TP_SOURCE_AGREEMENT,
            "maximum_fundamentals_age_days": MAX_FUNDAMENTALS_AGE_DAYS,
            "minimum_fundamental_completeness": 0.60,
            "macro": macro,
            "sector_profiles": ["financial", "real_estate", "utilities", "cyclical", "growth", "quality_compounder", "general"],
            "sector_taxonomy": "Every B3 issuer is classified nightly using EODHD GICS/industry, cross-checked with Brapi and reviewed C3PO overrides. Relative valuation uses the narrowest peer group with at least four eligible companies, then canonical sector, then valuation profile.",
            "target_price": "Sector-adapted internal valuation blended with 20%-35% normalized public consensus. A second validation layer rejects the TP unless methods converge, Brapi and EODHD agree, fundamentals are fresh and the internal/public-consensus gap is within 40%.",
            "cvm_first": "Official CVM/SEC/RI disclosures enrich valuation inputs and remain visible in the audit trail. A pending disclosure never excludes a security from Candidates, Jedi Force or One Pager by itself.",
            "buy_in": "Winsorized risk- and confidence-adjusted weighted mean of Morgan Stanley 30%, JPMorgan 25%, Goldman Sachs 20%, Bridgewater 15% and BlackRock 10%, capped by both the entry-return hurdle and a 60-session market-structure entry.",
            "cadence": "Full screening and valuation basis recompute once daily at 00:00 America/Sao_Paulo; intraday requests reuse the PostgreSQL snapshot.",
            "learning": "Rolling 90-day calibration measures forecast bias and directional accuracy by valuation profile. Adjustments require minimum samples and are capped at +/-5%.",
            "score_weights": {
                "rule": "Power Score",
                "tp_upside": score_weights["tp_upside"],
                "inverse_risk": score_weights["inverse_risk"],
                "quality": score_weights["quality"],
                "confidence": score_weights["confidence"],
                "entry": score_weights["entry"],
            },
        }
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            parameters,
            f"{C3PO_VALUATION_POLICY.label}: {C3PO_VALUATION_POLICY.release_note}",
        )
        self.database.save_analysis_snapshot(
            "candidate_screen",
            "B3_TOP_10",
            methodology_id,
            {"source": response.source, "universe_size": response.universe_size, "criteria": response.criteria, "macro": macro},
            response.model_dump(mode="json"),
            response.generated_at,
        )
        self.database.save_analysis_snapshot(
            "valuation_universe",
            "B3_UNIVERSE",
            methodology_id,
            {
                "source": response.source,
                "methodology_version": response.methodology_version,
                "cvm_first": True,
            },
            self._json_safe({
                "rows": self._matrix_rows,
                "macro": macro,
                "universe_size": self._matrix_universe_size,
                "coverage_audit": self._matrix_coverage_audit,
                "sector_audit": self._matrix_sector_audit,
                "basis_at": response.generated_at,
            }),
            response.generated_at,
        )
        self._persist_calibration(methodology_id, response.generated_at, self._matrix_rows)

    def _persist_calibration(
        self,
        methodology_id: str,
        generated_at: datetime,
        current_rows: list[dict[str, Any]],
    ) -> None:
        prior = self.database.analysis_snapshot_at_or_before(
            "valuation_universe",
            "B3_UNIVERSE",
            generated_at - timedelta(days=CALIBRATION_HORIZON_DAYS),
        )
        factors = dict(self._calibration_factors)
        metrics: dict[str, dict[str, Any]] = {}
        status = "warming_up"
        horizon_days = None
        if prior:
            horizon_days = max(1, (generated_at - prior["published_at"]).days)
            prior_output = prior.get("outputs") or {}
            prior_rows = prior_output.get("rows") if isinstance(prior_output, dict) else []
            previous = {
                str(row.get("symbol")): row
                for row in prior_rows or []
                if isinstance(row, dict) and row.get("symbol")
            }
            grouped: dict[str, list[tuple[float, float]]] = {"global": []}
            for row in current_rows:
                symbol = str(row.get("symbol") or "")
                if symbol.endswith("F"):
                    continue
                old = previous.get(symbol)
                old_price = positive((old or {}).get("price"))
                current_price = positive(row.get("price"))
                expected_annual = number((old or {}).get("expected_total_return_percent"))
                if not old_price or not current_price or expected_annual is None:
                    continue
                expected_dividend = number((old or {}).get("expected_dividend")) or 0.0
                expected_annual -= expected_dividend / old_price * 100
                annual = clamp(expected_annual / 100, -0.90, 3.0)
                expected_period = (1 + annual) ** (horizon_days / 365) - 1
                realized = current_price / old_price - 1
                if abs(realized) > 0.75:
                    continue
                sample = (realized, expected_period)
                grouped["global"].append(sample)
                grouped.setdefault(str((old or {}).get("valuation_profile") or "general"), []).append(sample)

            global_factor = 1.0
            for profile, samples in grouped.items():
                required = CALIBRATION_MIN_GLOBAL_SAMPLES if profile == "global" else CALIBRATION_MIN_PROFILE_SAMPLES
                errors = [realized - expected for realized, expected in samples]
                absolute_errors = [abs(error) for error in errors]
                directional = [
                    (realized >= 0) == (expected >= 0)
                    for realized, expected in samples
                    if realized != 0 or expected != 0
                ]
                factor = 1.0
                if len(samples) >= required and 60 <= horizon_days <= 150:
                    factor = clamp(
                        1 + statistics.median(errors) * 0.25,
                        1 - CALIBRATION_FACTOR_LIMIT,
                        1 + CALIBRATION_FACTOR_LIMIT,
                    )
                    if profile == "global":
                        global_factor = factor
                    else:
                        factor = factor * 0.70 + global_factor * 0.30
                    factors[profile] = factor
                    status = "active"
                metrics[profile] = {
                    "samples": len(samples),
                    "median_forecast_error_percent": round(statistics.median(errors) * 100, 2) if errors else None,
                    "mean_absolute_error_percent": round(statistics.mean(absolute_errors) * 100, 2) if absolute_errors else None,
                    "directional_accuracy_percent": round(statistics.mean(directional) * 100, 2) if directional else None,
                    "factor": round(factor, 5),
                }

        self.database.save_analysis_snapshot(
            "valuation_calibration",
            "B3_POWER_MODEL",
            methodology_id,
            {
                "horizon_days": CALIBRATION_HORIZON_DAYS,
                "minimum_global_samples": CALIBRATION_MIN_GLOBAL_SAMPLES,
                "minimum_profile_samples": CALIBRATION_MIN_PROFILE_SAMPLES,
                "factor_limit": CALIBRATION_FACTOR_LIMIT,
            },
            {
                "status": status,
                "observed_horizon_days": horizon_days,
                "factors": factors,
                "metrics": metrics,
            },
            generated_at,
        )

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        return value
