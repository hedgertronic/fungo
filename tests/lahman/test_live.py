"""Live network smoke test for the Lahman module (deselected by default;
`-m live`).

Three requests total (SABR page, Box folder pages, one small table). Proves
the load-bearing assumptions: the SABR page still carries a comma-delimited
Box link, the Box folder JSON still parses, and the shared-file download
route still serves CSV. The cache is redirected to a tmp dir so the run
always exercises the network and never pollutes ~/.cache/fungo/lahman.
"""

from __future__ import annotations

import pytest

from fungo.lahman import tables as tables_mod


@pytest.mark.live
def test_parks_table_downloads_and_parses(monkeypatch, tmp_path):
    monkeypatch.setattr(tables_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tables_mod, "_INDEX", None)

    tables = tables_mod.list_tables()
    assert "People" in tables
    assert "Batting" in tables

    rows = tables_mod.get_table("Parks")  # one of the smallest tables
    assert rows
    assert "parkkey" in rows[0]
    assert all(isinstance(v, str) for v in rows[0].values())
