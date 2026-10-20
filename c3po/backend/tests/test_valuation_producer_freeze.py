"""The US point-in-time backtest hashes its producer files (``valuation_pit_rerun.IMPLEMENTATION_FILES`` and the frozen
producer list of the week of 19/10) and refuses to run when one of them moves. The decisor branch must not touch them:
their bytes are pinned here at the release of 19/10 (origin/main 42f4280). A legitimate change to any of them belongs to
the backtest's own revision, which updates this list with it."""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.valuation_pit_rerun import IMPLEMENTATION_FILES

APP = Path(__file__).resolve().parents[1] / "app"
FROZEN = {
    "market_data/eodhd.py": "94c2aab73e660b9d6b7d3775f5342766485776205b59c4d4742c10a72a72c8ed",
    "market_data/models.py": "57aa53f06defe58b9ba82a0da8ea1b6e275d82a589aa77ba11fe76e4ba080978",
    "market_data/us_screener.py": "797989558522449aeee35174b20421476fae9f6b720c9a6e995935cdcd133f32",
    "one_pager.py": "76e8cc35fcd03be591280ff1bfbf76e0eb48495019fbe0484ead4231118a2ca4",
    "sec_xbrl.py": "42d5f04232995eb30b7b7b36f6c4ef809e672076ea921c174b0e91f7a21c538c",
    "statement_vintages.py": "ca6537b08a3cbd00765e71bae5bc4b26295a74af2082568e34b5a89a5eb4ace9",
    "valuation_asfiled.py": "6b0d2fa2f0b1e9934bc5569a07dd5920a99b1ae34aa299906d43054770ae41a4",
    "valuation_official.py": "fde3b7a15c1b97e2a014b09dc915df2ec65272b53222a3689559a9ddcda99f02",
    "valuation_official_engine.py": "64230c9f08f891f9c7531359925b161584f15d61d6f20c0970582a1e96ae83fe",
    "valuation_pit_rerun.py": "13ea6b01e695459c992a57f4f0da5dbec1767c62bb7d298fd792230761ac46f7",
    "valuation_price_history.py": "df057f2aafd7ca219df11e2979a32cf3965400047a583d33cc00d1a7d64ea011",
    "valuation_v2_engine.py": "7814f4d139459284ffafcb3a0c15fe50c128a2ae7047e87f377d6f6cab28418d",
    "valuation_v3_ab.py": "0aaa48ee47212016f21a693e618757ec93ba1c1eb3ba03f9b75055b94fa75721",
    "valuation_v3_engine.py": "f4eff56aff449f747e695fa81f73e4cc544cefba142d9d5c6473318e12ad0327",
    "valuation_v3_inputs.py": "c052fcadba507b1dd1475eae40ee28f82da7a84c24de945bc7635a145ae71ba9",
    "valuation_v3_macro.py": "c5e518d9466d22228ca6fa6ed288fb03c57915cb314df1fd47dc45390f3df647",
    "valuation_v3_shadow.py": "3ea257f47924ce669e52c660605a68dde33042a6837f7ff0e5ea8eaec0ae2669",
}


def test_the_backtest_producer_files_are_byte_identical_to_the_release() -> None:
    assert set(IMPLEMENTATION_FILES) <= set(FROZEN), "a file the backtest hashes is missing from the frozen list"
    assert {path.relative_to(APP).as_posix() for path in [*APP.glob("valuation_official*.py"), *APP.glob("valuation_v3_*.py")]} <= set(FROZEN)
    for name, digest in FROZEN.items():
        assert hashlib.sha256((APP / name).read_bytes()).hexdigest() == digest, f"{name} moved: the US PIT backtest would refuse to run"
