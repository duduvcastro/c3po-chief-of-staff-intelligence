from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValuationPolicy:
    key: str
    name: str
    version: int
    surfaces: tuple[str, ...]
    score_weights: dict[str, float]
    release_note: str

    @property
    def label(self) -> str:
        return f"{self.name} v{self.version}"


# Single source of truth for every C3PO surface that publishes valuation data.
# A methodology change must update this policy and the shared valuation tests.
C3PO_VALUATION_POLICY = ValuationPolicy(
    key="b3_value_quality",
    name="C3PO Power Model",
    version=32,
    surfaces=(
        "candidate_stocks",
        "matrix_power",
        "one_pager",
        "company_intelligence",
        "portfolio_intelligence",
    ),
    score_weights={
        "tp_upside": 0.35,
        "inverse_risk": 0.25,
        "quality": 0.15,
        "confidence": 0.15,
        "entry": 0.10,
    },
    release_note=(
        "US financial-profile stocks (banks/insurers) no longer use EV/EBITDA or FCF-DCF -- a bank's "
        "reported debt is overwhelmingly customer deposits, not leverage, and its free cash flow is "
        "dominated by loan/deposit balance changes, not owner earnings; both methods produced targets "
        "2-3x price for real names. Real analyst consensus (FMP Ultimate: price-target-consensus, "
        "price-target-summary, broker-level grades, 13F institutional positions) now feeds an explicit "
        "final blend against the internal model and a governance-risk signal, replacing EODHD's single "
        "target price field, which carried no update date and paired with an analyst count that measured "
        "a different population of analysts than the ones behind the price target. US peer-median "
        "benchmarking gained a statistical dispersion guard so a heterogeneous peer bucket (e.g. banks "
        "pooled with high-multiple diversified financials) can't quietly distort a fair multiple. B3 "
        "governance risk now factors in disclosure materiality, and the Selic risk-free input is "
        "cross-checked against real Tesouro Direto market yields and against a staleness warning on its "
        "hardcoded COPOM governor."
    ),
)

METHODOLOGY_KEY = C3PO_VALUATION_POLICY.key
METHODOLOGY_NAME = C3PO_VALUATION_POLICY.name
METHODOLOGY_VERSION = C3PO_VALUATION_POLICY.version
