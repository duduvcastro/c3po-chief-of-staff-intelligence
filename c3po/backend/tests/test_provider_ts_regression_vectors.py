from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "provider_ts_no_tape_support_v1.json"


def test_provider_ts_fixture_preserves_all_nominal_no_tape_support_cases() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["case_count"] == len(cases) == 18
    assert payload["unique_fill_count"] == len({case["fill_id"] for case in cases}) == 14
    assert payload["unique_symbol_count"] == len({case["symbol"] for case in cases}) == 12
    assert len({case["case_id"] for case in cases}) == 18
    assert {case["study"] for case in cases} == {
        "entry_quality_v1",
        "exit_policy_v1_1",
    }
    assert all(case["classification_reason"] == "no_trade_within_10bps" for case in cases)
    assert all(case["nearest_trade_bps"] > 10.0 for case in cases)

    assert Counter(case["symbol"] for case in cases) == Counter(
        {
            "AMP": 1,
            "ANIP": 1,
            "BRUN": 1,
            "BVN": 3,
            "CNX": 1,
            "CSTM": 1,
            "ETOR": 1,
            "GPOR": 1,
            "INGR": 2,
            "LIFE": 3,
            "PJT": 1,
            "WIX": 2,
        }
    )


def test_provider_ts_fixture_is_pinned_to_verified_probe_hashes() -> None:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))["source"]

    assert source == {
        "run_id": "33069776868",
        "manifest_file_sha256": "e4b318a155863078486b03c322ef88ac49d97cd57074d5062fd652d85f722adf",
        "report_file_sha256": "0f72e092cf2d4251f1dacf87b3c16233e568477a7d3e2a696813e11648129ba6",
        "report_self_sha256": "aeff080a2c23b9dc523697f991bfe1afe2d0d0e575277fb55eace18ad5a65e67",
        "raw_tape_sha256": "b8bf7f8a1d81adee6bbfacec31e4a3847accc54245f77fe0f5d6f4918c033cfd",
    }
