"""The freeze of the week of 19/10/2026: the US point-in-time backtest grid refuses any change to the code it reads. The
ACCEPTED producer is PR #456 (``fable/val-pit-served-tp`` at 739b215, merged here): its V3 producer
(``valuation_pit_rerun.IMPLEMENTATION_FILES``) and its served producer (``valuation_pit_served.IMPLEMENTATION_FILES``, the
thirteen files of PREREG_VALUATION_PIT_BACKTEST_US_V1 §1-bis.10) — seventeen files in all — stay byte-identical to the
state of that merge (sha256 below: ``valuation_pit_served.py``, ``valuation_pit_rerun.py`` and ``valuation_v3_macro.py`` as
739b215 has them; the others as main 42f4280 has them, which #456 does not change), and the served producer's identity
(files AND the nine ``Database`` reader methods, ``engine_sha256``) is pinned too. Also pinned: ``config.py`` and the R2D2
V2 implementation package (every ``PACKAGE_FILES`` byte, through ``implementation_package_sha``), the R2D2 V2 risk
differential's auxiliary ``official_fundamentals.py``, and the PREREG_VALUATION_DECISOR_V1 §17 modules.

A failure here means a change reached a frozen file. Revert it; lifting the freeze is the owner's decision, made in a PR
that changes this list on purpose — never as a side effect."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.r2d2_v2_earnings_package import implementation_package_sha

BACKEND = Path(__file__).resolve().parents[1]
FREEZE_REVISION = "42f4280 + 739b215 (PR #456) + the P1 lock (main 7f14740, PREREG rev 3)"
FROZEN: dict[str, str | None] = {
    "app/market_data/eodhd.py": "94c2aab73e660b9d6b7d3775f5342766485776205b59c4d4742c10a72a72c8ed",
    "app/market_data/models.py": "57aa53f06defe58b9ba82a0da8ea1b6e275d82a589aa77ba11fe76e4ba080978",
    "app/market_data/us_screener.py": "797989558522449aeee35174b20421476fae9f6b720c9a6e995935cdcd133f32",
    "app/one_pager.py": "76e8cc35fcd03be591280ff1bfbf76e0eb48495019fbe0484ead4231118a2ca4",
    "app/sec_xbrl.py": "42d5f04232995eb30b7b7b36f6c4ef809e672076ea921c174b0e91f7a21c538c",
    "app/statement_vintages.py": "ca6537b08a3cbd00765e71bae5bc4b26295a74af2082568e34b5a89a5eb4ace9",
    "app/valuation_asfiled.py": "6b0d2fa2f0b1e9934bc5569a07dd5920a99b1ae34aa299906d43054770ae41a4",
    "app/valuation_official.py": "3451b954a6cbc800db0051e7e341bf4a4f72e1254a7bc40d4c695c42d7e606ce",  # P1 lock (4652f34, 8b34659; PREREG rev 3 7f14740)
    "app/valuation_official_engine.py": "64230c9f08f891f9c7531359925b161584f15d61d6f20c0970582a1e96ae83fe",
    "app/valuation_pit_rerun.py": "609cda399e0b2d23243c35d594f5c7e0b591de26c97f09ff25271ad3ba6f3e8b",  # 739b215
    "app/valuation_pit_served.py": "3aa8e0954e4f6722b17bd08eba6335bd2b2dbb7d4df3a8e142cc554dd022bac1",  # 739b215
    "app/valuation_price_history.py": "df057f2aafd7ca219df11e2979a32cf3965400047a583d33cc00d1a7d64ea011",
    "app/valuation_v2_engine.py": "7814f4d139459284ffafcb3a0c15fe50c128a2ae7047e87f377d6f6cab28418d",
    "app/valuation_v3_engine.py": "f4eff56aff449f747e695fa81f73e4cc544cefba142d9d5c6473318e12ad0327",
    "app/valuation_v3_inputs.py": "c052fcadba507b1dd1475eae40ee28f82da7a84c24de945bc7635a145ae71ba9",
    "app/valuation_v3_macro.py": "c9edfaeea80c01d9ac3a2424c5b43a878bd28711ca378fcb491e0380d709545c",  # 739b215
    "app/valuation_v3_shadow.py": "3ea257f47924ce669e52c660605a68dde33042a6837f7ff0e5ea8eaec0ae2669",
    # untouched by the valuation fronts this week: hashed into the R2D2 V2 package / the risk differential / §17
    "app/config.py": "91619929a513074f2eee01a6bcd78342305e0066e61ac79f2afd087c2e035897",
    "app/official_fundamentals.py": "b6edf7903931ce781735bc1c80d3c9ee865d6b4a8cd1f414589f8e6c23e27ff5",
    "app/valuation_accuracy_report.py": "3388d3221535b768e68a68e8cdec83914e8d3e3084b8a4eb32256366341f040e",
    "app/valuation_panel.py": "cfebdd986876bd5d2929a4cda6de335e1634ea60cb10c632fa7dee997f883e16",
}
R2D2_V2_IMPLEMENTATION_PACKAGE_SHA = "43db2b969fe113594fafe4a9e0cabec1f80ada9f8ab9ee5852677d65e2ec716a"
SERVED_PRODUCER_ENGINE_SHA256 = "fbadbd374e31bff77e02e68bf5e9b7fc9a9542c7934946629ca2452bae43f7f2"  # files + the nine Database readers


@pytest.mark.parametrize("path", sorted(FROZEN))
def test_a_frozen_file_is_byte_identical_to_the_freeze_revision(path: str) -> None:
    target = BACKEND / path
    expected = FROZEN[path]
    if expected is None:
        assert not target.exists(), f"{path} did not exist at {FREEZE_REVISION}: it may not appear during the freeze"
        return
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    assert actual == expected, f"{path} changed since {FREEZE_REVISION} (sha256 {actual}): the US PIT backtest grid refuses it — revert"


def test_the_r2d2_v2_implementation_package_did_not_move() -> None:
    assert implementation_package_sha() == R2D2_V2_IMPLEMENTATION_PACKAGE_SHA


def test_every_file_of_both_pit_producers_is_frozen() -> None:
    from app import valuation_pit_rerun, valuation_pit_served

    producers = {f"app/{name}" for name in (*valuation_pit_rerun.IMPLEMENTATION_FILES, *valuation_pit_served.IMPLEMENTATION_FILES)}
    assert len(valuation_pit_served.IMPLEMENTATION_FILES) == 13 and len(producers) == 17
    assert producers <= {path for path, digest in FROZEN.items() if digest is not None}


def test_the_served_producer_identity_did_not_move() -> None:
    from app import valuation_pit_served

    assert valuation_pit_served.producer()["engine_sha256"] == SERVED_PRODUCER_ENGINE_SHA256
