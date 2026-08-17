from app.valuation_policy import C3PO_VALUATION_POLICY


def test_canonical_policy_covers_every_valuation_surface() -> None:
    assert set(C3PO_VALUATION_POLICY.surfaces) == {
        "candidate_stocks",
        "matrix_power",
        "one_pager",
        "company_intelligence",
        "portfolio_intelligence",
    }
    assert C3PO_VALUATION_POLICY.version > 0
    assert round(sum(C3PO_VALUATION_POLICY.score_weights.values()), 10) == 1.0

