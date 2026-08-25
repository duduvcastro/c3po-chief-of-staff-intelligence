from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, time, timedelta, timezone
from itertools import combinations
from math import exp, floor, log
from statistics import median
from typing import Any

from .valuation_v2_engine import (
    EV_EBITDA_RANGE,
    MIN_HISTORY_YEARS,
    MIN_PEER_SAMPLE,
    PB_RANGE,
    PE_RANGE,
    ValuationV2Engine,
    _clamp,
    _number,
    _valid_multiple,
    _winsorized_median,
)
from .valuation_v3_macro import (
    package_hash_is_valid,
    validate_us_curve_package,
)


ENGINE_VERSION = 3
QUALITY_PROFILES = frozenset({"general", "growth", "quality"})
QUALITY_BASES = ("fmp_forward", "chewie_trailing")


class ValuationV3InputError(RuntimeError):
    pass


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _empirical_rank(value: float, peers: list[float]) -> float:
    return (
        sum(peer < value for peer in peers)
        + 0.5 * sum(peer == value for peer in peers)
    ) / len(peers)


class ValuationV3Engine(ValuationV2Engine):
    """Pure Valuation V3 engine, isolated from every production consumer.

    Feature switches exist only so the frozen A/B can attribute V3.1, V3.2 and
    V3.3 independently. A full US V3 engine defaults to fail-closed Treasury
    input; disabling that switch is an explicit decomposition mode.
    """

    def __init__(
        self,
        *,
        market: str,
        risk_free_rate: float | None = None,
        today: date | None = None,
        macro_as_of: date | None = None,
        us_curve_package: dict[str, Any] | None = None,
        selic_package: dict[str, Any] | None = None,
        enable_quality: bool = True,
        enable_selic: bool = True,
        enable_treasury: bool = True,
    ) -> None:
        if market not in {"B3", "US"}:
            raise ValueError(f"Unsupported V3 market: {market}")
        self.enable_quality = enable_quality
        self.enable_selic = enable_selic
        self.enable_treasury = enable_treasury
        self.as_of = today or datetime.now(timezone.utc).date()
        self.macro_as_of = macro_as_of or self.as_of
        self.us_curve_package = us_curve_package
        self.selic_package = selic_package

        if market == "US" and enable_treasury:
            if not isinstance(us_curve_package, dict):
                raise ValuationV3InputError("Full US V3 requires the dated Treasury package")
            try:
                risk_free_rate = validate_us_curve_package(
                    us_curve_package, as_of=self.macro_as_of
                )
            except Exception as exc:
                raise ValuationV3InputError(str(exc)) from exc
        if market == "B3" and selic_package is not None:
            if not package_hash_is_valid(selic_package):
                raise ValuationV3InputError("B3 Selic package hash mismatch")
            if (
                selic_package.get("schema_version") != "VALUATION-V3-MACRO-v1"
                or selic_package.get("engine_version") != ENGINE_VERSION
                or selic_package.get("source") != "Banco Central do Brasil SGS 432"
            ):
                raise ValuationV3InputError("B3 Selic package metadata mismatch")
            if selic_package.get("as_of") != self.macro_as_of.isoformat():
                raise ValuationV3InputError("B3 Selic package as_of does not match the run")

        super().__init__(
            market=market,  # type: ignore[arg-type]
            risk_free_rate=risk_free_rate,
            today=self.as_of,
        )
        if market == "US" and enable_treasury:
            self.risk_free_source = "eodhd_us5y_interpolated"

        self._selic_dates: list[date] = []
        self._selic_rates: list[float] = []
        self._selic_regime_cache: dict[date, float | None] = {}
        if market == "B3" and enable_selic and isinstance(selic_package, dict):
            self._load_selic_observations(selic_package)

    def evaluate(
        self,
        row: dict[str, Any],
        packet: dict[str, Any] | None,
        *,
        peer_multiples: dict[str, dict[str, Any]] | None = None,
        sector_fair_multiples: dict[str, float] | None = None,
        target_quality: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        price = _number(row.get("price"))
        if price is None or price <= 0:
            return None
        packet = packet or {}
        peers = peer_multiples or {}
        profile = str(row.get("valuation_profile") or "general")
        inputs = self._inputs(row, packet, price)
        ladder: list[str] = []
        fair_audits: dict[str, dict[str, Any]] = {}

        fair_pe, pe_source, pe_basis, fair_audits["pe"] = self._fair_multiple_v3(
            "pe", packet, peers, sector_fair_multiples, profile, target_quality or {}
        )
        fair_ev_ebitda, ev_source, _, fair_audits["ev_ebitda"] = self._fair_multiple_v3(
            "ev_ebitda", packet, peers, sector_fair_multiples, profile, target_quality or {}
        )
        fair_pb, pb_source, _, fair_audits["price_to_book"] = self._fair_multiple_v3(
            "price_to_book", packet, peers, sector_fair_multiples, profile, target_quality or {}
        )
        ladder.extend([
            f"pe:{pe_source}" if fair_pe else "pe:unavailable",
            f"ev_ebitda:{ev_source}" if fair_ev_ebitda else "ev_ebitda:unavailable",
            f"price_to_book:{pb_source}" if fair_pb else "price_to_book:unavailable",
        ])

        models: dict[str, dict[str, Any]] = {}
        if profile == "financial":
            self._add(models, "rim", self._rim_tp(inputs, price))
            self._add(models, "ddm", self._ddm_tp(inputs, price))
            self._add(models, "peer_comps", self._financial_peer_comps_tp(inputs, price, peers))
            self._add(
                models,
                "own_history",
                self._own_history_tp_v3(packet, inputs, price, profile=profile, financial=True),
            )
        else:
            self._add(
                models,
                "peer_comps",
                self._peer_comps_tp_v3(
                    inputs,
                    price,
                    peers,
                    profile=profile,
                    target_quality=target_quality or {},
                ),
            )
            self._add(
                models,
                "own_history",
                self._own_history_tp_v3(packet, inputs, price, profile=profile),
            )
            earnings_power = self._earnings_power_tp(
                inputs, price, fair_pe, pe_source, pe_basis, profile
            )
            earnings_power = self._attach_quality_audit(
                earnings_power, fair_audits["pe"], profile=profile
            )
            if pe_source == "own_history" and "own_history" in models:
                ladder.append("earnings_power:deduplicated_against_own_history")
            else:
                self._add(models, "earnings_power", earnings_power)
            self._add(models, "reverse_dcf", self._reverse_dcf_signal(inputs, price, profile))

        if not models:
            return {
                "symbol": str(row.get("symbol")),
                "engine_version": ENGINE_VERSION,
                "v3_tp": None,
                "low_conviction": True,
                "reason": "no_model_had_verifiable_anchors",
                "fair_multiple_ladder": ladder,
                "fair_multiple_audits": fair_audits,
                "risk_free_rate": self.risk_free_rate,
                "risk_free_source": self.risk_free_source,
                "macro_inputs": self._macro_inputs(),
            }
        return self._aggregate_v3(
            row, inputs, models, price, ladder, profile, fair_audits
        )

    # --------------------------------------------------------- V3.1 quality comps

    @staticmethod
    def _quality_record(
        record: dict[str, Any], basis: str
    ) -> tuple[float, float] | None:
        quality = record.get("quality")
        quality = quality if isinstance(quality, dict) else {}
        values = quality.get(basis)
        values = values if isinstance(values, dict) else {}
        roe = _number(values.get("roe"))
        growth = _number(values.get("revenue_growth"))
        return (roe, growth) if roe is not None and growth is not None else None

    def _quality_adjusted_multiple(
        self,
        *,
        metric: str,
        multiple_field: str,
        unadjusted: float,
        peers: dict[str, dict[str, Any]],
        target_quality: dict[str, dict[str, Any]],
    ) -> tuple[float, dict[str, Any]]:
        base_audit = {
            "quality_adjustment_status": "insufficient_quality_data",
            "quality_sample": 0,
            "quality_basis": None,
            "unadjusted_multiple": round(unadjusted, 6),
            "adjusted_multiple": round(unadjusted, 6),
            "quality_beta": None,
            "quality_beta_zeroed_negative": False,
        }
        if not self.enable_quality:
            return unadjusted, {**base_audit, "quality_adjustment_status": "disabled_for_ab"}

        selected: list[tuple[str, float, float, float]] = []
        target_pair: tuple[float, float] | None = None
        basis_used: str | None = None
        for basis in QUALITY_BASES:
            target_pair = self._quality_record({"quality": target_quality}, basis)
            if target_pair is None:
                continue
            candidate: list[tuple[str, float, float, float]] = []
            for symbol, peer in sorted(peers.items()):
                multiple = _valid_multiple(
                    peer.get(multiple_field),
                    {"pe": PE_RANGE, "ev_ebitda": EV_EBITDA_RANGE, "price_to_book": PB_RANGE}[metric],
                )
                quality_pair = self._quality_record(peer, basis)
                if multiple is not None and quality_pair is not None:
                    candidate.append((symbol, multiple, quality_pair[0], quality_pair[1]))
            if len(candidate) >= MIN_PEER_SAMPLE:
                selected = candidate
                basis_used = basis
                break
        if not selected or target_pair is None or basis_used is None:
            return unadjusted, base_audit

        multiples = [item[1] for item in selected]
        roes = [item[2] for item in selected]
        growths = [item[3] for item in selected]
        qualities = [
            (_empirical_rank(roe, roes) + _empirical_rank(growth, growths)) / 2
            for _, _, roe, growth in selected
        ]
        target_roe_rank = _empirical_rank(target_pair[0], roes)
        target_growth_rank = _empirical_rank(target_pair[1], growths)
        target_rank = (target_roe_rank + target_growth_rank) / 2
        slopes = [
            (log(multiples[b]) - log(multiples[a])) / (qualities[b] - qualities[a])
            for a, b in combinations(range(len(selected)), 2)
            if qualities[a] != qualities[b]
        ]
        raw_beta = median(slopes) if slopes else 0.0
        beta = max(0.0, raw_beta)
        q0 = median(qualities)
        m0 = _winsorized_median(multiples)
        if m0 is None:
            return unadjusted, base_audit
        q25, q75 = _percentile(multiples, 0.25), _percentile(multiples, 0.75)
        raw = m0 * exp(beta * (target_rank - q0))
        adjusted = _clamp(raw, q25, q75)
        reliability_cap = _clamp(len(selected) / 8, 0.25, 1.0)
        quartile = min(4, floor(4 * target_rank) + 1)
        return adjusted, {
            "quality_adjustment_status": "applied",
            "quality_sample": len(selected),
            "quality_basis": basis_used,
            "target_roe_rank": round(target_roe_rank, 6),
            "target_growth_rank": round(target_growth_rank, 6),
            "target_quality_rank": round(target_rank, 6),
            "target_quality_quartile": quartile,
            "quality_beta": round(beta, 9),
            "quality_beta_zeroed_negative": raw_beta < 0,
            "quality_neutral_rank": round(q0, 6),
            "unadjusted_multiple": round(unadjusted, 6),
            "quality_sample_median": round(m0, 6),
            "raw_adjusted_multiple": round(raw, 6),
            "adjusted_multiple": round(adjusted, 6),
            "iqr_low": round(q25, 6),
            "iqr_high": round(q75, 6),
            "reliability_cap": round(reliability_cap, 6),
        }

    def _fair_multiple_v3(
        self,
        metric: str,
        packet: dict[str, Any],
        peers: dict[str, dict[str, Any]],
        sector_fair_multiples: dict[str, float] | None,
        profile: str,
        target_quality: dict[str, dict[str, Any]],
    ) -> tuple[float | None, str | None, str | None, dict[str, Any]]:
        fair, source, basis = super()._fair_multiple(
            metric, packet, peers, sector_fair_multiples
        )
        audit: dict[str, Any] = {
            "quality_adjustment_status": "not_peer_anchor",
            "quality_sample": 0,
            "quality_basis": None,
        }
        if fair is None:
            return fair, source, basis, audit
        if (
            profile in QUALITY_PROFILES
            and source in {"peers", "peers_forward", "peers_trailing"}
        ):
            field = (
                "forward_pe" if metric == "pe" and basis == "forward"
                else "pe" if metric == "pe" else metric
            )
            fair, audit = self._quality_adjusted_multiple(
                metric=metric,
                multiple_field=field,
                unadjusted=fair,
                peers=peers,
                target_quality=target_quality,
            )
        elif profile not in QUALITY_PROFILES:
            audit["quality_adjustment_status"] = "profile_not_eligible"

        if metric == "pe" and source == "own_history" and self.market == "B3":
            fair, regime = self._condition_history_metric(packet, metric)
            audit["regime_adjustment"] = regime
        return fair, source, basis, audit

    def _peer_comps_tp_v3(
        self,
        inputs: dict[str, Any],
        price: float,
        peers: dict[str, dict[str, Any]],
        *,
        profile: str,
        target_quality: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        baseline = super()._peer_comps_tp(inputs, price, peers)
        if baseline is None or profile not in QUALITY_PROFILES or not self.enable_quality:
            return baseline

        values: list[float] = []
        audits: dict[str, dict[str, Any]] = {}
        reliability_caps: list[float] = []
        ev_values = [
            value for peer in peers.values()
            if (value := _valid_multiple(peer.get("ev_ebitda"), EV_EBITDA_RANGE)) is not None
        ]
        if (
            len(ev_values) >= MIN_PEER_SAMPLE
            and inputs["ntm_ebitda"] and inputs["shares"]
            and inputs["net_debt"] is not None
        ):
            unadjusted = _winsorized_median(ev_values)
            if unadjusted is not None:
                adjusted, audit = self._quality_adjusted_multiple(
                    metric="ev_ebitda",
                    multiple_field="ev_ebitda",
                    unadjusted=unadjusted,
                    peers=peers,
                    target_quality=target_quality,
                )
                equity = adjusted * inputs["ntm_ebitda"] - inputs["net_debt"]
                if (tp := self._bounded(equity / inputs["shares"], price)) is not None:
                    values.append(tp)
                    audits["ev_ebitda"] = audit
                    if audit.get("quality_adjustment_status") == "applied":
                        reliability_caps.append(float(audit["reliability_cap"]))

        pb_values = [
            value for peer in peers.values()
            if (value := _valid_multiple(peer.get("price_to_book"), PB_RANGE)) is not None
        ]
        if len(pb_values) >= MIN_PEER_SAMPLE and inputs["book_value"]:
            unadjusted = _winsorized_median(pb_values)
            if unadjusted is not None:
                adjusted, audit = self._quality_adjusted_multiple(
                    metric="price_to_book",
                    multiple_field="price_to_book",
                    unadjusted=unadjusted,
                    peers=peers,
                    target_quality=target_quality,
                )
                if (tp := self._bounded(adjusted * inputs["book_value"], price)) is not None:
                    values.append(tp)
                    audits["price_to_book"] = audit
                    if audit.get("quality_adjustment_status") == "applied":
                        reliability_caps.append(float(audit["reliability_cap"]))
        if not values:
            return baseline

        reliability = float(baseline["reliability"])
        if reliability_caps:
            reliability = min(reliability, *reliability_caps)
        return {
            **baseline,
            "tp": median(values),
            "reliability": round(reliability, 3),
            "metrics_used": list(audits),
            "quality_adjustments": audits,
        }

    @staticmethod
    def _attach_quality_audit(
        model: dict[str, Any] | None,
        audit: dict[str, Any],
        *,
        profile: str,
    ) -> dict[str, Any] | None:
        if (
            model is None
            or profile not in QUALITY_PROFILES
            or audit.get("quality_adjustment_status") == "disabled_for_ab"
        ):
            return model
        reliability = float(model["reliability"])
        if audit.get("quality_adjustment_status") == "applied":
            reliability = min(reliability, float(audit["reliability_cap"]))
        return {**model, "reliability": round(reliability, 3), "quality_adjustment": audit}

    # ---------------------------------------------------------- V3.2 Selic regime

    def _load_selic_observations(self, package: dict[str, Any]) -> None:
        as_of_end = datetime.combine(self.as_of, time.max, tzinfo=timezone.utc)
        by_date: dict[date, float] = {}
        for item in package.get("observations") or []:
            if not isinstance(item, dict):
                continue
            try:
                observed = date.fromisoformat(str(item.get("observation_date") or ""))
                available = datetime.fromisoformat(str(item.get("available_at") or ""))
            except ValueError:
                continue
            if available.tzinfo is None:
                available = available.replace(tzinfo=timezone.utc)
            rate = _number(item.get("annual_rate"))
            if observed <= self.as_of and available <= as_of_end and rate is not None and rate > 0:
                by_date[observed] = rate
        self._selic_dates = sorted(by_date)
        self._selic_rates = [by_date[observed] for observed in self._selic_dates]

    def _selic_regime(self, window_end: date) -> float | None:
        if window_end > self.as_of:
            return None
        if window_end in self._selic_regime_cache:
            return self._selic_regime_cache[window_end]
        window_start = window_end - timedelta(days=365)
        daily: list[float] = []
        current = window_start
        while current <= window_end:
            index = bisect_right(self._selic_dates, current) - 1
            if index >= 0:
                daily.append(self._selic_rates[index])
            current += timedelta(days=1)
        value = median(daily) if daily else None
        self._selic_regime_cache[window_end] = value
        return value

    def _condition_history_metric(
        self, packet: dict[str, Any], metric: str
    ) -> tuple[float | None, dict[str, Any]]:
        bounds = {"pe": PE_RANGE, "ev_ebitda": EV_EBITDA_RANGE, "price_to_book": PB_RANGE}[metric]
        rows: list[tuple[date, float]] = []
        for item in packet.get("ratios_annual") or []:
            if not isinstance(item, dict):
                continue
            try:
                fiscal_end = date.fromisoformat(str(item.get("fiscal_year_end") or ""))
            except ValueError:
                continue
            value = _valid_multiple(item.get(metric), bounds)
            if value is not None and fiscal_end <= self.as_of:
                rows.append((fiscal_end, value))
        unconditioned = _winsorized_median([value for _, value in rows])
        base = {
            "regime_status": "not_applicable",
            "metric": metric,
            "current_selic_regime": None,
            "selected": [],
            "discarded_years": [],
            "unconditioned_multiple": unconditioned,
            "conditioned_multiple": unconditioned,
            "source": None,
            "as_of": self.as_of.isoformat(),
            "macro_hash": None,
        }
        if self.market != "B3" or not self.enable_selic:
            return unconditioned, base
        package = self.selic_package or {}
        package_hash = package.get("payload_sha256")
        source = package.get("source")
        if not self._selic_dates:
            return unconditioned, {
                **base,
                "regime_status": "insufficient_selic_history",
                "source": source,
                "macro_hash": package_hash,
            }
        current_regime = self._selic_regime(self.as_of)
        mapped: list[dict[str, Any]] = []
        if current_regime is not None:
            for fiscal_end, value in rows:
                historical_regime = self._selic_regime(fiscal_end)
                if historical_regime is not None:
                    mapped.append({
                        "fiscal_year_end": fiscal_end.isoformat(),
                        "multiple": value,
                        "selic_regime": historical_regime,
                        "distance": abs(historical_regime - current_regime),
                    })
        mapped.sort(
            key=lambda item: (
                float(item["distance"]),
                -date.fromisoformat(str(item["fiscal_year_end"])).toordinal(),
            )
        )
        if len(mapped) < MIN_HISTORY_YEARS:
            return unconditioned, {
                **base,
                "regime_status": "insufficient_selic_history",
                "current_selic_regime": current_regime,
                "source": source,
                "macro_hash": package_hash,
                "discarded_years": [],
            }
        selected = mapped[:MIN_HISTORY_YEARS]
        conditioned = _winsorized_median([float(item["multiple"]) for item in selected])
        selected_dates = {str(item["fiscal_year_end"]) for item in selected}
        discarded = [
            str(item["fiscal_year_end"])
            for item in mapped
            if str(item["fiscal_year_end"]) not in selected_dates
        ]
        return conditioned, {
            **base,
            "regime_status": "applied",
            "current_selic_regime": current_regime,
            "selected": selected,
            "discarded_years": discarded,
            "conditioned_multiple": conditioned,
            "source": source,
            "macro_hash": package_hash,
        }

    def _own_history_tp_v3(
        self,
        packet: dict[str, Any],
        inputs: dict[str, Any],
        price: float,
        *,
        profile: str,
        financial: bool = False,
    ) -> dict[str, Any] | None:
        if self.market != "B3" or not self.enable_selic:
            return super()._own_history_tp(
                packet, inputs, price, profile=profile, financial=financial
            )
        ratios: list[dict[str, Any]] = []
        for item in packet.get("ratios_annual") or []:
            if not isinstance(item, dict):
                continue
            try:
                fiscal_end = date.fromisoformat(str(item.get("fiscal_year_end") or ""))
            except ValueError:
                continue
            if fiscal_end <= self.as_of:
                ratios.append(item)
        values: list[float] = []
        used: list[str] = []
        pe_history = [
            value for item in ratios
            if (value := _valid_multiple(item.get("pe"), PE_RANGE)) is not None
        ]
        pb_history = [
            value for item in ratios
            if (value := _valid_multiple(item.get("price_to_book"), PB_RANGE)) is not None
        ]
        regime_metrics: dict[str, dict[str, Any]] = {}
        fair_pe, regime_metrics["pe"] = self._condition_history_metric(packet, "pe")
        _fair_ev, regime_metrics["ev_ebitda"] = self._condition_history_metric(
            packet, "ev_ebitda"
        )
        fair_pb, regime_metrics["price_to_book"] = self._condition_history_metric(
            packet, "price_to_book"
        )
        earnings_base = inputs["mid_cycle_eps"] if profile == "cyclical" else inputs["trailing_eps"]
        if (
            not financial and len(pe_history) >= MIN_HISTORY_YEARS
            and earnings_base and earnings_base > 0 and fair_pe is not None
        ):
            if (tp := self._bounded(fair_pe * earnings_base, price)) is not None:
                values.append(tp)
                used.append("pe")
        if len(pb_history) >= MIN_HISTORY_YEARS and inputs["book_value"] and fair_pb is not None:
            if (tp := self._bounded(fair_pb * inputs["book_value"], price)) is not None:
                values.append(tp)
                used.append("price_to_book")
        if not values:
            return None
        years = max(len(pe_history), len(pb_history))
        current_pe = price / earnings_base if earnings_base and earnings_base > 0 else None
        current_percentile = None
        if current_pe is not None and pe_history:
            current_percentile = round(
                sum(value <= current_pe for value in pe_history) / len(pe_history), 2
            )
        return {
            "tp": median(values),
            "reliability": round(_clamp(years / 10, 0.3, 1.0), 3),
            "metrics_used": used,
            "earnings_base": (
                "mid_cycle_median" if profile == "cyclical" and "pe" in used
                else "trailing" if "pe" in used else None
            ),
            "history_years": years,
            "current_pe_percentile_in_history": current_percentile,
            "regime_status": (
                "applied"
                if any(item.get("regime_status") == "applied" for item in regime_metrics.values())
                else "insufficient_selic_history"
            ),
            "regime_metrics": regime_metrics,
        }

    # -------------------------------------------------------- aggregation/audit

    def _aggregate_v3(
        self,
        row: dict[str, Any],
        inputs: dict[str, Any],
        models: dict[str, dict[str, Any]],
        price: float,
        ladder: list[str],
        profile: str,
        fair_audits: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        result = super()._aggregate(row, inputs, models, price, ladder, profile)
        result["engine_version"] = ENGINE_VERSION
        result["v3_tp"] = result.pop("v2_tp")
        result["v3_internal_tp"] = result.pop("v2_internal_tp")
        result["v3_upside_percent"] = result.pop("v2_upside_percent")
        result["fair_multiple_audits"] = fair_audits
        result["macro_inputs"] = self._macro_inputs()
        return result

    def _macro_inputs(self) -> dict[str, Any]:
        return {
            "b3_selic_regime_hash": (
                self.selic_package.get("payload_sha256")
                if isinstance(self.selic_package, dict) else None
            ),
            "us_curve_hash": (
                self.us_curve_package.get("payload_sha256")
                if isinstance(self.us_curve_package, dict) else None
            ),
            "us_curve_source": self.risk_free_source if self.market == "US" else None,
        }
