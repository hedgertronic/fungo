"""fungo — tools for acquiring baseball data from Statcast, the MLB Stats API,
FanGraphs, Baseball-Reference, Retrosheet, the Lahman database, and the
Chadwick player-ID register.

The core returns raw ``list[dict]`` / ``dict`` — no DataFrame dependency.
Wrap results in whatever frame library you use: ``pl.DataFrame(rows)`` or
``pd.DataFrame(rows)`` both accept fungo output directly.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fungo import bbref, constants, fangraphs, lahman, lookup, mlb, retrosheet, statcast
from fungo.exceptions import (
    BBRefError,
    FangraphsError,
    FungoError,
    LahmanError,
    MLBStatsError,
    RequestError,
    SavantError,
    StaleCacheWarning,
    ValidationError,
)

try:
    __version__ = version("fungo")
except PackageNotFoundError:  # pragma: no cover - source tree fallback
    __version__ = "2.0.0"

# Subpackages are the primary surface: `fungo.statcast.search_pitches(...)`,
# `fungo.mlb.get_schedule(...)`, `fungo.lookup.lookup(...)`. The names below
# are the small cross-cutting top level — exceptions and the shared resolvers.
# Per-domain functions stay under their subpackage to avoid collisions (both
# statcast and mlb define PITCH_TYPES, etc.).
__all__ = [
    "BBRefError",
    "FangraphsError",
    "FungoError",
    "LahmanError",
    "MLBStatsError",
    "RequestError",
    "SavantError",
    "StaleCacheWarning",
    "ValidationError",
    "__version__",
    "bbref",
    "constants",
    "fangraphs",
    "lahman",
    "lookup",
    "mlb",
    "retrosheet",
    "statcast",
]
