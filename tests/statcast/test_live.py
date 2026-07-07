"""Live network smoke test (deselected by default; run with `-m live`).

Checks ``year_format`` against real Baseball Savant: the bat-tracking board
ignores `year=` and needs seasonStart/seasonEnd. A passing run returns non-empty
2024 rows.
"""

from __future__ import annotations

import pytest

from fungo.statcast import leaderboards as lb


@pytest.mark.live
def test_bat_tracking_2024_returns_rows():
    rows = lb.get_bat_tracking(2024, min_swings="q")
    assert len(rows) > 0
    # camelCase season params return real data, not an empty/current-season page.
    assert "avg_bat_speed" in rows[0] or "swing_length" in rows[0]


@pytest.mark.live
@pytest.mark.parametrize(
    "view", ["batter", "batting-team", "pitcher", "pitching-team", "league"]
)
def test_bat_tracking_all_type_views_return_rows(view):
    # All five Savant `type` views must return data (team views ~30 rows, league 1).
    rows = lb.get_bat_tracking(2024, type=view, min_swings="q")
    assert len(rows) > 0


@pytest.mark.live
def test_bat_tracking_multi_year_range_aggregates_per_player():
    # camelCase seasonStart != seasonEnd is a contiguous RANGE: one aggregated row
    # per player across the span, with NO year column.
    rng = lb.get_bat_tracking((2023, 2025), type="batter", min_swings="q")
    assert len(rng) > 0
    assert "year" not in rng[0]


@pytest.mark.live
def test_swing_timing_miss_distance_multi_year_array_is_per_year():
    # season[] is a true multi-select: one row per player PER year.
    rows = lb.get_swing_timing_miss_distance([2023, 2024], type="batter", min="q")
    assert len(rows) > 0
    assert "miss_distance" in rows[0]
    years = {r.get("year") for r in rows}
    assert years == {"2023", "2024"}
