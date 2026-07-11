"""Live network tests for fungo.retrosheet (deselected by default).

Run with ``uv run pytest -m live tests/retrosheet``. One small file (the
~0.5 MB 2024 game-log zip) is fetched from Retrosheet's static host; the
cache is redirected to a tmp dir so the real ~/.cache/fungo/retrosheet is
never touched.
"""

from __future__ import annotations

import pytest

from fungo import retrosheet
from fungo.retrosheet import files as files_mod


@pytest.mark.live
def test_get_game_logs_live(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)

    rows = retrosheet.get_game_logs(2024)

    # A full modern season has ~2,430 games (2024 shipped 2,429 rows).
    assert len(rows) > 2400
    assert list(rows[0]) == list(retrosheet.GAME_LOG_FIELDS)
    assert rows[0]["date"].startswith("2024")
    assert rows[0]["acquisition_info"] in {"Y", "N", "D", "P"}
