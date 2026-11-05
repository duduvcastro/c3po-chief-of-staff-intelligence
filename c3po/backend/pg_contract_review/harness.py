"""Future real-PG fixtures for an externally provisioned disposable cluster.

Import is inert. No role/database/container is provisioned and no production DSN
is accepted. These methods are NOT called by the local synthetic test suite.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from app.config import Settings
from app.database import Database
from app.listed_universe import Catalogue, Listing, digest
from app.listed_universe_runtime import producer_identity
from app import listed_universe_pg as adapter
from app import valuation_official as official
from app.valuation_policy import METHODOLOGY_VERSION
from .plan import PreconditionError, ReviewPlan, assert_no_ambient_libpq

OWNER = "c3po_full_universe_owner"  # proposed prerequisite, not an observed role
MARKETS = ("B3", "NASDAQ", "NYSE")


def required_row(cursor) -> tuple[Any, ...]:
    row = cursor.fetchone()
    if row is None:
        raise PreconditionError("a required real PostgreSQL metadata row is absent")
    return tuple(row)


def synthetic_row(symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "name": "SYNTHETIC DATABASE CONTRACT FIXTURE", "price": 5.0,
            "our_tp": 20.0, "buy_in": 10.0, "internal_tp": 20.0, "internal_buy_in": 10.0,
            "internal_score": 70.0, "internal_status": "full_match", "internal_expected_total_return_percent": 20.0}


def record_params(record: dict[str, Any]) -> tuple[Any, ...]:
    numeric = Database._numeric_param
    return (record["id"], record["source"], record["source_version"], record["market"], record["symbol"], record["scope"],
            record["session_date"], record["cycle_id"], record["prediction_instant"], record["published_at"],
            numeric(record["tp"]), numeric(record["buy_in"]), numeric(record.get("internal_tp")), numeric(record.get("consensus_tp")),
            record.get("consensus_source"), record.get("analyst_count"), numeric(record.get("consensus_weight_percent")),
            numeric(record.get("price")), record["currency"], json.dumps(record["decomposition"]), record["row_sha256"])


class _SeedDatabase(Database):
    """Canonical fixture creation before installation; no DSN in Settings."""
    def __init__(self, harness: ReviewHarness) -> None:
        super().__init__(Settings(database_url="explicit-local-review-seed", auth_cookie_secure=False))
        self.harness = harness

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.harness.connect("schema_admin") as connection:
            # Restore the ordinary Database connection's transaction semantics
            # after the isolated-cluster identity guard's autocommit reads.
            connection.autocommit = False
            with connection:
                yield connection


class ReviewHarness:
    def __init__(self, plan: ReviewPlan, ddl: Path) -> None:
        self.plan, self.ddl = plan, ddl
        self.connections: list[Any] = []
        self.server_started_at: Any = None
        self.preconditions_verified = False
        self.catalogues: dict[str, Catalogue] = {}
        self.stages: dict[str, str] = {}
        self.database = _SeedDatabase(self)

    def _open(self, actor: str):
        assert_no_ambient_libpq(os.environ)
        # Delayed import: ordinary pytest discovery/import can never connect.
        import psycopg
        connection = psycopg.connect(**self.plan.connection_kwargs(actor, os.environ))
        self.connections.append(connection)
        try:
            self._guard(connection, actor)
        except BaseException:
            connection.close()
            self.connections.remove(connection)
            raise
        return connection

    @contextmanager
    def connect(self, actor: str):
        connection = self._open(actor)
        try:
            yield connection
        finally:
            connection.close()
            self.connections.remove(connection)

    def _guard(self, connection, actor: str) -> None:
        row = connection.execute("SELECT current_database(), current_user::text, session_user::text, inet_server_addr(), pg_postmaster_start_time()").fetchone()
        expected = self.plan.users[actor]
        if not row or row[:3] != (self.plan.database, expected, expected) or row[3] is not None:
            raise PreconditionError("connection is not the explicitly named local review database/principal")
        marker = connection.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=current_database()").fetchone()
        if not marker or marker[0] != self.plan.database_comment:
            raise PreconditionError("externally provisioned disposable database marker is absent")
        if actor == "schema_admin":
            identifier = connection.execute("SELECT system_identifier::text FROM pg_control_system()").fetchone()
            if not identifier or identifier[0] != self.plan.server_system_identifier:
                raise PreconditionError("local cluster system identifier differs from the externally verified plan")
            if self.server_started_at is None:
                self.server_started_at = row[4]
        if self.server_started_at is None or self.server_started_at != row[4]:
            raise PreconditionError("cluster identity/start time was not verified or changed")

    def preflight(self) -> None:
        if hashlib.sha256(self.ddl.read_bytes()).hexdigest() != self.plan.ddl_sha256:
            raise PreconditionError("dormant DDL digest changed")
        with self.connect("schema_admin") as connection:
            if required_row(connection.execute("SELECT to_regnamespace('c3po_full_universe')"))[0] is not None:
                raise PreconditionError("use a fresh disposable database: the ownership schema already exists")
            for relation in ("analysis_snapshots", "valuation_predictions", "valuation_official_selection", "methodology_versions"):
                if required_row(connection.execute("SELECT to_regclass(%s)", ("public."+relation,)))[0] is None:
                    raise PreconditionError("original canonical schema must be provisioned externally before this suite")
            for relation in ("analysis_snapshots", "valuation_predictions", "valuation_official_selection"):
                count = required_row(connection.execute("SELECT count(*) FROM public."+relation))[0]
                if count:
                    raise PreconditionError("fresh fixture database required; existing canonical/PIT snapshot data is never cleared")
            rows = connection.execute("SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolcanlogin FROM pg_roles WHERE rolname=ANY(%s)",
                                      ([OWNER, *self.plan.users.values()],)).fetchall()
            roles = {row[0]: row[1:] for row in rows}
            for name in (OWNER, "c3po", adapter.PUBLISHER, "c3po_full_universe_operator"):
                if name not in roles or any(roles[name][:4]) or roles[name][4] != (name != OWNER):
                    raise PreconditionError("externally provisioned role flags do not satisfy the proposed ownership contract")
            admin = self.plan.users["schema_admin"]
            if (not roles[admin][0] and not required_row(connection.execute("SELECT pg_has_role(%s,%s,'MEMBER')", (admin, OWNER)))[0]
                    or not required_row(connection.execute("SELECT has_database_privilege(current_user,current_database(),'CREATE')"))[0]):
                raise PreconditionError("actual review admin lacks the externally required installation ownership/schema capability")
            for relation in ("analysis_snapshots", "valuation_predictions", "valuation_official_selection"):
                owner = connection.execute("SELECT pg_get_userbyid(c.relowner) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=%s", (relation,)).fetchone()
                if not owner or owner[0] != OWNER:
                    raise PreconditionError("canonical object ownership handoff must be prepared externally, not assumed")
            for actor, target in (("c3po", OWNER), ("c3po", adapter.PUBLISHER), ("c3po", "c3po_full_universe_operator"),
                                  (adapter.PUBLISHER, OWNER), ("c3po_full_universe_operator", OWNER)):
                if required_row(connection.execute("SELECT pg_has_role(%s,%s,'MEMBER')", (actor, target)))[0]:
                    raise PreconditionError("actual role membership violates the proposed isolated-principal contract")
        # Verify all four *authenticated* identities, not SET ROLE substitutes.
        for actor in self.plan.users:
            with self.connect(actor) as connection:
                if actor == "legacy":
                    for action in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        if not required_row(connection.execute("SELECT has_table_privilege(current_user,'public.analysis_snapshots',%s)", (action,)))[0]:
                            raise PreconditionError("legacy test principal needs ordinary DML privileges to exercise conditional fencing")
                if actor == "publisher" and required_row(connection.execute("SHOW transaction_isolation"))[0] != "read committed":
                    raise PreconditionError("test publisher must really use READ COMMITTED; no isolation override is inferred")
        self.preconditions_verified = True

    def seed_before_installation(self) -> None:
        if not self.preconditions_verified:
            raise PreconditionError("real disposable-database preflight must precede fixture writes")
        method = self.database.ensure_methodology_version("full_universe_pg_test_fixture", METHODOLOGY_VERSION, {}, "SYNTHETIC TEST DATA ONLY")
        for market in MARKETS:
            with self.connect("schema_admin") as connection:
                at = required_row(connection.execute("SELECT clock_timestamp()"))[0]
            self.database.save_analysis_snapshot("valuation_universe", market+"_UNIVERSE", method,
                {"methodology_version": METHODOLOGY_VERSION}, {"rows": [synthetic_row("LEGACY_"+market)], "universe_size": 1}, at)
        for market in MARKETS:
            with self.connect("schema_admin") as connection:
                at = required_row(connection.execute("SELECT clock_timestamp()"))[0]
            source = {"B3": "https://bvmf.bmfbovespa.com.br/suplemento/ExecutaAcaoDownload.asp?arquivo=Titulos_Negociaveis.zip&server=L",
                      "NASDAQ": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                      "NYSE": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"}[market]
            listings = (Listing(market, market+"_ONE", "SYNTHETIC STOCK"), Listing(market, market+"_MISSING", "SYNTHETIC MISSING"))
            catalogue = Catalogue(market, source, "b3-titulos-220-v1" if market == "B3" else "nasdaq-trader-pipe-v1",
                at.isoformat(), at.date().isoformat() if market == "B3" else at.isoformat(), digest({"synthetic": market}), 2, {}, listings)
            run, context = digest({"test_run": market}), digest({"test_context": market})
            rows = [synthetic_row(market+"_ONE")]
            stage = self.database.save_analysis_snapshot("full_universe_stage", market, method,
                {"canonical_methodology_version": METHODOLOGY_VERSION, "run_identity": run, "source_manifest_sha256": catalogue.payload()["manifest_sha256"]},
                {"rows": rows, "not_evaluable": {market+"_MISSING": "synthetic_statements_missing"}, "inventory_count": 2, "context_sha256": context}, at)
            records = [official.prediction_from_row(row, market=market, scope="universe", cycle_id=stage,
                source_version=str(METHODOLOGY_VERSION), prediction_instant=at, published_at=at, source=source_name,
                source_manifest_sha256=catalogue.payload()["manifest_sha256"],
                extra_provenance={"full_universe_stage": True, "run_identity": run, "context_sha256": context})
                for source_name in official.OFFICIAL_SOURCES for row in rows]
            if any(record is None for record in records):
                raise PreconditionError("canonical exchange calendar/fixture was not recordable")
            self.database.insert_valuation_predictions([record for record in records if record is not None])
            self.catalogues[market], self.stages[market] = catalogue, stage

    def install_review_artifact(self) -> None:
        if not self.preconditions_verified or not self.stages:
            raise PreconditionError("empty verified disposable setup and synthetic cohort must precede installation")
        if hashlib.sha256(self.ddl.read_bytes()).hexdigest() != self.plan.ddl_sha256:
            raise PreconditionError("dormant DDL digest changed")
        with self.connect("schema_admin") as connection:
            connection.execute(self.ddl.read_bytes())  # hash-bound file bytes; FUTURE OPT-IN ONLY

    def append_synthetic_epoch(self, *, expired: bool) -> None:
        with self.connect("schema_admin") as connection:
            at = required_row(connection.execute("SELECT clock_timestamp()"))[0]
            reviewed = at-timedelta(minutes=2) if expired else at-timedelta(seconds=1)
            until = at-timedelta(minutes=1) if expired else at+timedelta(minutes=10)
            with connection.transaction():
                connection.execute("LOCK TABLE public.analysis_snapshots,public.valuation_predictions,public.valuation_official_selection,c3po_full_universe.epochs IN SHARE ROW EXCLUSIVE MODE NOWAIT")
                connection.execute("""INSERT INTO c3po_full_universe.epochs
                (epoch_id,source,source_version,code_pins_sha256,readiness_receipt_sha256,reviewed_at,readiness_valid_until)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""", (str(uuid4()), official.SOURCE_OFFICIAL, str(METHODOLOGY_VERSION), digest(producer_identity()),
                    digest({"SYNTHETIC_TEST_ONLY_NOT_CAPACITY_OR_FABLE_GO": True}), reviewed, until))

    def head(self, connection) -> dict[str, Any]:
        return adapter.TransactionReadDatabase(connection).latest_valuation_official_selection() or {}

    def compile(self, connection) -> tuple[dict[str, Any], dict[str, Any]]:
        connection.execute("SELECT c3po_full_universe.lock_cohort()")
        at = adapter._clock(connection)
        epoch = adapter._epoch(connection, at)
        compiled = adapter.compile_locked(adapter.TransactionReadDatabase(connection), self.catalogues, self.stages,
            expected_predecessor=str(self.head(connection)["generation_id"]), max_age_seconds=600, published_at=at)
        return compiled, epoch

    def close(self) -> None:
        # Do not DROP/TRUNCATE/repair anything: preserve the disposable database
        # for inspection. The next invocation needs a newly provisioned database.
        for connection in self.connections[:]:
            connection.close()
            self.connections.remove(connection)
