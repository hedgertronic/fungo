"""Live network smoke tests for FanGraphs (deselected by default; `-m live`).

Two requests total. Proves the load-bearing assumptions: the okhttp UA still
clears Cloudflare, the leaders API returns Stuff+/PitchingBot columns, and the
guts.aspx HTML table still parses.
"""

from __future__ import annotations

import pytest

from fungo import fangraphs as fg


@pytest.mark.live
def test_pitching_leaders_include_stuff_plus():
    rows = fg.get_leaders("pit", 2025, qual="y", page_items=3)
    assert rows
    row = rows[0]
    assert "playerid" in row and "xMLBAMID" in row
    assert "sp_stuff" in row  # Stuff+
    assert "pb_overall" in row  # PitchingBot


@pytest.mark.live
def test_guts_constants_parse():
    rows = fg.get_guts_constants()
    assert rows
    assert rows[0]["Season"].isdigit()
    assert "wOBA" in rows[0]
