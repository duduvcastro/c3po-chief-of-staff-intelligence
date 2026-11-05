from pathlib import Path

import pytest

from .plan import load_plan


def pytest_addoption(parser):
    parser.addoption("--full-universe-pg-plan", action="store", default=None,
                     help="Explicit 0600 descriptor for a verified local disposable PostgreSQL cluster; never a production DSN")


@pytest.fixture(scope="session")
def review_harness(request):
    descriptor = request.config.getoption("--full-universe-pg-plan")
    if descriptor is None:
        pytest.skip("dormant integration cases require an explicit verified disposable-database descriptor")
    from .harness import ReviewHarness
    ddl = Path(__file__).resolve().parents[2]/"deployment/full-universe/ownership.review.sql"
    plan = load_plan(Path(descriptor), ddl)
    harness = ReviewHarness(plan, ddl)
    harness.preflight()
    yield harness
    harness.close()
