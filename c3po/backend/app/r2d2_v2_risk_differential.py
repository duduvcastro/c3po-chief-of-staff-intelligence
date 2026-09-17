"""Offline contemporary same-input comparison against independent origin paths.

No provider calls, real database or orders. Private input/output contains names.
The caller must establish factual capture provenance; synthetic tests are not it.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, cast

from app.config import Settings
from app.database import Database
from app.foreign_listings import normalize_foreign_fundamentals, policy_for
from app.market_data.http import JsonHttpClient
from app.market_data.eodhd import EodhdClient
from app.market_data.fmp import FmpClient
from app.official_fundamentals import apply_official_fundamentals
from app.one_pager import OnePagerService
from app.r2d2_v2_risk_acquisition import SourceReceipt
from app.r2d2_v2_risk_bundle import build_risk_bundle
from app.r2d2_v2_risk_source import (ORACLE_ONE_PAGER_SHA256, ORACLE_REVISION, ORIGIN_REVISION,
    CanonicalRiskInputs, InsiderActivity, InstitutionalPositions, canonical_risk_score)

ORIGIN_PINS = {
    "app/one_pager.py": "e49265da0cfc4cd10ab8e94d826ff8be38ee1d278137769a62d3c9a86f006e0d",
    "app/database.py": "30f406c141e06dba326aeab74669a38ff67a907d76d0a7b8752271c9f5221173",
    "app/market_data/eodhd.py": "f66f35a561e2ae71d978c39a73c83fb67de6297d1333a5054acacdef633faa4f",
    "app/market_data/fmp.py": "ea975e146251492add3dbb2f9fc20cb983d63c7cf5512df76a7f8dea6ec6a9ed",
    "app/foreign_listings.py": "26242b5b4efbff7f06aff98f1a8b2f9884942e33b903d0c94a457dfad5f20d14",
    "app/official_fundamentals.py": "b6edf7903931ce781735bc1c80d3c9ee865d6b4a8cd1f414589f8e6c23e27ff5",
}
PREREGISTERED_LIST = "eba757a4953c20d1b25e56c9006265a82c16acbaa1a37d297715d7508a20acb1"
PREREGISTERED_RECEIPT = "a47f8d333d9ff15a9a03eafb6289162cf320a808dc4a46e65f63047f9cd5f299"
CLASSIFIED_CODES = frozenset({
    "FUNDAMENTALS_IDENTITY_MISMATCH", "PATH_A_FX_MISSING", "SOURCE_RECEIPT_BINDING_INVALID",
    "MARKET_INVALID", "US_SOURCE_RECEIPTS_REQUIRED", "BUNDLE_CLOCK_INVALID",
    "OFFICIAL_SNAPSHOT_IDENTITY_INVALID", "OFFICIAL_SNAPSHOT_INVALID", "PATH_A_FX_RECEIPT_MISSING",
    "PATH_A_FX_RECEIPT_BINDING_INVALID", "INSIDER_SNAPSHOT_IDENTITY_INVALID", "INSIDER_EVENTS_INVALID",
    "INSTITUTIONAL_REQUEST_MISMATCH", "GRADES_REQUEST_MISMATCH", "SYMBOL_INVALID",
    "INSIDER_DECISION_CLOCK_INVALID", "INSIDER_PUBLICATION_CLOCK_INVALID", "INSIDER_FUTURE_EVENT",
    "INSIDER_EVENT_ID_MISSING", "INSIDER_DUPLICATE_EVENT", "INSIDER_METADATA_INVALID",
    "NUMBER_MISSING_OR_INVALID", "COUNT_INVALID", "INSTITUTIONAL_ROW_MISSING",
    "INSTITUTIONAL_IDENTITY_MISMATCH", "GRADES_WINDOW_OR_PAYLOAD_INVALID", "GRADES_IDENTITY_MISMATCH",
    "GRADES_FUTURE_RECORD", "GRADES_FIELDS_MISSING", "QUARTERLY_STATEMENTS_MISSING",
    "STATEMENT_DATE_INVALID", "STATEMENT_FUTURE_PERIOD", "TTM_FOUR_QUARTERS_REQUIRED",
    "STATEMENT_DUPLICATE_PERIOD", "STATEMENT_CURRENCY_MISMATCH", "TTM_NOT_FINITE",
})


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def verify_oracle_sources(origin_sources: Mapping[str, bytes]) -> dict[str, Any]:
    """Reject changed imported source; distinguish whole-file and method pins."""
    if set(origin_sources) != set(ORIGIN_PINS):
        raise ValueError("ORIGIN_SOURCE_SET_INVALID")
    backend = Path(__file__).resolve().parents[1]
    runtime = {}
    for path, expected in ORIGIN_PINS.items():
        if _sha(origin_sources[path]) != expected:
            raise ValueError("ORIGIN_SOURCE_HASH_INVALID")
        runtime[path] = (backend / path).read_bytes()
    if _sha(runtime['app/one_pager.py']) != ORACLE_ONE_PAGER_SHA256:
        raise ValueError("ORACLE_SOURCE_HASH_INVALID")
    for path in ('app/market_data/fmp.py', 'app/foreign_listings.py', 'app/official_fundamentals.py'):
        if runtime[path] != origin_sources[path]:
            raise ValueError("ORIGIN_AUXILIARY_CHANGED")
    methods = {'app/database.py': ('save_ir_events', 'insider_transaction_activity', '_insider_transaction_direction'),
               'app/market_data/eodhd.py': ('_normalize_fundamentals', '_latest_statement', '_statement_rows', '_valid_date', '_dated_rows', 'normalize_logo_url')}
    for path, names in methods.items():
        for name in names:
            trees = [[node for node in ast.walk(ast.parse(raw)) if isinstance(node, ast.FunctionDef) and node.name == name]
                     for raw in (origin_sources[path], runtime[path])]
            if any(len(nodes) != 1 for nodes in trees) or ast.dump(trees[0][0]) != ast.dump(trees[1][0]):
                raise ValueError("ORIGIN_METHOD_CHANGED")
    return {'origin_revision': ORIGIN_REVISION, 'origin_sha256': dict(ORIGIN_PINS),
            'oracle_revision': ORACLE_REVISION, 'runtime_sha256': {path: _sha(raw) for path, raw in runtime.items()},
            'origin_methods_ast_identical': methods}


class RecordedFmpHttp:
    """An in-memory HTTP adapter. Unexpected calls never leave the process."""
    def __init__(self, receipts: tuple[SourceReceipt, ...]) -> None:
        self.receipts = receipts
        self.calls: list[str] = []
        self.failed = False

    def get_json(self, url: str, *, params: dict[str, Any]) -> Any:
        clean = {key: value for key, value in params.items() if key != 'apikey'}
        matching = [receipt for receipt in self.receipts
                    if url == 'https://recorded.invalid' + receipt.request.path
                    and dict(receipt.request.parameters) == clean and receipt.request.provider == 'fmp']
        if len(matching) != 1:
            self.failed = True
            raise ValueError("RECORDED_REQUEST_UNMATCHED")
        receipt = matching[0]
        if (receipt.status != 200 or receipt.diagnostic is not None
                or _sha(receipt.body) != receipt.payload_sha256):
            self.failed = True
            raise ValueError("RECORDED_RESPONSE_INVALID")
        self.calls.append(receipt.request.path)
        return copy.deepcopy(receipt.payload())


def independent_oracle(arguments: dict[str, Any], *, control_price: float = 1.0) -> dict[str, Any]:
    """Execute origin normalization and actual legacy _analyze independently.

    Non-FX control_price is a labelled positive auxiliary test constant, not a
    fabricated quote; it must not affect canonical risk. FX uses its factual
    quote_price from the same private bundle, never the control constant.
    """
    symbol = arguments['symbol']
    fundamentals = EodhdClient._normalize_fundamentals(arguments['fundamentals'].payload())
    policy = policy_for(symbol)
    quote_price = control_price
    if policy is not None:
        quote_price = arguments['quote_price']
        fundamentals = normalize_foreign_fundamentals(fundamentals, policy=policy,
                                                       fx_rate=arguments['fx_rate'], quote_price=quote_price)
    official = arguments['official_snapshot'].payload()
    fundamentals = apply_official_fundamentals(fundamentals, official['outputs'])
    snapshot = arguments['insider_snapshot'].payload()
    cutoff = datetime.fromisoformat(snapshot['query_cutoff_at'])
    events = copy.deepcopy(snapshot['events'])
    for event in events:
        for key in ('published_at', 'collected_at', 'reviewed_at'):
            if isinstance(event.get(key), str):
                event[key] = datetime.fromisoformat(event[key])
    database = Database(Settings(database_url=''))
    if database.database_url:
        raise ValueError("ORACLE_DATABASE_NOT_ISOLATED")
    saved = database.save_ir_events(events)
    activity = database.insider_transaction_activity([symbol], 'US', cutoff-timedelta(days=180)).get(symbol)
    grades_receipt, institutional_receipt = arguments['grades'], arguments['institutional']
    http = RecordedFmpHttp((grades_receipt, institutional_receipt))
    fmp = FmpClient('https://recorded.invalid', 'OFFLINE-NO-CREDENTIAL', cast(JsonHttpClient, http))
    year, quarter = fmp.latest_reportable_13f_quarter(institutional_receipt.started_at.date())
    institutional = fmp.institutional_positions(symbol, year=year, quarter=quarter)
    grades = fmp.recent_grades(symbol, since=grades_receipt.started_at.date()-timedelta(days=90))
    if http.failed or len(http.calls) != 2:
        raise ValueError("ORACLE_RECORDED_CALLS_INCOMPLETE")
    analysis = object.__new__(OnePagerService)._analyze(
        symbol, 'US', {'price': quote_price}, fundamentals, role='producer',
        shared_valuation=None, insider_activity=activity,
        institutional_positions=institutional, recent_grades=grades)
    return json.loads(json.dumps({'risk_score': analysis['risk_score'], 'insider_activity': activity,
            'institutional_positions': institutional, 'recent_grades': grades,
            'saved_event_count': saved, 'auxiliary_control_price': None if policy else control_price,
            'factual_fx_quote_used': policy is not None}, default=str))


def compare_contemporary_sample(*, sample_bytes: bytes, sample_sha256: str,
                                bundles: Mapping[str, dict[str, Any]],
                                origin_sources: Mapping[str, bytes]) -> dict[str, Any]:
    """Private report; public callers publish only aggregate and hashes.

    Gate: at least 10 READY, all READY exactly equal, zero unclassified errors.
    With fewer than 10 READY return INCONCLUSIVE, never a vacuous PASS.
    """
    if _sha(sample_bytes) != sample_sha256:
        raise ValueError("SAMPLE_HASH_INVALID")
    sample = json.loads(sample_bytes)
    names = sample.get('symbols')
    if (sample.get('schema') != 'RISK_DIFFERENTIAL_SAMPLE_V1'
            or sample.get('namespace') != 'R2D2-V2-DIAG-ENSAIO-2026-09-14'
            or sample.get('session_date') != '2026-09-14'
            or sample.get('list_sha256') != PREREGISTERED_LIST
            or sample.get('receipt_sha256') != PREREGISTERED_RECEIPT
            or not isinstance(names, list) or not 1 <= len(names) <= 20
            or any(not isinstance(name, str) or not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', name) for name in names)
            or len(names) != len(set(names))
            or list(bundles) != names):
        raise ValueError("SAMPLE_BINDING_INVALID")
    selected = datetime.fromisoformat(sample['selected_at'])
    envelope_sha = sample.get('source_envelope_sha256')
    if (selected.tzinfo is None or selected.utcoffset() is None or not isinstance(envelope_sha, str)
            or not re.fullmatch(r'[0-9a-f]{64}', envelope_sha)):
        raise ValueError("SAMPLE_PROVENANCE_INVALID")
    source_pins = verify_oracle_sources(origin_sources)
    counts = {'READY': 0, 'READY_EXACT': 0, 'READY_MISMATCH': 0,
              'COMPLETED_NULL': 0, 'CLASSIFIED_REFUSAL': 0, 'UNCLASSIFIED_EXCEPTION': 0}
    comparisons = {}
    arithmetic_exact = 0
    arithmetic_mismatch = 0
    for symbol in names:
        arguments = bundles[symbol]
        if arguments.get('symbol') != symbol or arguments.get('market') != 'US':
            raise ValueError("SAMPLE_SYMBOL_IDENTITY_INVALID")
        if any(arguments[name].started_at < selected for name in ('fundamentals', 'grades', 'institutional')):
            raise ValueError("SAMPLE_CAPTURE_PRECEDES_SELECTION")
        stage = 'candidate'
        try:
            candidate = build_risk_bundle(**arguments)
            stage = 'oracle'
            oracle = independent_oracle(arguments)
            raw_inputs = dict(candidate['calculation']['inputs'])
            for key, cls in (('insider_activity', InsiderActivity), ('institutional_positions', InstitutionalPositions)):
                if raw_inputs[key] is not None:
                    raw_inputs[key] = cls(**raw_inputs[key])
            if raw_inputs['recent_grade_actions'] is not None:
                raw_inputs['recent_grade_actions'] = tuple(raw_inputs['recent_grade_actions'])
            diagnostic_score = canonical_risk_score(CanonicalRiskInputs(**raw_inputs))
            arithmetic_matches = diagnostic_score == oracle['risk_score']
            arithmetic_exact += int(arithmetic_matches)
            arithmetic_mismatch += int(not arithmetic_matches)
            status = candidate['status']
            if status == 'READY':
                counts['READY'] += 1
                same = candidate['risk']['value'] == oracle['risk_score']
                counts['READY_EXACT' if same else 'READY_MISMATCH'] += 1
            elif status == 'COMPLETED_NULL':
                counts['COMPLETED_NULL'] += 1
            else:
                counts['CLASSIFIED_REFUSAL'] += 1
            comparisons[symbol] = {'status': status, 'candidate': candidate,
                                   'legacy_oracle': oracle, 'same_raw_bundle': True,
                                   'diagnostic_arithmetic_score': diagnostic_score,
                                   'arithmetic_exact': arithmetic_matches}
        except ValueError as error:
            # Only fixed uppercase diagnostic codes are classified. Never echo
            # a raw exception or provider field that could disclose credentials.
            code = str(error)
            if stage == 'candidate' and code in CLASSIFIED_CODES:
                counts['CLASSIFIED_REFUSAL'] += 1
                comparisons[symbol] = {'status': 'CLASSIFIED_REFUSAL', 'code': code}
            else:
                counts['UNCLASSIFIED_EXCEPTION'] += 1
                comparisons[symbol] = {'status': 'UNCLASSIFIED_EXCEPTION'}
        except Exception:
            counts['UNCLASSIFIED_EXCEPTION'] += 1
            comparisons[symbol] = {'status': 'UNCLASSIFIED_EXCEPTION'}
    status = ('NO_GO' if counts['READY_MISMATCH'] or counts['UNCLASSIFIED_EXCEPTION']
              else 'INCONCLUSIVE' if counts['READY'] < 10 else 'PASS')
    aggregate = {'schema': 'RISK_CONTEMPORARY_DIFFERENTIAL_V1', 'status': status,
                 'sample_sha256': sample_sha256, 'sample_count': len(names), 'minimum_ready': 10,
                 'counts': counts, 'origin_revision': ORIGIN_REVISION, 'oracle_revision': ORACLE_REVISION,
                 'historical_proof': False, 'capture_provenance_independently_verified': False,
                 'production_authorized': False}
    aggregate['arithmetic_gate_rev2'] = {
        'disposition_comment': 5718883179, 'required': 20, 'exact': arithmetic_exact,
        'mismatches': arithmetic_mismatch,
        'status': 'PASS' if len(names) == 20 and arithmetic_exact == 20 and not counts['UNCLASSIFIED_EXCEPTION'] else 'NO_GO',
        'coverage_authorization': False}
    private = {'aggregate': aggregate, 'source_pins': source_pins, 'comparisons': comparisons}
    private['sha256'] = _sha(json.dumps(private, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False).encode())
    return private
