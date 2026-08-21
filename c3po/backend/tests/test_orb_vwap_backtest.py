from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "r2d2_orb_vwap_backtest.py"
SPEC = spec_from_file_location("r2d2_orb_vwap_backtest", SCRIPT)
module = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def bar(at, open_, high, low, close, volume=1_000):
    return {"timestamp": at, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def opening_bars():
    start = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    return [bar(start + timedelta(minutes=i), 100, 100.10, 99.90, 100, 1_000) for i in range(15)]


def test_candidate_f_accepts_first_unextended_breakout_above_vwap():
    bars = opening_bars()
    bars.append(bar(datetime(2026, 8, 20, 13, 45, tzinfo=timezone.utc), 100, 100.15, 99.98, 100.12, 2_000))
    signal = module.candidate_f_signal(bars, 15)
    assert signal is not None
    assert signal.route == "F_ORB_VWAP"
    assert signal.stop < signal.entry


def test_candidate_f_rejects_breakout_extended_beyond_half_or_range():
    bars = opening_bars()
    bars.append(bar(datetime(2026, 8, 20, 13, 45, tzinfo=timezone.utc), 100, 100.40, 99.98, 100.30, 2_000))
    assert module.candidate_f_signal(bars, 15) is None


def test_candidate_f_rejects_price_that_never_crossed_or_high():
    bars = opening_bars()
    bars.append(bar(datetime(2026, 8, 20, 13, 45, tzinfo=timezone.utc), 100, 100.09, 99.98, 100.05, 2_000))
    assert module.candidate_f_signal(bars, 15) is None
