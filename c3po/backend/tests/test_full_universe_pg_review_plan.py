"""Pure local guards only: no PostgreSQL, SQL parser, DDL or connection."""
import ast
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from pg_contract_review.plan import PreconditionError, assert_no_ambient_libpq, load_plan, parse_plan


def synthetic_plan(ddl_sha="a"*64):
    return {"schema": "FULL-UNIVERSE-LOCAL-PG-REVIEW-PLAN-v1", "database": "c3po_fu_review_"+"1"*32,
            "database_nonce": "22222222-2222-4222-8222-222222222222", "socket_directory": "/private/tmp/fu-review-synthetic",
            "port": 55432, "server_system_identifier": "123456789", "ddl_sha256": ddl_sha,
            "users": {"schema_admin": "synthetic_review_admin", "legacy": "c3po", "publisher": "c3po_full_universe_publisher",
                      "operator": "c3po_full_universe_operator"},
            "password_env": {"schema_admin": "FU_PG_REVIEW_ADMIN_PASSWORD", "legacy": None, "publisher": None, "operator": None}}


def test_valid_descriptor_only_prepares_explicit_unix_socket_kwargs_without_app_defaults():
    plan = parse_plan(synthetic_plan())
    values = plan.connection_kwargs("schema_admin", {"FU_PG_REVIEW_ADMIN_PASSWORD": "synthetic-test-password",
        "PGHOST": "must-not-use", "PGDATABASE": "c3po", "C3PO_DATABASE_URL": "must-not-use"})
    assert values["host"] == "/private/tmp/fu-review-synthetic" and values["dbname"] == "c3po_fu_review_"+"1"*32
    assert values["user"] == "synthetic_review_admin" and values["passfile"] == "/dev/null"
    assert values["password"] == "synthetic-test-password" and "dsn" not in values
    assert plan.database_comment.endswith(plan.database_nonce)


@pytest.mark.parametrize("field,value", [("database", "c3po"), ("database", None), ("socket_directory", "127.0.0.1"),
    ("socket_directory", "/tmp/a/../postgres"), ("socket_directory", "/var/run/postgresql"), ("port", None),
    ("port", True), ("server_system_identifier", None), ("server_system_identifier", "guessed"), ("database_nonce", None),
    ("ddl_sha256", None)])
def test_missing_or_unsafe_external_facts_are_rejected_without_connecting(field, value):
    data = synthetic_plan()
    data[field] = value
    with pytest.raises(PreconditionError):
        parse_plan(data)


def test_actor_roles_and_password_sources_cannot_be_silently_substituted():
    data = synthetic_plan()
    data["users"]["schema_admin"] = data["users"]["publisher"]
    with pytest.raises(PreconditionError, match="separate"):
        parse_plan(data)
    data = synthetic_plan()
    data["password_env"]["publisher"] = "PGPASSWORD"
    with pytest.raises(PreconditionError, match="explicit"):
        parse_plan(data)
    with pytest.raises(PreconditionError, match="unset"):
        parse_plan(synthetic_plan()).connection_kwargs("schema_admin", {})


def test_actual_connection_boundary_rejects_ambient_libpq_overrides_before_driver_import():
    assert_no_ambient_libpq({"FU_PG_REVIEW_ADMIN_PASSWORD": "synthetic"})
    for key in ("PGHOST", "PGPASSWORD", "PGSERVICE", "PGOPTIONS"):
        with pytest.raises(PreconditionError, match="ambient"):
            assert_no_ambient_libpq({key: "must-not-be-used"})


def test_template_is_deliberately_incomplete_not_claimed_live_setup():
    template = Path(__file__).resolve().parents[1]/"pg_contract_review/plan.pending.json"
    with pytest.raises(PreconditionError):
        parse_plan(json.loads(template.read_text()))


def test_private_descriptor_and_exact_ddl_digest_are_mandatory(tmp_path):
    ddl = tmp_path/"dormant.sql"
    ddl.write_text("synthetic bytes, never SQL-parsed or executed")
    path = tmp_path/"plan.json"
    path.write_text(json.dumps(synthetic_plan(hashlib.sha256(ddl.read_bytes()).hexdigest())))
    os.chmod(path, 0o644)
    with pytest.raises(PreconditionError, match="0600"):
        load_plan(path, ddl)
    os.chmod(path, 0o600)
    assert load_plan(path, ddl).database.startswith("c3po_fu_review_")
    link = tmp_path/"linked.json"
    link.symlink_to(path)
    with pytest.raises(PreconditionError, match="symlink"):
        load_plan(link, ddl)
    ddl.write_text("changed synthetic bytes")
    with pytest.raises(PreconditionError, match="differs"):
        load_plan(path, ddl)


def test_importing_harness_and_cases_does_not_import_or_call_a_postgresql_driver(monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("a preparation/import must never open a PostgreSQL connection")
    # The runtime driver may already be imported by unrelated app tests; replace
    # only its import binding for this import-inertness assertion.
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=forbidden))
    for name in ("pg_contract_review.harness", "pg_contract_review.postgresql_contract_cases"):
        module = importlib.import_module(name)
        importlib.reload(module)
    assert calls == []


def test_dormant_python_sources_parse_and_case_filename_is_not_auto_discovered():
    directory = Path(__file__).resolve().parents[1]/"pg_contract_review"
    for path in directory.glob("*.py"):
        ast.parse(path.read_text(), filename=str(path))  # Python syntax only, never a SQL parser
    cases = directory/"postgresql_contract_cases.py"
    assert not cases.name.startswith("test_") and not cases.name.endswith("_test.py")
    assert not list(directory.glob("test_*.py"))
