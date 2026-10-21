from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import exchange_calendars as xcals

from .config import Settings
from .database import Database
from .market_data.http import JsonHttpClient


SCHEMA_VERSION = "R2D2-CASH-YIELD-v2"
METHODOLOGY_KEY = "r2d2_cash_yield_accounting"
METHODOLOGY_VERSION = 2
RATE_ANALYSIS_TYPE = "r2d2_cash_yield_rate"
RATE_ENTITY_KEY = "US_TBILL_13_WEEK_COUPON_EQUIVALENT"
RUN_ANALYSIS_TYPE = "r2d2_cash_yield_run"
RUN_ENTITY_KEY = "R2D2_CASH_YIELD"
SOURCE_NAME = "U.S. Department of the Treasury"
SOURCE_SERIES = "Daily Treasury Bill Rates / 13-week Coupon Equivalent"
TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)


class CashYieldDataError(RuntimeError):
    """A real data or integrity fault: the run raises and the phase fails."""


class CashYieldPendingData(CashYieldDataError):
    """An expected steady state of the frozen spec, never a failure.

    The spec keeps an entry ``pending`` while its source is absent ("fonte
    ausente ou stale => accrual pending ... nunca taxa fixa"), so these states
    are recorded on the run and retried by the next run; nothing is substituted.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


# Expected pending reasons (recorded, never raised out of a run).
PENDING_PRIOR_SNAPSHOT_MISSING = "prior_final_session_snapshot_missing"
PENDING_TREASURY_NOT_YET_PUBLISHED = "treasury_observation_not_yet_published"
PENDING_TREASURY_NOT_YET_CAUSAL = "treasury_observation_not_yet_causal"
# Treasury published later dates but none for the source date: a day the Treasury
# does not publish while XNYS trades (Columbus Day, Veterans Day). The frozen spec
# has no rule for it, so the entry stays pending until a deliberation decides one.
PENDING_TREASURY_OBSERVATION_ABSENT = "treasury_observation_absent_for_source_date"
INACTIVE_EXPERIMENT_STATUSES = frozenset({"paused", "completed"})
# "Not yet published" is only plausible for a few days; older than this it is a stale feed.
# Compared in UTC dates: safe because the phase runs 06:00–10:00 BRT (same UTC
# date); revisit if the schedule moves past 21:00 BRT.
TREASURY_STALE_AFTER = timedelta(days=4)


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {key: value for key, value in payload.items() if key != "payload_sha256"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _available_after_day(observation_date: date) -> datetime:
    return datetime.combine(
        observation_date.fromordinal(observation_date.toordinal() + 1),
        time.min,
        tzinfo=timezone.utc,
    )


def parse_treasury_bill_xml(
    xml_text: str,
    *,
    observation_date: date,
    fetched_at: datetime,
) -> dict[str, Any]:
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise CashYieldDataError("Treasury bill feed returned invalid XML") from exc

    matches: list[float] = []
    published_later = False
    dated_rows = 0
    for properties in root.iter():
        if not properties.tag.endswith("properties"):
            continue
        values = {
            child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
            for child in properties
        }
        raw_date = values.get("INDEX_DATE", "")[:10]
        try:
            row_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        dated_rows += 1
        if row_date != observation_date:
            published_later = published_later or row_date > observation_date
            continue
        try:
            rate = float(values["ROUND_B1_YIELD_13WK_2"]) / 100
        except (KeyError, ValueError) as exc:
            raise CashYieldDataError(
                "Treasury row lacks 13-week Coupon Equivalent"
            ) from exc
        if rate < 0:
            raise CashYieldDataError("Treasury 13-week Coupon Equivalent is negative")
        matches.append(rate)

    fetched_day = fetched_at.astimezone(timezone.utc).date()
    if not dated_rows and not (
        observation_date.month == 1
        and observation_date >= fetched_day - TREASURY_STALE_AFTER
    ):
        # An empty feed, a renamed INDEX_DATE or an XML error page: a broken source.
        # The feed is fetched per year, so early January may legitimately be empty
        # for up to the stale grace before it counts as broken.
        raise CashYieldDataError("Treasury feed has no dated rows")
    message = f"Expected one Treasury observation for {observation_date}, found {len(matches)}"
    if (
        not matches and not published_later
        and observation_date < fetched_day - TREASURY_STALE_AFTER
    ):
        # Nothing on or after the source date days later: the feed is stale, not late.
        raise CashYieldDataError(f"Treasury feed is stale: {message}")
    if not matches:
        raise CashYieldPendingData(
            PENDING_TREASURY_OBSERVATION_ABSENT
            if published_later else PENDING_TREASURY_NOT_YET_PUBLISHED,
            message,
        )
    if len(matches) != 1:
        raise CashYieldDataError(message)
    available_at = _available_after_day(observation_date)
    if available_at > fetched_at:
        raise CashYieldPendingData(
            PENDING_TREASURY_NOT_YET_CAUSAL,
            "Treasury observation is not yet causally available",
        )
    package: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE_NAME,
        "series": SOURCE_SERIES,
        "field": "ROUND_B1_YIELD_13WK_2",
        "field_label": "Coupon Equivalent",
        "excluded_field": "Bank Discount",
        "observation_date": observation_date.isoformat(),
        "annual_rate": matches[0],
        "day_count_convention": "ACT/365-or-366",
        "available_at": available_at.isoformat(),
        "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
    }
    package["payload_sha256"] = _canonical_sha256(package)
    return package


def coupon_equivalent_factor(annual_rate: float, start: date, end: date) -> float:
    if annual_rate < 0 or end <= start:
        raise ValueError("Cash-yield interval and rate must be positive")
    factor = 0.0
    cursor = start
    while cursor < end:
        next_year = date(cursor.year + 1, 1, 1)
        segment_end = min(end, next_year)
        days = (segment_end - cursor).days
        factor += annual_rate * days / (366 if calendar.isleap(cursor.year) else 365)
        cursor = segment_end
    return factor


class R2D2CashYieldService:
    """Post synthetic cash accrual without changing operational R2D2 cash or NAV."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        if not hasattr(database, "_r2d2_cash_yield_entries"):
            database._r2d2_cash_yield_entries = []  # type: ignore[attr-defined]

    def last_run_at(self) -> datetime | None:
        latest = self.database.latest_analysis_snapshot(RUN_ANALYSIS_TYPE, RUN_ENTITY_KEY)
        if not latest or (latest.get("outputs") or {}).get("status") == "partial":
            return None
        return latest["published_at"]

    def run_latest(self) -> dict[str, Any]:
        experiment = self._experiment()
        if self._inactive(experiment):
            return self._record_inactive(experiment)
        experiment_id = str(experiment["id"])
        snapshots = self._final_snapshots(experiment_id)
        eligible = [
            row for row in snapshots
            if row["session_date"] >= experiment["start_date"]
        ]
        if not eligible:
            return self._record_run({"status": "pending", "reason": "no_final_experiment_session"})
        return self.run_through(eligible[-1]["session_date"])

    def run_through(self, target_session: date) -> dict[str, Any]:
        calendar = xcals.get_calendar("XNYS")
        if not calendar.is_session(target_session):
            return self._record_run({
                "status": "skipped",
                "target_session": target_session.isoformat(),
                "reason": "target_is_not_a_us_equities_session",
            })

        experiment = self._experiment()
        if self._inactive(experiment):
            return self._record_inactive(experiment)
        experiment_id = str(experiment["id"])
        snapshots = self._final_snapshots(experiment_id)
        eligible = [
            row for row in snapshots
            if row["session_date"] >= experiment["start_date"]
            and row["session_date"] < target_session
        ]
        if not eligible:
            return self._record_run({"status": "pending", "reason": "no_prior_final_session"})

        snapshots_by_date = {row["session_date"]: row for row in eligible}
        first_target = calendar.next_session(eligible[0]["session_date"]).date()
        accruable = [
            {"session_date": value.date()}
            for value in calendar.sessions_in_range(first_target, target_session)
        ]
        missing = [
            row for row in accruable
            if self._entry(experiment_id, row["session_date"]) is None
        ]
        if not missing:
            current = accruable[-1]
            existing = self._entry(experiment_id, current["session_date"])
            return self._record_run({
                "status": "idempotent",
                "session_date": current["session_date"].isoformat(),
                "entry_sha256": existing["entry_sha256"],
            })

        posted: list[dict[str, Any]] = []
        pending: list[dict[str, str]] = []
        faults: list[dict[str, str]] = []
        xml_by_year: dict[int, str] = {}
        for current in missing:
            prior_session = calendar.previous_session(current["session_date"]).date()
            prior = snapshots_by_date.get(prior_session)
            if prior is None:
                pending.append({
                    "session_date": current["session_date"].isoformat(),
                    "source_observation_date": prior_session.isoformat(),
                    "reason": PENDING_PRIOR_SNAPSHOT_MISSING,
                })
                continue

            fetched_at = datetime.now(timezone.utc)
            year = prior["session_date"].year
            if year not in xml_by_year:
                xml_by_year[year] = self.http.get_text(
                    TREASURY_XML_URL,
                    params={
                        "data": "daily_treasury_bill_rates",
                        "field_tdr_date_value": str(year),
                    },
                )
            try:
                rate = self._refresh_rate(
                    prior["session_date"],
                    fetched_at=fetched_at,
                    xml_text=xml_by_year[year],
                )
            except CashYieldPendingData as exc:
                pending.append({
                    "session_date": current["session_date"].isoformat(),
                    "source_observation_date": prior["session_date"].isoformat(),
                    "reason": exc.reason,
                    "detail": str(exc),
                })
                continue
            except CashYieldDataError as exc:
                faults.append({
                    "session_date": current["session_date"].isoformat(),
                    "source_observation_date": prior["session_date"].isoformat(),
                    "reason": str(exc),
                })
                continue
            base_cash = max(float(prior["cash_usd"]), 0.0)
            factor = coupon_equivalent_factor(
                float(rate["annual_rate"]), prior["session_date"], current["session_date"]
            )
            entry: dict[str, Any] = {
                "id": str(uuid4()),
                "experiment_id": experiment_id,
                "session_date": current["session_date"],
                "prior_session_date": prior["session_date"],
                "base_cash_usd": round(base_cash, 6),
                "annual_coupon_equivalent_rate": float(rate["annual_rate"]),
                "calendar_days": (current["session_date"] - prior["session_date"]).days,
                "daily_factor": factor,
                "interest_income_usd": round(base_cash * factor, 6),
                "source_name": SOURCE_NAME,
                "source_series": SOURCE_SERIES,
                "source_observation_date": prior["session_date"],
                "source_available_at": datetime.fromisoformat(rate["available_at"]),
                "source_fetched_at": datetime.fromisoformat(rate["fetched_at"]),
                "source_payload_sha256": rate["payload_sha256"],
                "backfilled_at": fetched_at if current["session_date"] < fetched_at.date() else None,
            }
            entry["entry_sha256"] = _canonical_sha256({
                key: value.isoformat() if isinstance(value, (date, datetime)) else value
                for key, value in entry.items()
                if key != "id"
            })
            posted.append(self._insert_entry(entry))

        posted_dates = [row["session_date"].isoformat() for row in posted]
        if faults:
            # A real fault: every other session was still posted, then the phase fails.
            self._record_run({
                "status": "partial",
                "posted_count": len(posted),
                "posted_session_dates": posted_dates,
                "pending_count": len(pending),
                "pending_sessions": pending,
                "fault_count": len(faults),
                "fault_sessions": faults,
            })
            raise CashYieldDataError(
                "Cash-yield sessions failed on a data fault: "
                + ", ".join(row["session_date"] for row in faults)
            )
        if pending:
            # Expected steady state (spec: "fonte ausente => pending"): recorded, not raised.
            return self._record_run({
                "status": "pending_data",
                "target_session": target_session.isoformat(),
                "posted_count": len(posted),
                "posted_session_dates": posted_dates,
                "pending_count": len(pending),
                "pending_sessions": pending,
                "pending_reasons": sorted({row["reason"] for row in pending}),
                "entries_paused": bool(experiment.get("entries_paused")),
            })

        latest_session = accruable[-1]["session_date"]
        latest = self._entry(experiment_id, latest_session)
        if latest is None:
            raise CashYieldDataError("Latest cash-yield session was not persisted")
        return self._record_run({
            "status": "posted",
            "session_date": latest_session.isoformat(),
            "interest_income_usd": latest["interest_income_usd"],
            "entry_sha256": latest["entry_sha256"],
            "posted_count": len(posted),
            "posted_session_dates": posted_dates,
        })

    @staticmethod
    def _inactive(experiment: dict[str, Any]) -> bool:
        return str(experiment.get("status") or "running") in INACTIVE_EXPERIMENT_STATUSES

    def _record_inactive(self, experiment: dict[str, Any]) -> dict[str, Any]:
        # A paused or completed experiment accrues nothing new; if it resumes, the
        # oldest-first backfill posts every missed session from its own final snapshots.
        return self._record_run({
            "status": "idle",
            "reason": f"experiment_{experiment['status']}",
            "experiment_status": str(experiment["status"]),
        })

    def _refresh_rate(
        self,
        observation_date: date,
        *,
        fetched_at: datetime,
        xml_text: str,
    ) -> dict[str, Any]:
        package = parse_treasury_bill_xml(
            xml_text, observation_date=observation_date, fetched_at=fetched_at
        )
        methodology_id = self._methodology_id()
        self.database.save_analysis_snapshot(
            RATE_ANALYSIS_TYPE,
            RATE_ENTITY_KEY,
            methodology_id,
            {"observation_date": observation_date.isoformat()},
            package,
            fetched_at,
        )
        return package

    def _methodology_id(self) -> str:
        return self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {
                "schema_version": SCHEMA_VERSION,
                "tenor": "13-week",
                "field": "Coupon Equivalent",
                "operational_nav_influence": False,
                "strategy_influence": False,
            },
            "Synthetic cash accrual, isolated from R2D2 strategy and operational NAV.",
        )

    def _record_run(self, result: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        payload = {"schema_version": SCHEMA_VERSION, "recorded_at": now.isoformat(), **result}
        payload["payload_sha256"] = _canonical_sha256(payload)
        self.database.save_analysis_snapshot(
            RUN_ANALYSIS_TYPE,
            RUN_ENTITY_KEY,
            self._methodology_id(),
            {"experiment_code": self.settings.r2d2_experiment_code},
            payload,
            now,
        )
        return payload

    def _experiment(self) -> dict[str, Any]:
        if not self.database.database_url:
            experiment = getattr(self.database, "_r2d2_memory", {}).get("experiment")
            if experiment:
                return dict(experiment)
        else:
            with self.database.connection() as connection:
                row = connection.execute(
                    """SELECT id::text, code, start_date, status, entries_paused
                       FROM r2d2_experiments WHERE code=%s""",
                    (self.settings.r2d2_experiment_code,),
                ).fetchone()
            if row:
                return {
                    "id": row[0], "code": row[1], "start_date": row[2],
                    "status": row[3], "entries_paused": bool(row[4]),
                }
        raise CashYieldDataError("R2D2 experiment is not initialized")

    def _final_snapshots(self, experiment_id: str) -> list[dict[str, Any]]:
        if not self.database.database_url:
            snapshots = getattr(self.database, "_r2d2_memory", {}).get("snapshots", {})
            return [
                dict(item) for _, item in sorted(snapshots.items()) if item.get("is_final")
            ]
        with self.database.connection() as connection:
            rows = connection.execute(
                """SELECT session_date, cash_usd FROM r2d2_daily_snapshots
                   WHERE experiment_id=%s AND is_final=TRUE ORDER BY session_date""",
                (experiment_id,),
            ).fetchall()
        return [{"session_date": row[0], "cash_usd": row[1], "is_final": True} for row in rows]

    def _entry(self, experiment_id: str, session_date: date) -> dict[str, Any] | None:
        if not self.database.database_url:
            return next((
                dict(item)
                for item in self.database._r2d2_cash_yield_entries  # type: ignore[attr-defined]
                if item["experiment_id"] == experiment_id and item["session_date"] == session_date
            ), None)
        with self.database.connection() as connection:
            row = connection.execute(
                """SELECT interest_income_usd, entry_sha256 FROM r2d2_cash_yield_ledger
                   WHERE experiment_id=%s AND session_date=%s""",
                (experiment_id, session_date),
            ).fetchone()
        return {"interest_income_usd": float(row[0]), "entry_sha256": row[1]} if row else None

    def _insert_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        if not self.database.database_url:
            self.database._r2d2_cash_yield_entries.append(dict(entry))  # type: ignore[attr-defined]
            return entry
        with self.database.connection() as connection:
            row = connection.execute(
                """INSERT INTO r2d2_cash_yield_ledger
                   (id, experiment_id, session_date, prior_session_date, base_cash_usd,
                    annual_coupon_equivalent_rate, calendar_days, daily_factor,
                    interest_income_usd, source_name, source_series, source_observation_date,
                    source_available_at, source_fetched_at, source_payload_sha256,
                    entry_sha256, backfilled_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (experiment_id, session_date) DO NOTHING
                   RETURNING interest_income_usd, entry_sha256""",
                (
                    entry["id"], entry["experiment_id"], entry["session_date"],
                    entry["prior_session_date"], entry["base_cash_usd"],
                    entry["annual_coupon_equivalent_rate"], entry["calendar_days"],
                    entry["daily_factor"], entry["interest_income_usd"],
                    entry["source_name"], entry["source_series"],
                    entry["source_observation_date"], entry["source_available_at"],
                    entry["source_fetched_at"], entry["source_payload_sha256"],
                    entry["entry_sha256"], entry["backfilled_at"],
                ),
            ).fetchone()
            connection.commit()
        if row:
            return {**entry, "interest_income_usd": float(row[0]), "entry_sha256": row[1]}
        existing = self._entry(entry["experiment_id"], entry["session_date"])
        if not existing or existing["entry_sha256"] != entry["entry_sha256"]:
            raise CashYieldDataError("Existing cash-yield entry does not match the canonical entry")
        return {**entry, **existing}
