"""Causal, research-only replay harness for the Day D experiment.

The package is deliberately isolated from the live R2D2 worker. Importing it
does not start a worker, read production state or change trading behavior.
"""

from .engine import (
    DayDReplayHarness,
    ReplayDataset,
    ReplayEntryAudit,
    ReplayMatrixResult,
    ReplayResult,
)
from .models import CostScenario, RunMode

__all__ = [
    "CostScenario",
    "DayDReplayHarness",
    "ReplayDataset",
    "ReplayEntryAudit",
    "ReplayMatrixResult",
    "ReplayResult",
    "RunMode",
]
