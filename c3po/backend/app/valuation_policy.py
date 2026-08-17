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
    version=31,
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
        "Cyclical issuers now use market P/E and EV/EBITDA reconciled against the same normalized earnings "
        "and EBITDA used by the valuation, preventing incomplete TTM denominators from inflating targets. "
        "Broader issuer-published analyst consensus takes precedence over narrower secondary feeds."
    ),
)

METHODOLOGY_KEY = C3PO_VALUATION_POLICY.key
METHODOLOGY_NAME = C3PO_VALUATION_POLICY.name
METHODOLOGY_VERSION = C3PO_VALUATION_POLICY.version
