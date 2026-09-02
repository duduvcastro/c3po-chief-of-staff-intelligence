from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
REDUCER_PATH = SCRIPTS / "c3po_interim_m1_reduce.py"
SQL_PATH = SCRIPTS / "c3po_interim_m1_server_aggregate.sql"
SHELL_PATH = SCRIPTS / "c3po_interim_m1_server_read.sh"
SPEC = importlib.util.spec_from_file_location("c3po_interim_m1_reduce", REDUCER_PATH)
assert SPEC is not None and SPEC.loader is not None
reducer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reducer)


def session(
    day: int,
    upper: int,
    lower: int,
    ambiguous: int,
    censored: int,
    *,
    cell: str | None = None,
) -> dict[str, object]:
    entry_count = upper + lower + ambiguous + censored
    row: dict[str, object] = {
        "session_date": f"2026-08-{day:02d}",
        "entry_count": entry_count,
        "upper_first": upper,
        "lower_first": lower,
        "ambiguous_same_bar": ambiguous,
        "censored": censored,
    }
    if cell is not None:
        row.update({
            "cell": cell,
            "primary_observed_count": entry_count,
            "primary_sum": float(upper - lower),
            "mfe_observed_count": entry_count,
            "mfe_sum": float(upper + ambiguous),
            "mae_observed_count": entry_count,
            "mae_sum": float(-(lower + ambiguous)),
        })
    return row


FIXED_VECTOR = [
    session(26, 8, 4, 1, 2),
    session(27, 5, 5, 2, 1),
    session(28, 9, 3, 0, 3),
    session(29, 4, 6, 1, 2),
    session(30, 7, 4, 3, 0),
]


def source_payload(
    rows: list[dict[str, object]],
    *,
    equivalent: bool = True,
) -> dict[str, object]:
    measured = sum(int(row["entry_count"]) for row in rows)
    h3_rows = [
        session(
            26 + index,
            1,
            1,
            0,
            0,
            cell=cell,
        )
        for cell in ("bottom_decile", "top_decile")
        for index in range(2)
    ]
    return {
        "schema": reducer.SOURCE_SCHEMA,
        "generated_at": "2026-09-02T20:15:00.000000Z",
        "database_access": {
            "effective_role": "pg_read_all_data",
            "transaction_read_only": "on",
            "statement_timeout": "2min",
            "lock_timeout": "5s",
            "ddl_or_dml_executed": False,
        },
        "ruler": {
            "policy_epoch": reducer.POLICY_EPOCH,
            "bootstrap_seed": 20260824,
            "bootstrap_iterations": 10000,
            "percentile_method": "nearest_rank_ceil_qn_minus_1",
            "current_epoch_only": True,
            "cross_epoch_pooling": False,
        },
        "equivalence": {
            "canonical_equivalent": equivalent,
            "source_complete": equivalent,
            "reasons": [] if equivalent else ["current_epoch_contains_pre_instrumentation_gap"],
        },
        "cohort": {
            "current_epoch_constructed_count": measured,
            "current_epoch_measured_count": measured,
            "current_epoch_bar_unavailable_count": 0,
            "current_epoch_market_compatibility_violation_count": 0,
        },
        "session_stats": rows if equivalent else [],
        "h3": {
            "session_stats": h3_rows if equivalent else [],
            "cell_totals": {
                "bottom_decile": {"primary_median": 0.0},
                "top_decile": {"primary_median": 0.0},
            } if equivalent else {},
        },
        "fallback": {
            "required": not equivalent,
            "method": "github_runner_session_streaming_rebuild",
            "partial_shadow_result_must_not_be_published": True,
        },
    }


class FrozenMathTests(unittest.TestCase):
    def test_independent_five_session_vector(self) -> None:
        summary = reducer.summarize_barrier(FIXED_VECTOR)

        self.assertAlmostEqual(summary["p_hat"], 0.6)
        self.assertAlmostEqual(summary["p_hat_conservative"], 0.532258064516129)
        self.assertEqual(
            summary["bootstrap_ci95"],
            [0.4807692307692308, 0.6949152542372882],
        )
        self.assertEqual(summary["p_hat_ucb_98_75"], 0.7068965517241379)
        self.assertEqual(
            summary["p_hat_cons_ucb_98_75"],
            0.6666666666666666,
        )

    def test_nearest_rank_is_ceil_qn_minus_one(self) -> None:
        values = [4.0, 1.0, 3.0, 2.0]
        self.assertEqual(reducer.nearest_rank(values, 0.25), 1.0)
        self.assertEqual(reducer.nearest_rank(values, 0.50), 2.0)
        self.assertEqual(reducer.nearest_rank(values, 0.9875), 4.0)

    def test_fifteen_session_ucb_can_trigger_only_at_decision_floor(self) -> None:
        fourteen = [session(1 + index, 0, 1, 0, 0) for index in range(14)]
        fifteen = [session(1 + index, 0, 1, 0, 0) for index in range(15)]

        self.assertEqual(len(fourteen), 14)
        self.assertEqual(reducer.summarize_barrier(fifteen)["p_hat_ucb_98_75"], 0.0)
        self.assertLess(len(fourteen), reducer.MIN_DECISION_SESSIONS)
        self.assertEqual(len(fifteen), reducer.MIN_DECISION_SESSIONS)


class FailClosedContractTests(unittest.TestCase):
    def test_incomplete_source_never_emits_m1(self) -> None:
        source = source_payload([], equivalent=False)
        with self.assertRaises(reducer.SourceIncomplete) as caught:
            reducer.reduce_source(
                source,
                source_sha256="a" * 64,
                query_sha256="b" * 64,
                reducer_sha256="c" * 64,
            )

        diagnostic = reducer.blocked_diagnostic(caught.exception)
        self.assertFalse(diagnostic["m1_emitted"])
        self.assertNotIn("m1", diagnostic)
        self.assertEqual(
            diagnostic["fallback"]["method"],
            "github_runner_session_streaming_rebuild",
        )

    def test_reduced_artifact_reconciles_population_and_self_hash(self) -> None:
        source = source_payload(FIXED_VECTOR)
        payload = reducer.reduce_source(
            source,
            source_sha256="a" * 64,
            query_sha256="b" * 64,
            reducer_sha256="c" * 64,
        )

        self.assertEqual(payload["m1"]["population"], {
            "entry_count": 70,
            "session_count": 5,
        })
        self.assertEqual(payload["m1"]["kill_criterion"]["result"], "WAIT_SAMPLE")
        self.assertFalse(payload["partial_verdict"]["strategy_change_authorized"])
        observed_hash = payload.pop("artifact_sha256")
        self.assertEqual(observed_hash, reducer.canonical_sha256(payload))

    def test_h3_preserves_both_cells_and_preregistered_floors(self) -> None:
        source = source_payload(FIXED_VECTOR)
        payload = reducer.reduce_source(
            source,
            source_sha256="a" * 64,
            query_sha256="b" * 64,
            reducer_sha256="c" * 64,
        )

        self.assertEqual(payload["h3"]["status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(
            payload["h3"]["insufficient_cells"],
            ["bottom_decile", "top_decile"],
        )
        self.assertEqual(payload["h3"]["required_session_count"], 15)
        self.assertEqual(payload["h3"]["required_decided_entries_per_cell"], 30)


class StaticSafetyTests(unittest.TestCase):
    def test_sql_is_read_only_and_withholds_partial_statistics(self) -> None:
        sql = SQL_PATH.read_text(encoding="utf-8")
        self.assertIn("BEGIN TRANSACTION READ ONLY", sql)
        self.assertIn("current_user = 'pg_read_all_data'", sql)
        self.assertIn("default_transaction_read_only", SHELL_PATH.read_text(encoding="utf-8"))
        self.assertIn("WHEN d.canonical_equivalent THEN", sql)
        self.assertIn("current_epoch_contains_pre_instrumentation_gap", sql)
        self.assertIn("partial_shadow_result_must_not_be_published", sql)
        self.assertIsNone(
            re.search(
                r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE)\b",
                sql,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        )

    def test_host_path_uses_existing_database_not_second_api(self) -> None:
        shell = SHELL_PATH.read_text(encoding="utf-8")
        self.assertIn("docker compose", shell)
        self.assertIn("exec -T", shell)
        self.assertIn("db sh -ceu", shell)
        self.assertNotRegex(shell, r"docker\s+compose[\s\S]{0,240}\brun\b")
        command_lines = "\n".join(
            line for line in shell.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotRegex(command_lines, r"\bapi\b")

    def test_query_returns_aggregates_not_raw_identity_columns(self) -> None:
        sql = SQL_PATH.read_text(encoding="utf-8")
        final_select = sql[sql.rfind("SELECT jsonb_build_object"):]
        for prohibited in ("trade_id", "candidate_id", "symbol", "fill_price_local"):
            self.assertNotRegex(final_select, rf"'{re.escape(prohibited)}'")

    def test_scripts_parse_as_utf8_and_blocked_diagnostic_is_json(self) -> None:
        diagnostic = reducer.blocked_diagnostic(
            reducer.SourceIncomplete(["coverage_gap"], {"required": True})
        )
        json.dumps(diagnostic, ensure_ascii=True, allow_nan=False)
        self.assertTrue(REDUCER_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
