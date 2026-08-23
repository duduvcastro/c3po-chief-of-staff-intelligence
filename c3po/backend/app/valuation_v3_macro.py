from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .config import Settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient


ENGINE_VERSION = 3
SCHEMA_VERSION = "VALUATION-V3-MACRO-v1"
SELIC_ANALYSIS_TYPE = "valuation_macro_history"
SELIC_ENTITY_KEY = "B3_SELIC_REGIME"
US_CURVE_ANALYSIS_TYPE = "valuation_macro_rates"
US_CURVE_ENTITY_KEY = "US_5Y_INTERPOLATED"
METHODOLOGY_KEY = "valuation_v3_macro_inputs"
METHODOLOGY_VERSION = 1

BCB_SELIC_SERIES_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
SELIC_SOURCE = "Banco Central do Brasil SGS 432"
US_CURVE_SOURCE = "EODHD Government Bonds"
US_CURVE_SYMBOLS = ((3, "US3Y.GBOND"), (10, "US10Y.GBOND"))


class ValuationV3MacroDataError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _annual_rate(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed / 100 if parsed > 1 else parsed


def _available_after_day(observation_date: date) -> str:
    # Both sources expose daily observations without an intraday publication
    # timestamp. Next-day UTC is a conservative availability convention: it
    # never lets a same-session close enter a valuation run early.
    return datetime.combine(
        observation_date + timedelta(days=1), time.min, tzinfo=timezone.utc
    ).isoformat()


def canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key != "payload_sha256"
    }


def canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        canonical_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def package_hash_is_valid(payload: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(payload, dict)
        and payload.get("payload_sha256")
        and payload["payload_sha256"] == canonical_payload_sha256(payload)
    )


def interpolate_us_five_year_rate(three_year: float, ten_year: float) -> float:
    if three_year <= 0 or ten_year <= 0:
        raise ValuationV3MacroDataError("Treasury yields must be positive")
    return three_year + (2 / 7) * (ten_year - three_year)


def validate_us_curve_package(payload: dict[str, Any], *, as_of: date) -> float:
    if not package_hash_is_valid(payload):
        raise ValuationV3MacroDataError("US curve package hash mismatch")
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("engine_version") != ENGINE_VERSION
        or payload.get("source") != US_CURVE_SOURCE
    ):
        raise ValuationV3MacroDataError("US curve package metadata mismatch")
    try:
        package_as_of = date.fromisoformat(str(payload.get("as_of") or ""))
    except ValueError as exc:
        raise ValuationV3MacroDataError("US curve package has invalid as_of") from exc
    if package_as_of != as_of:
        raise ValuationV3MacroDataError("US curve package as_of does not match the run")
    points = payload.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise ValuationV3MacroDataError("US curve requires exactly 3Y and 10Y")
    by_tenor: dict[int, dict[str, Any]] = {}
    for point in points:
        if not isinstance(point, dict):
            raise ValuationV3MacroDataError("US curve contains an invalid point")
        tenor_value = _number(point.get("tenor_years"))
        if tenor_value not in {3.0, 10.0} or int(tenor_value) in by_tenor:
            raise ValuationV3MacroDataError("US curve requires exactly 3Y and 10Y")
        by_tenor[int(tenor_value)] = point
    if set(by_tenor) != {3, 10}:
        raise ValuationV3MacroDataError("US curve requires exactly 3Y and 10Y")
    observation_dates: set[date] = set()
    rates: dict[int, float] = {}
    as_of_end = datetime.combine(as_of, time.max, tzinfo=timezone.utc)
    for tenor in (3, 10):
        point = by_tenor[tenor]
        try:
            observed = date.fromisoformat(str(point.get("observation_date") or ""))
            available = datetime.fromisoformat(str(point.get("available_at") or ""))
        except ValueError as exc:
            raise ValuationV3MacroDataError("US curve has invalid dates") from exc
        if available.tzinfo is None:
            available = available.replace(tzinfo=timezone.utc)
        if observed > as_of or available > as_of_end:
            raise ValuationV3MacroDataError("US curve contains a future observation")
        rate = _annual_rate(point.get("annual_rate"))
        if rate is None:
            raise ValuationV3MacroDataError("US curve contains an invalid yield")
        observation_dates.add(observed)
        rates[tenor] = rate
    if len(observation_dates) != 1:
        raise ValuationV3MacroDataError("US curve tenors have different observation dates")
    interpolated = interpolate_us_five_year_rate(rates[3], rates[10])
    persisted = _annual_rate(payload.get("interpolated_5y_rate"))
    if persisted is None or abs(persisted - interpolated) > 1e-12:
        raise ValuationV3MacroDataError("US curve interpolation does not reconcile")
    return interpolated


class ValuationV3MacroService:
    """Fetch and persist the two dated macro packages required by V3.

    This service is operator-driven until the frozen A/B is approved. It does
    not run in the valuation worker and no production consumer imports it.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http

    def refresh_selic(self, *, as_of: date | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(timezone.utc).date()
        start = as_of - timedelta(days=12 * 366)
        by_date: dict[date, dict[str, Any]] = {}
        # The SGS API limits long daily-series queries. Deterministic four-year
        # chunks cover the 10y history plus each fiscal window without changing
        # the resulting canonical package; inclusive boundaries are deduped by
        # observation date.
        chunk_start = start
        while chunk_start <= as_of:
            chunk_end = min(as_of, chunk_start + timedelta(days=4 * 365))
            raw = self.http.get_json(
                BCB_SELIC_SERIES_URL,
                params={
                    "formato": "json",
                    "dataInicial": chunk_start.strftime("%d/%m/%Y"),
                    "dataFinal": chunk_end.strftime("%d/%m/%Y"),
                },
            )
            if not isinstance(raw, list):
                raise ValuationV3MacroDataError("BCB SGS 432 returned an invalid payload")
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    observed = datetime.strptime(
                        str(item.get("data") or ""), "%d/%m/%Y"
                    ).date()
                except ValueError:
                    continue
                rate = _annual_rate(item.get("valor"))
                if observed < start or observed > as_of or rate is None:
                    continue
                by_date[observed] = {
                    "observation_date": observed.isoformat(),
                    "annual_rate": rate,
                    "available_at": _available_after_day(observed),
                }
            chunk_start = chunk_end + timedelta(days=1)
        if not by_date:
            raise ValuationV3MacroDataError("BCB SGS 432 returned no usable observations")

        fetched_at = datetime.now(timezone.utc)
        package: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "source": SELIC_SOURCE,
            "series": "SGS 432",
            "as_of": as_of.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "observations": [by_date[key] for key in sorted(by_date)],
        }
        package["payload_sha256"] = canonical_payload_sha256(package)
        self._persist(
            SELIC_ANALYSIS_TYPE,
            SELIC_ENTITY_KEY,
            package,
            inputs={"as_of": as_of.isoformat(), "source": SELIC_SOURCE},
            published_at=fetched_at,
        )
        return package

    def refresh_us_curve(self, *, as_of: date | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(timezone.utc).date()
        if not self.settings.eodhd_api_token:
            raise ValuationV3MacroDataError("EODHD credential is not configured")
        client = EodhdClient(
            self.settings.eodhd_base_url,
            self.settings.eodhd_api_token,
            self.http,
        )
        points: list[dict[str, Any]] = []
        for tenor, symbol in US_CURVE_SYMBOLS:
            candidates: list[tuple[date, float]] = []
            for item in client.history(symbol, exchange="GBOND", days=30):
                if not isinstance(item, dict):
                    continue
                try:
                    observed = date.fromisoformat(str(item.get("date") or ""))
                except ValueError:
                    continue
                rate = _annual_rate(item.get("close"))
                if observed <= as_of and rate is not None:
                    candidates.append((observed, rate))
            if not candidates:
                raise ValuationV3MacroDataError(f"No completed observation for {symbol}")
            observed, rate = max(candidates, key=lambda item: item[0])
            points.append({
                "symbol": symbol,
                "tenor_years": tenor,
                "observation_date": observed.isoformat(),
                "annual_rate": rate,
                "available_at": _available_after_day(observed),
                "source": US_CURVE_SOURCE,
            })

        dates = {point["observation_date"] for point in points}
        if len(dates) != 1:
            raise ValuationV3MacroDataError("US Treasury tenors have different dates")
        by_tenor = {int(point["tenor_years"]): float(point["annual_rate"]) for point in points}
        interpolated = interpolate_us_five_year_rate(by_tenor[3], by_tenor[10])
        fetched_at = datetime.now(timezone.utc)
        package: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "source": US_CURVE_SOURCE,
            "as_of": as_of.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "formula": "r3y + (2/7) * (r10y - r3y)",
            "points": sorted(points, key=lambda point: int(point["tenor_years"])),
            "interpolated_5y_rate": interpolated,
        }
        package["payload_sha256"] = canonical_payload_sha256(package)
        validate_us_curve_package(package, as_of=as_of)
        self._persist(
            US_CURVE_ANALYSIS_TYPE,
            US_CURVE_ENTITY_KEY,
            package,
            inputs={"as_of": as_of.isoformat(), "source": US_CURVE_SOURCE},
            published_at=fetched_at,
        )
        return package

    def refresh_all(self, *, as_of: date | None = None) -> dict[str, dict[str, Any]]:
        return {
            "B3_SELIC_REGIME": self.refresh_selic(as_of=as_of),
            "US_5Y_INTERPOLATED": self.refresh_us_curve(as_of=as_of),
        }

    def selic_package(self) -> dict[str, Any] | None:
        return self._read(SELIC_ANALYSIS_TYPE, SELIC_ENTITY_KEY)

    def us_curve_package(self) -> dict[str, Any] | None:
        return self._read(US_CURVE_ANALYSIS_TYPE, US_CURVE_ENTITY_KEY)

    def _persist(
        self,
        analysis_type: str,
        entity_key: str,
        package: dict[str, Any],
        *,
        inputs: dict[str, Any],
        published_at: datetime,
    ) -> None:
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "engine_version": ENGINE_VERSION,
                "hash": "sha256_canonical_json",
                "consumers": "valuation_v3_only_after_frozen_ab",
            },
            "Dated macro inputs for Valuation V3; no production consumer.",
        )
        self.database.save_analysis_snapshot(
            analysis_type,
            entity_key,
            methodology_id,
            {**inputs, "payload_sha256": package["payload_sha256"]},
            package,
            published_at,
        )

    def _read(self, analysis_type: str, entity_key: str) -> dict[str, Any] | None:
        snapshot = self.database.latest_analysis_snapshot(analysis_type, entity_key)
        outputs = snapshot.get("outputs") if snapshot else None
        if not isinstance(outputs, dict):
            return None
        if not package_hash_is_valid(outputs):
            raise ValuationV3MacroDataError(f"Stored macro package hash mismatch: {entity_key}")
        return outputs


def main() -> int:
    from .config import get_settings
    from .market_data.service import MarketDataService

    settings = get_settings()
    database = Database(settings)
    database.initialize()
    market_data = MarketDataService(settings, database)
    service = ValuationV3MacroService(settings, database, market_data.http)
    packages = service.refresh_all()
    print(json.dumps(
        {
            key: {
                "as_of": value["as_of"],
                "payload_sha256": value["payload_sha256"],
            }
            for key, value in packages.items()
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
