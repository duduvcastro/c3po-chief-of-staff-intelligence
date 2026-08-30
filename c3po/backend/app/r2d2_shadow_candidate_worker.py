from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import get_settings
from .database import Database
from .observability import init_sentry
from .r2d2 import R2D2Repository
from .r2d2_shadow_candidate_log import R2D2ShadowCandidateLog
from .r2d2_shadow_candidate_outcomes import run_session, session_is_closed


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def run_due_sessions(database: Database, *, now: datetime | None = None) -> list[dict[str, object]]:
    settings = get_settings()
    if not settings.r2d2_shadow_candidate_outcomes_enabled:
        return []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    repository = R2D2Repository(database)
    experiment = repository.experiment(settings.r2d2_experiment_code)
    if experiment is None:
        return []
    store = R2D2ShadowCandidateLog(database)
    summaries: list[dict[str, object]] = []
    for session_date in store.pending_sessions(str(experiment["id"])):
        if not session_is_closed(session_date, now):
            continue
        output = settings.r2d2_shadow_candidate_evidence_dir / f"session_date={session_date.isoformat()}"
        summaries.append(run_session(
            settings=settings,
            database=database,
            session_date=session_date,
            output=output,
            generated_at=now,
        ))
    return summaries


def main() -> None:
    settings = get_settings()
    init_sentry(settings, service_name="r2d2-shadow-candidate-worker")
    database = Database(settings)
    database.initialize()
    logger.info(
        "R2D2 shadow-candidate nightly worker ready; enabled=%s evidence=%s",
        settings.r2d2_shadow_candidate_outcomes_enabled,
        settings.r2d2_shadow_candidate_evidence_dir,
    )
    while True:
        try:
            local_hour = datetime.now(timezone.utc).astimezone(SAO_PAULO).hour
            if 0 <= local_hour < 8:
                for summary in run_due_sessions(database):
                    logger.info("R2D2 shadow-candidate report completed: %s", summary)
        except Exception:
            logger.exception("R2D2 shadow-candidate nightly run failed")
        time.sleep(60)


if __name__ == "__main__":
    main()
