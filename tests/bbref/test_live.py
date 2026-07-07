"""Live network smoke test for Baseball-Reference (deselected by default).

ONE page request, through the shared rate limiter. Proves the comment-aware
table extraction against the real page (mix of live and commented tables).
Run sparingly: `uv run pytest tests/bbref/test_live.py -m live`.
"""

from __future__ import annotations

import pytest

from fungo import bbref


@pytest.mark.live
def test_player_page_extracts_live_and_commented_tables():
    out = bbref.get_player("troutmi01")
    # Live table on the current page layout.
    assert "players_standard_batting" in out
    assert any(r.get("year_id") == "2012" for r in out["players_standard_batting"])
    # Comment-deferred table — proves the uncomment-then-parse strategy.
    assert "br-salaries" in out
