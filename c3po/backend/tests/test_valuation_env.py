"""The SEC contact and pace and the as-filed/decisor switches are read from the environment (``app/valuation_env.py``),
never from ``Settings``: ``config.py`` is hashed into the R2D2 V2 implementation package, and the Settings fields first
added for them moved ``implementation_package_sha`` — on deploy the R2D2 V2 shadow collector refuses the build
(``COLLECTOR_IMPLEMENTATION_PACKAGE_MISMATCH``) and the capacity bootstrap fails (``CAPACITY_CONFIG_PACKAGE``)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import sec_xbrl, valuation_env
from app.config import Settings
from app.r2d2_v2_earnings_package import PACKAGE_FILES, implementation_package_sha

APP = Path(__file__).resolve().parents[1] / "app"
FORMER_SETTINGS_FIELDS = ("sec_contact", "sec_max_requests_per_second", "valuation_asfiled_enabled", "valuation_asfiled_backfill_issuers_per_poll",
                          "valuation_decisor_shadow")


def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in valuation_env.ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_nothing_ships_enabled_or_with_a_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean(monkeypatch)
    assert valuation_env.sec_contact() == "" and valuation_env.sec_max_requests_per_second() == 2.5
    assert valuation_env.asfiled_enabled() is False and valuation_env.decisor_shadow_enabled() is False
    assert valuation_env.asfiled_backfill_issuers_per_poll() == 10
    # three processes call EDGAR (API, IR worker, valuation worker): the default keeps the host under the 8/s ceiling
    assert 3 * valuation_env.sec_max_requests_per_second() <= sec_xbrl.SEC_FAIR_ACCESS_MAX_PER_SECOND


def test_values_parse_into_their_ranges_and_an_unparseable_one_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean(monkeypatch)
    monkeypatch.setenv(valuation_env.SEC_CONTACT_ENV, "  C3PO test desk  ")
    assert valuation_env.sec_contact() == "C3PO test desk"
    for raw, rate in (("3", 3.0), (" 1.5 ", 1.5), ("8", 8.0), ("50", 8.0), ("0", 2.5), ("-1", 2.5), ("nan", 2.5), ("inf", 2.5), ("fast", 2.5), ("", 2.5)):
        monkeypatch.setenv(valuation_env.SEC_MAX_REQUESTS_PER_SECOND_ENV, raw)
        assert valuation_env.sec_max_requests_per_second() == rate, raw
    for raw, count in (("25", 25), ("0", 0), ("-3", 0), ("999", 200), ("7.5", 10), ("many", 10), ("", 10)):
        monkeypatch.setenv(valuation_env.ASFILED_BACKFILL_ENV, raw)
        assert valuation_env.asfiled_backfill_issuers_per_poll() == count, raw
    for name, read in ((valuation_env.ASFILED_ENABLED_ENV, valuation_env.asfiled_enabled), (valuation_env.DECISOR_SHADOW_ENV, valuation_env.decisor_shadow_enabled)):
        for raw in ("true", "TRUE", " True ", "1", "yes", "on", "t", "y"):
            monkeypatch.setenv(name, raw)
            assert read() is True, (name, raw)
        for raw in ("", "false", "0", "no", "off", "enabled", "2"):
            monkeypatch.setenv(name, raw)
            assert read() is False, (name, raw)


def test_config_declares_none_of_them_so_the_r2d2_v2_package_does_not_move(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "config.py" in PACKAGE_FILES and "valuation_env.py" not in PACKAGE_FILES
    assert not set(FORMER_SETTINGS_FIELDS) & set(Settings.model_fields)
    source = (APP / "config.py").read_text(encoding="utf-8")
    for name in (*valuation_env.ENVIRONMENT_NAMES, *FORMER_SETTINGS_FIELDS):
        assert name not in source, name
    # the values are read at call time from the environment: setting every one of them leaves the package hash alone
    _clean(monkeypatch)
    before = implementation_package_sha()
    for name, value in ((valuation_env.SEC_CONTACT_ENV, "C3PO test desk"), (valuation_env.SEC_MAX_REQUESTS_PER_SECOND_ENV, "3"),
                        (valuation_env.ASFILED_ENABLED_ENV, "true"), (valuation_env.ASFILED_BACKFILL_ENV, "5"), (valuation_env.DECISOR_SHADOW_ENV, "true")):
        monkeypatch.setenv(name, value)
    assert implementation_package_sha() == before
    assert "C3PO test desk" not in repr(Settings())  # a Settings object never carries the contact


def test_every_switch_starts_from_its_default_in_the_test_session() -> None:
    # conftest.py clears each name before any import: a shell or container that exports one never leaks into the suite
    conftest = (Path(__file__).resolve().parent / "conftest.py").read_text(encoding="utf-8")
    for name in valuation_env.ENVIRONMENT_NAMES:
        assert f'os.environ["{name}"] = ""' in conftest, name
