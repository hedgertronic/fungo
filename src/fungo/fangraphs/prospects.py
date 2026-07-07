"""THE BOARD — FanGraphs prospect rankings and scouting grades.

One JSON endpoint serves the whole board: ~1,300 prospects per season with
future value (``cFV``), risk, ETA, org rank, position-player tool grades
(``Hit``/``Game``/``Raw``/``Spd``/``Fld``/``Arm``) and pitch grades
(``FB``/``SL``/``CB``/``CH``/``SPL``/``CT``/``CMD``) plus velo/spin.
"""

from __future__ import annotations

from typing import Any

from fungo.fangraphs.api import fg_json

#####################################################################
# Fetchers
#####################################################################


def get_prospect_board(
    season: int,
    *,
    draft: str | None = None,
    pos: str | None = None,
    board_type: str | None = None,
    players: str | None = None,
) -> Any:
    """Fetch THE BOARD for a season.

    Args:
        season: Board season year.
        draft: Board slug; defaults to ``"<season>prospect"`` (the main
            prospect board). Other slugs select draft/international boards.
        pos: Optional position filter.
        board_type: Optional board type filter.
        players: Optional comma-joined player filter.

    Returns:
        The raw JSON payload exactly as FanGraphs produced it.

    Raises:
        FangraphsError: On a Cloudflare 403.
    """
    return fg_json(
        "/api/prospects/board/data",
        {
            "draft": draft or f"{season}prospect",
            "season": season,
            "type": board_type,
            "pos": pos,
            "players": players,
        },
    )
