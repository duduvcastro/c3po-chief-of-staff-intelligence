"""Pure validation of an explicit, local disposable-database review descriptor."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import UUID

SCHEMA = "FULL-UNIVERSE-LOCAL-PG-REVIEW-PLAN-v1"
PROPOSED_USERS = {"legacy": "c3po", "publisher": "c3po_full_universe_publisher", "operator": "c3po_full_universe_operator"}
KEYS = {"schema", "database", "database_nonce", "socket_directory", "port", "server_system_identifier", "ddl_sha256",
        "users", "password_env"}


class PreconditionError(ValueError):
    pass


def assert_no_ambient_libpq(environment: Mapping[str, str]) -> None:
    if any(key.startswith("PG") for key in environment):
        raise PreconditionError("clear ambient PG* overrides before an explicit disposable review connection")


@dataclass(frozen=True)
class ReviewPlan:
    database: str
    database_nonce: str
    socket_directory: str
    port: int
    server_system_identifier: str
    ddl_sha256: str
    users: dict[str, str]
    password_env: dict[str, str | None]

    @property
    def database_comment(self) -> str:
        return "c3po-full-universe-disposable-review:" + self.database_nonce

    def connection_kwargs(self, actor: str, environment: Mapping[str, str]) -> dict[str, Any]:
        if actor not in self.users:
            raise PreconditionError("unknown review actor")
        reference = self.password_env[actor]
        if reference is not None and reference not in environment:
            raise PreconditionError("explicit review password environment reference is unset")
        return {"host": self.socket_directory, "port": self.port, "dbname": self.database, "user": self.users[actor],
                "password": environment[reference] if reference is not None else "", "passfile": "/dev/null",
                "sslmode": "disable", "connect_timeout": 5,
                "options": "-c search_path=pg_catalog,public -c statement_timeout=15000", "autocommit": True}


def parse_plan(value: Any) -> ReviewPlan:
    if not isinstance(value, Mapping) or set(value) != KEYS or value.get("schema") != SCHEMA:
        raise PreconditionError("the complete explicit review descriptor is required")
    database = value["database"]
    if not isinstance(database, str) or not re.fullmatch(r"c3po_fu_review_[a-f0-9]{32}", database):
        raise PreconditionError("only a fresh c3po_fu_review_<32 hex> disposable database is accepted")
    try:
        nonce = str(UUID(value["database_nonce"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PreconditionError("a real externally recorded disposable database nonce is required") from exc
    socket = value["socket_directory"]
    if (not isinstance(socket, str) or not Path(socket).is_absolute() or not socket.startswith(("/private/tmp/", "/tmp/"))
            or any(part in {".", ".."} for part in socket.split("/")) or any(item in socket for item in [",", "\x00", "\n"])):
        raise PreconditionError("only an explicit private /tmp Unix socket directory is accepted; no TCP or default host")
    port = value["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise PreconditionError("an explicit verified test-cluster port is required")
    identifier = value["server_system_identifier"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", identifier):
        raise PreconditionError("the actual test-cluster system identifier must be supplied, never guessed")
    ddl_sha = value["ddl_sha256"]
    if not isinstance(ddl_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", ddl_sha):
        raise PreconditionError("the reviewed dormant DDL digest is required")
    users, passwords = value["users"], value["password_env"]
    actors = {"schema_admin", *PROPOSED_USERS}
    if not isinstance(users, Mapping) or not isinstance(passwords, Mapping) or set(users) != actors or set(passwords) != actors:
        raise PreconditionError("all proposed actor identities and explicit password references are required")
    if (not all(isinstance(item, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", item) for item in users.values())
            or len(set(users.values())) != 4 or users["schema_admin"] == "c3po_full_universe_owner"
            or any(users[key] != proposed for key, proposed in PROPOSED_USERS.items())):
        raise PreconditionError("actual separate actor identities must match the proposed role contract")
    if not all(item is None or isinstance(item, str) and re.fullmatch(r"FU_PG_REVIEW_[A-Z_]+", item) for item in passwords.values()):
        raise PreconditionError("only explicit FU_PG_REVIEW password references are accepted; no normal PG/app fallback")
    return ReviewPlan(database, nonce, socket, port, identifier, ddl_sha, dict(users), dict(passwords))


def load_plan(path: Path, ddl_path: Path) -> ReviewPlan:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536 or path.stat().st_mode & 0o077:
        raise PreconditionError("review descriptor must be an ordinary private 0600 file, not a symlink")
    plan = parse_plan(json.loads(path.read_text()))
    if hashlib.sha256(ddl_path.read_bytes()).hexdigest() != plan.ddl_sha256:
        raise PreconditionError("the local dormant DDL differs from the explicitly reviewed digest")
    return plan
