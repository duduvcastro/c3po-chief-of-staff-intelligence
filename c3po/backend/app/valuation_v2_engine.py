from __future__ import annotations

from datetime import date, datetime, timezone
from statistics import median
from typing import Any, Literal


V2EngineMarket = Literal["B3", "US"]

ENGINE_VERSION = 1

# ---------------------------------------------------------------------------
# Frozen V2 principles (Fable, 2026-08-23):
#   P1  every anchor is external and verifiable (real peers, FY consensus
#       estimates, the company's own history, market consensus TP);
#   P2  no free constants -- a fair multiple comes from peers, sector medians
#       or own history, or the model declares itself unable (low_conviction);
#   P3  the DCF is anchored to CONSENSUS growth (and reports the growth the
#       price implies), never to a house growth premise;
#   P4  divergence vs consensus is a measured output with frozen bands
#       (>30% -> low_conviction + max shrink; 15-30% -> flagged note);
#   cyclicals value mid-cycle earnings -- peak TTM/NTM is never the sole base.
#
# The only economic conventions retained (documented, not "fair value"
# guesses): CAPM equity risk premium, discount-rate clamps, terminal growth
# ceilings and multiple sanity ranges, shared with the existing engine.
# ---------------------------------------------------------------------------

EQUITY_RISK_PREMIUM = 0.055
US_RISK_FREE_FALLBACK = 0.042
BR_RISK_FREE_FALLBACK = 0.115  # explicit fallback when the Tesouro curve is unavailable
US_DISCOUNT_MIN, US_DISCOUNT_MAX = 0.06, 0.16
BR_DISCOUNT_MIN, BR_DISCOUNT_MAX = 0.10, 0.22
US_TERMINAL_GROWTH = 0.03
BR_TERMINAL_GROWTH = 0.055

PE_RANGE = (1.5, 80.0)
EV_EBITDA_RANGE = (1.0, 50.0)
PB_RANGE = (0.10, 30.0)

MIN_PEER_SAMPLE = 4
MIN_HISTORY_YEARS = 5
PEER_DISPERSION_CAP = 0.80  # IQR/median above this halves the comps reliability
LOW_CONVICTION_DISPERSION_RATIO = 1.75
TP_BOUND_VS_PRICE = (0.35, 3.0)  # any single model TP clamped to [35%, 300%] of price

# P4 bands, frozen 2026-08-23.
DIVERGENCE_NOTE_BAND = 0.15
DIVERGENCE_LOW_CONVICTION_BAND = 0.30
MAX_CONSENSUS_SHRINK = 0.50

MODEL_LABELS = {
    "peer_comps": "Comps de peers reais",
    "own_history": "Banda histórica própria",
    "earnings_power": "Earnings power (FY1/FY2)",
    "consensus_dcf": "DCF ancorado no consenso",
    "rim": "Residual Income (RIM)",
    "ddm": "Dividendos descontados (DDM)",
}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _valid_multiple(value: Any, bounds: tuple[float, float]) -> float | None:
    parsed = _number(value)
    if parsed is None or not bounds[0] <= parsed <= bounds[1]:
        return None
    return parsed


def _winsorized_median(values: list[float]) -> float | None:
    clean = sorted(values)
    if not clean:
        return None
    if len(clean) >= 5:
        trim = max(1, len(clean) // 10)
        clean = clean[trim:-trim] or clean
    return median(clean)


def _dispersion(values: list[float]) -> float | None:
    clean = sorted(values)
    if len(clean) < 4:
        return None
    mid = median(clean)
    if mid <= 0:
        return None
    lower = clean[len(clean) // 4]
    upper = clean[(3 * len(clean)) // 4]
    return (upper - lower) / mid


class ValuationV2Engine:
    """The V2 target-price engine. Pure computation over persisted inputs:
    a screener universe row, a V2.1 data packet, resolved peer multiples and
    optional sector fair multiples. No network access, no side effects --
    the shadow service owns data resolution and persistence."""

    def __init__(
        self,
        *,
        market: V2EngineMarket,
        risk_free_rate: float | None = None,
        today: date | None = None,
    ) -> None:
        self.market = market
        fallback = US_RISK_FREE_FALLBACK if market == "US" else BR_RISK_FREE_FALLBACK
        self.risk_free_rate = risk_free_rate if risk_free_rate is not None else fallback
        self.risk_free_source = "provided" if risk_free_rate is not None else "fallback_constant"
        self.terminal_growth = US_TERMINAL_GROWTH if market == "US" else BR_TERMINAL_GROWTH
        self.discount_bounds = (
            (US_DISCOUNT_MIN, US_DISCOUNT_MAX) if market == "US" else (BR_DISCOUNT_MIN, BR_DISCOUNT_MAX)
        )
        self.today = today or datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------ public

    def evaluate(
        self,
        row: dict[str, Any],
        packet: dict[str, Any] | None,
        *,
        peer_multiples: dict[str, dict[str, Any]] | None = None,
        sector_fair_multiples: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        price = _number(row.get("price"))
        if price is None or price <= 0:
            return None
        packet = packet or {}
        profile = str(row.get("valuation_profile") or "general")
        inputs = self._inputs(row, packet, price)
        ladder: list[str] = []

        fair_pe, pe_source = self._fair_multiple(
            "pe", packet, peer_multiples, sector_fair_multiples, inputs
        )
        fair_ev_ebitda, ev_source = self._fair_multiple(
            "ev_ebitda", packet, peer_multiples, sector_fair_multiples, inputs
        )
        fair_pb, pb_source = self._fair_multiple(
            "price_to_book", packet, peer_multiples, sector_fair_multiples, inputs
        )
        ladder.extend(filter(None, [
            f"pe:{pe_source}" if fair_pe else "pe:unavailable",
            f"ev_ebitda:{ev_source}" if fair_ev_ebitda else "ev_ebitda:unavailable",
            f"price_to_book:{pb_source}" if fair_pb else "price_to_book:unavailable",
        ]))

        models: dict[str, dict[str, Any]] = {}
        if profile == "financial":
            self._add(models, "rim", self._rim_tp(inputs, price))
            self._add(models, "ddm", self._ddm_tp(inputs, price))
            self._add(models, "peer_comps", self._financial_peer_comps_tp(
                inputs, price, peer_multiples or {}
            ))
            self._add(models, "own_history", self._own_history_tp(
                packet, inputs, price, financial=True
            ))
        else:
            self._add(models, "peer_comps", self._peer_comps_tp(
                inputs, price, peer_multiples or {}
            ))
            self._add(models, "own_history", self._own_history_tp(packet, inputs, price))
            self._add(models, "earnings_power", self._earnings_power_tp(
                inputs, price, fair_pe, pe_source, profile
            ))
            self._add(models, "consensus_dcf", self._consensus_dcf_tp(inputs, price, profile))

        if not models:
            return {
                "symbol": str(row.get("symbol")),
                "engine_version": ENGINE_VERSION,
                "v2_tp": None,
                "low_conviction": True,
                "reason": "no_model_had_verifiable_anchors",
                "fair_multiple_ladder": ladder,
                "risk_free_rate": self.risk_free_rate,
                "risk_free_source": self.risk_free_source,
            }

        return self._aggregate(row, inputs, models, price, ladder, profile)

    # ------------------------------------------------------------------ inputs

    def _inputs(self, row: dict[str, Any], packet: dict[str, Any], price: float) -> dict[str, Any]:
        market_cap = _number(row.get("market_cap"))
        shares = _number(row.get("shares")) or (
            market_cap / price if market_cap and price else None
        )
        key_metrics = [
            item for item in packet.get("key_metrics_annual") or [] if isinstance(item, dict)
        ]
        ratios = [item for item in packet.get("ratios_annual") or [] if isinstance(item, dict)]
        latest_km = key_metrics[0] if key_metrics else {}
        net_debt = None
        km_ev, km_mc = _number(latest_km.get("enterprise_value")), _number(latest_km.get("market_cap"))
        if km_ev is not None and km_mc is not None:
            net_debt = km_ev - km_mc
        debt, cash = _number(row.get("debt")), _number(row.get("cash"))
        if net_debt is None and debt is not None and cash is not None:
            net_debt = debt - cash

        estimates = sorted(
            (
                item for item in packet.get("analyst_estimates_annual") or []
                if isinstance(item, dict)
                and str(item.get("fiscal_year_end") or "") >= self.today.isoformat()
            ),
            key=lambda item: str(item.get("fiscal_year_end")),
        )
        ntm_eps, consensus_growth, analysts_eps = self._ntm_eps(estimates)
        ntm_ebitda = _number(estimates[0].get("ebitda_avg")) if estimates else None

        trailing_eps = _number(row.get("eps")) or (
            price / pe if (pe := _valid_multiple(row.get("pe"), PE_RANGE)) else None
        )
        historical_eps = [
            value for item in key_metrics
            if (value := _number(item.get("eps"))) is not None and value > 0
        ]
        latest_ratios = ratios[0] if ratios else {}
        roe = _number(row.get("roe"))
        if roe is None:
            roe_percent = _number(row.get("roe_percent"))
            roe = roe_percent / 100 if roe_percent is not None else _number(latest_ratios.get("roe"))
        book_value = _number(row.get("book_value")) or (
            price / pb if (pb := _valid_multiple(row.get("price_to_book"), PB_RANGE)) else None
        )
        dividend_yield = _number(row.get("dividend_yield")) or _number(latest_ratios.get("dividend_yield"))
        beta = _number(row.get("beta"))
        cost_of_equity = _clamp(
            self.risk_free_rate + (beta if beta is not None else 1.0) * EQUITY_RISK_PREMIUM,
            *self.discount_bounds,
        )
        return {
            "market_cap": market_cap,
            "shares": shares,
            "net_debt": net_debt,
            "ntm_eps": ntm_eps,
            "ntm_ebitda": ntm_ebitda,
            "consensus_growth": consensus_growth,
            "analysts_eps": analysts_eps,
            "trailing_eps": trailing_eps,
            "mid_cycle_eps": _winsorized_median(historical_eps[:7]) if len(historical_eps) >= 4 else None,
            "roe": roe,
            "book_value": book_value,
            "dividend_per_share": dividend_yield * price if dividend_yield else None,
            "beta": beta,
            "cost_of_equity": cost_of_equity,
            "history_years": len(ratios),
            "estimates": estimates,
        }

    def _ntm_eps(self, estimates: list[dict[str, Any]]) -> tuple[float | None, float | None, int]:
        if not estimates:
            return None, None, 0
        fy1 = estimates[0]
        fy1_eps = _number(fy1.get("eps_avg"))
        analysts = int(_number(fy1.get("analysts_eps")) or 0)
        try:
            fy1_end = date.fromisoformat(str(fy1.get("fiscal_year_end")))
            fy1_fraction = _clamp((fy1_end - self.today).days / 365.0, 0.0, 1.0)
        except ValueError:
            fy1_fraction = 1.0
        fy2_eps = _number(estimates[1].get("eps_avg")) if len(estimates) > 1 else None
        if fy1_eps is None:
            return None, None, analysts
        ntm = (
            fy1_eps * fy1_fraction + fy2_eps * (1 - fy1_fraction)
            if fy2_eps is not None else fy1_eps
        )
        growth = (
            _clamp(fy2_eps / fy1_eps - 1, -0.20, 0.35)
            if fy2_eps is not None and fy1_eps > 0 else None
        )
        return ntm, growth, analysts

    # ------------------------------------------------------------- fair multiples

    def _fair_multiple(
        self,
        metric: str,
        packet: dict[str, Any],
        peer_multiples: dict[str, dict[str, Any]] | None,
        sector_fair_multiples: dict[str, float] | None,
        inputs: dict[str, Any],
    ) -> tuple[float | None, str | None]:
        """The frozen ladder: real peers -> sector medians -> own history.
        No constant fallback exists by design (P2)."""
        bounds = {"pe": PE_RANGE, "ev_ebitda": EV_EBITDA_RANGE, "price_to_book": PB_RANGE}[metric]
        peer_values: list[float] = []
        for peer in (peer_multiples or {}).values():
            raw = peer.get("forward_pe") or peer.get("pe") if metric == "pe" else peer.get(metric)
            value = _valid_multiple(raw, bounds)
            if value is not None:
                peer_values.append(value)
        if len(peer_values) >= MIN_PEER_SAMPLE:
            fair = _winsorized_median(peer_values)
            if fair is not None:
                return fair, "peers"
        sector_value = _valid_multiple((sector_fair_multiples or {}).get(metric), bounds)
        if sector_value is not None:
            return sector_value, "sector_median"
        history = [
            value for item in packet.get("ratios_annual") or []
            if isinstance(item, dict)
            and (value := _valid_multiple(item.get(metric), bounds)) is not None
        ]
        if len(history) >= MIN_HISTORY_YEARS:
            fair = _winsorized_median(history)
            if fair is not None:
                return fair, "own_history"
        return None, None

    # ------------------------------------------------------------------ models

    @staticmethod
    def _add(models: dict[str, dict[str, Any]], name: str, result: dict[str, Any] | None) -> None:
        if result is not None:
            models[name] = result

    def _bounded(self, value: float | None, price: float) -> float | None:
        if value is None or value <= 0:
            return None
        return _clamp(value, price * TP_BOUND_VS_PRICE[0], price * TP_BOUND_VS_PRICE[1])

    def _peer_comps_tp(
        self, inputs: dict[str, Any], price: float, peer_multiples: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        values: list[float] = []
        used: list[str] = []
        pe_values = [
            v for peer in peer_multiples.values()
            if (v := _valid_multiple(peer.get("forward_pe") or peer.get("pe"), PE_RANGE)) is not None
        ]
        earnings_base = inputs["ntm_eps"] or inputs["trailing_eps"]
        if len(pe_values) >= MIN_PEER_SAMPLE and earnings_base and earnings_base > 0:
            fair = _winsorized_median(pe_values)
            if fair and (tp := self._bounded(fair * earnings_base, price)):
                values.append(tp)
                used.append("pe")
        ev_values = [
            v for peer in peer_multiples.values()
            if (v := _valid_multiple(peer.get("ev_ebitda"), EV_EBITDA_RANGE)) is not None
        ]
        if (
            len(ev_values) >= MIN_PEER_SAMPLE
            and inputs["ntm_ebitda"] and inputs["shares"]
            and inputs["net_debt"] is not None
        ):
            fair = _winsorized_median(ev_values)
            if fair:
                equity = fair * inputs["ntm_ebitda"] - inputs["net_debt"]
                if (tp := self._bounded(equity / inputs["shares"], price)):
                    values.append(tp)
                    used.append("ev_ebitda")
        pb_values = [
            v for peer in peer_multiples.values()
            if (v := _valid_multiple(peer.get("price_to_book"), PB_RANGE)) is not None
        ]
        if len(pb_values) >= MIN_PEER_SAMPLE and inputs["book_value"]:
            fair = _winsorized_median(pb_values)
            if fair and (tp := self._bounded(fair * inputs["book_value"], price)):
                values.append(tp)
                used.append("price_to_book")
        if not values:
            return None
        sample = max(len(pe_values), len(ev_values), len(pb_values))
        dispersion = _dispersion(pe_values or ev_values or pb_values)
        reliability = _clamp(sample / 8, 0.25, 1.0) * (
            0.5 if dispersion is not None and dispersion > PEER_DISPERSION_CAP else 1.0
        )
        return {
            "tp": median(values),
            "reliability": round(reliability, 3),
            "metrics_used": used,
            "peer_sample": sample,
            "peer_dispersion": round(dispersion, 3) if dispersion is not None else None,
        }

    def _financial_peer_comps_tp(
        self, inputs: dict[str, Any], price: float, peer_multiples: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Financials: P/B anchored to peers, adjusted by relative ROE --
        never EV/EBITDA (meaningless for banks)."""
        pb_values = [
            v for peer in peer_multiples.values()
            if (v := _valid_multiple(peer.get("price_to_book"), PB_RANGE)) is not None
        ]
        roe_values = [
            v for peer in peer_multiples.values()
            if (v := _number(peer.get("roe"))) is not None and 0 < v < 1.5
        ]
        if len(pb_values) < MIN_PEER_SAMPLE or not inputs["book_value"]:
            return None
        fair_pb = _winsorized_median(pb_values)
        if fair_pb is None:
            return None
        if inputs["roe"] and roe_values:
            peer_roe = _winsorized_median(roe_values)
            if peer_roe and peer_roe > 0:
                fair_pb *= _clamp(inputs["roe"] / peer_roe, 0.5, 2.0)
        tp = self._bounded(fair_pb * inputs["book_value"], price)
        if tp is None:
            return None
        dispersion = _dispersion(pb_values)
        reliability = _clamp(len(pb_values) / 8, 0.25, 1.0) * (
            0.5 if dispersion is not None and dispersion > PEER_DISPERSION_CAP else 1.0
        )
        return {
            "tp": tp,
            "reliability": round(reliability, 3),
            "metrics_used": ["price_to_book_vs_roe"],
            "peer_sample": len(pb_values),
            "peer_dispersion": round(dispersion, 3) if dispersion is not None else None,
        }

    def _own_history_tp(
        self, packet: dict[str, Any], inputs: dict[str, Any], price: float, *, financial: bool = False,
    ) -> dict[str, Any] | None:
        ratios = [item for item in packet.get("ratios_annual") or [] if isinstance(item, dict)]
        values: list[float] = []
        used: list[str] = []
        pe_history = [v for item in ratios if (v := _valid_multiple(item.get("pe"), PE_RANGE))]
        earnings_base = inputs["ntm_eps"] or inputs["trailing_eps"]
        if not financial and len(pe_history) >= MIN_HISTORY_YEARS and earnings_base and earnings_base > 0:
            fair = _winsorized_median(pe_history)
            if fair and (tp := self._bounded(fair * earnings_base, price)):
                values.append(tp)
                used.append("pe")
        pb_history = [v for item in ratios if (v := _valid_multiple(item.get("price_to_book"), PB_RANGE))]
        if len(pb_history) >= MIN_HISTORY_YEARS and inputs["book_value"]:
            fair = _winsorized_median(pb_history)
            if fair and (tp := self._bounded(fair * inputs["book_value"], price)):
                values.append(tp)
                used.append("price_to_book")
        if not values:
            return None
        years = max(len(pe_history), len(pb_history))
        current_pe = (
            price / earnings_base if earnings_base and earnings_base > 0 else None
        )
        percentile = None
        if current_pe is not None and pe_history:
            percentile = round(
                sum(1 for value in pe_history if value <= current_pe) / len(pe_history), 2
            )
        return {
            "tp": median(values),
            "reliability": round(_clamp(years / 10, 0.3, 1.0), 3),
            "metrics_used": used,
            "history_years": years,
            "current_pe_percentile_in_history": percentile,
        }

    def _earnings_power_tp(
        self,
        inputs: dict[str, Any],
        price: float,
        fair_pe: float | None,
        fair_pe_source: str | None,
        profile: str,
    ) -> dict[str, Any] | None:
        if fair_pe is None:
            return None
        base = inputs["ntm_eps"]
        base_kind = "ntm_fy_weighted"
        if profile == "cyclical":
            # Frozen rule: cyclicals are valued on mid-cycle earnings; peak
            # TTM/NTM is never the sole base.
            if inputs["mid_cycle_eps"]:
                base = inputs["mid_cycle_eps"]
                base_kind = "mid_cycle_median"
            elif base is not None:
                base_kind = "ntm_unnormalized_flagged"
        if base is None or base <= 0:
            return None
        tp = self._bounded(fair_pe * base, price)
        if tp is None:
            return None
        reliability = _clamp(inputs["analysts_eps"] / 20, 0.3, 1.0)
        if base_kind == "ntm_unnormalized_flagged":
            reliability *= 0.6
        return {
            "tp": tp,
            "reliability": round(reliability, 3),
            "fair_pe": round(fair_pe, 2),
            "fair_pe_source": fair_pe_source,
            "earnings_base": base_kind,
        }

    def _consensus_dcf_tp(
        self, inputs: dict[str, Any], price: float, profile: str,
    ) -> dict[str, Any] | None:
        base = inputs["ntm_eps"]
        base_kind = "ntm_fy_weighted"
        if profile == "cyclical" and inputs["mid_cycle_eps"]:
            base = inputs["mid_cycle_eps"]
            base_kind = "mid_cycle_median"
        growth = inputs["consensus_growth"]
        if base is None or base <= 0 or growth is None:
            return None
        ke = inputs["cost_of_equity"]
        value = self._two_stage_value(base, growth, ke)
        tp = self._bounded(value, price)
        if tp is None:
            return None
        implied = self._implied_growth(base, ke, price)
        return {
            "tp": tp,
            "reliability": round(_clamp(inputs["analysts_eps"] / 20, 0.3, 1.0) * 0.9, 3),
            "consensus_growth": round(growth, 4),
            "implied_growth": round(implied, 4) if implied is not None else None,
            "cost_of_equity": round(ke, 4),
            "earnings_base": base_kind,
        }

    def _two_stage_value(self, base_eps: float, growth: float, ke: float) -> float:
        present = 0.0
        eps = base_eps
        for year in range(1, 6):
            fade = growth + (self.terminal_growth - growth) * (year - 1) / 5
            eps *= 1 + fade
            present += eps / (1 + ke) ** year
        terminal = eps * (1 + self.terminal_growth) / max(ke - self.terminal_growth, 0.02)
        return present + terminal / (1 + ke) ** 5

    def _implied_growth(self, base_eps: float, ke: float, price: float) -> float | None:
        """P3's reverse question: what 5y growth does the current price imply?"""
        low, high = -0.25, 0.40
        if self._two_stage_value(base_eps, low, ke) > price:
            return low
        if self._two_stage_value(base_eps, high, ke) < price:
            return high
        for _ in range(40):
            mid = (low + high) / 2
            if self._two_stage_value(base_eps, mid, ke) < price:
                low = mid
            else:
                high = mid
        return (low + high) / 2

    def _sustainable_growth(self, inputs: dict[str, Any]) -> float:
        ceiling = self.terminal_growth
        roe = inputs["roe"]
        if roe is None:
            return ceiling * 0.6
        payout = 0.0
        if inputs["dividend_per_share"] and inputs["trailing_eps"]:
            payout = _clamp(inputs["dividend_per_share"] / inputs["trailing_eps"], 0.0, 1.0)
        return _clamp(roe * (1 - (payout or 0.6)), 0.0, ceiling)

    def _rim_tp(self, inputs: dict[str, Any], price: float) -> dict[str, Any] | None:
        book, roe = inputs["book_value"], inputs["roe"]
        if not book or roe is None:
            return None
        ke = inputs["cost_of_equity"]
        growth = self._sustainable_growth(inputs)
        if ke - growth <= 0.005:
            return None
        fair_pb = _clamp((roe - growth) / (ke - growth), 0.3, 8.0)
        tp = self._bounded(book * fair_pb, price)
        if tp is None:
            return None
        return {"tp": tp, "reliability": 0.75, "fair_price_to_book": round(fair_pb, 2)}

    def _ddm_tp(self, inputs: dict[str, Any], price: float) -> dict[str, Any] | None:
        dividend = inputs["dividend_per_share"]
        if not dividend:
            return None
        ke = inputs["cost_of_equity"]
        growth = self._sustainable_growth(inputs)
        if ke - growth <= 0.005:
            return None
        tp = self._bounded(dividend * (1 + growth) / (ke - growth), price)
        if tp is None:
            return None
        return {"tp": tp, "reliability": 0.6, "gordon_growth": round(growth, 4)}

    # -------------------------------------------------------------- aggregation

    def _aggregate(
        self,
        row: dict[str, Any],
        inputs: dict[str, Any],
        models: dict[str, dict[str, Any]],
        price: float,
        ladder: list[str],
        profile: str,
    ) -> dict[str, Any]:
        weighted = [(name, item["tp"], max(item["reliability"], 0.05)) for name, item in models.items()]
        total_weight = sum(weight for _, _, weight in weighted)
        internal_tp = sum(tp * weight for _, tp, weight in weighted) / total_weight
        tps = [tp for _, tp, _ in weighted]
        dispersion_ratio = max(tps) / max(min(tps), 0.01) if len(tps) >= 2 else None
        low_conviction = len(tps) < 2 or (
            dispersion_ratio is not None and dispersion_ratio > LOW_CONVICTION_DISPERSION_RATIO
        )

        consensus_tp = _number(row.get("public_consensus_tp")) or _number(
            row.get("eodhd_consensus_tp")
        ) or _number(row.get("brapi_consensus_tp"))
        analyst_count = int(_number(row.get("analyst_count")) or 0) or max(
            int(_number(row.get("eodhd_analysts")) or 0),
            int(_number(row.get("brapi_analysts")) or 0),
        )
        divergence = (
            abs(internal_tp / consensus_tp - 1) if consensus_tp and consensus_tp > 0 else None
        )
        divergence_flag = None
        if divergence is not None:
            if divergence > DIVERGENCE_LOW_CONVICTION_BAND:
                divergence_flag = "low_conviction_band"
                low_conviction = True
            elif divergence > DIVERGENCE_NOTE_BAND:
                divergence_flag = "note_band"
        elif not any(name in models for name in ("peer_comps", "own_history")):
            # No consensus AND neither external anchor -> unable by design.
            low_conviction = True

        if consensus_tp and consensus_tp > 0:
            if analyst_count >= 8:
                consensus_weight = 0.35
            elif analyst_count >= 3:
                consensus_weight = 0.25
            elif analyst_count >= 1:
                consensus_weight = 0.20
            else:
                consensus_weight = 0.20
            if low_conviction:
                consensus_weight = MAX_CONSENSUS_SHRINK
        else:
            consensus_weight = 0.0
        v2_tp = internal_tp * (1 - consensus_weight) + (consensus_tp or 0.0) * consensus_weight

        attribution = None
        if consensus_tp and consensus_tp > 0:
            attribution = max(
                models.items(), key=lambda pair: abs(pair[1]["tp"] / consensus_tp - 1)
            )[0]

        spread = _clamp(((dispersion_ratio or 1.2) - 1) / 2, 0.08, 0.25)
        if low_conviction:
            spread *= 1.35

        return {
            "symbol": str(row.get("symbol")),
            "engine_version": ENGINE_VERSION,
            "profile": profile,
            "price": price,
            "v2_tp": round(v2_tp, 4),
            "v2_internal_tp": round(internal_tp, 4),
            "v2_upside_percent": round((v2_tp / price - 1) * 100, 2),
            "bear_tp": round(v2_tp * (1 - spread), 4),
            "bull_tp": round(v2_tp * (1 + spread), 4),
            "models": {
                name: {**item, "tp": round(item["tp"], 4), "label": MODEL_LABELS[name]}
                for name, item in models.items()
            },
            "model_count": len(models),
            "dispersion_ratio": round(dispersion_ratio, 3) if dispersion_ratio else None,
            "low_conviction": low_conviction,
            "consensus_tp": consensus_tp,
            "analyst_count": analyst_count,
            "consensus_weight": consensus_weight,
            "divergence_vs_consensus": round(divergence, 4) if divergence is not None else None,
            "divergence_flag": divergence_flag,
            "attribution_model": attribution,
            "fair_multiple_ladder": ladder,
            "risk_free_rate": round(self.risk_free_rate, 4),
            "risk_free_source": self.risk_free_source,
            "cost_of_equity": round(inputs["cost_of_equity"], 4),
        }
