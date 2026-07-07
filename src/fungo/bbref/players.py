"""Baseball-Reference player pages, game logs, and splits.

Single-page, on-demand fetchers. One player page carries a dozen-plus tables
(standard/advanced/value batting and pitching, fielding, appearances,
salaries, postseason), so the polite pattern is one fetch, all tables — never
loop these over a league. B-R ids come from fungo's Chadwick lookup:
``fungo.lookup.mlbam_to_bbref(mlbam)`` -> ``"troutmi01"``.
"""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_html
from fungo.bbref.tables import extract_all_tables, extract_table

#####################################################################
# Paths
#####################################################################


def _player_path(bbref_id: str) -> str:
    """Build a player-page path from a B-R id (``troutmi01`` -> ``/players/t/...``)."""
    return f"/players/{bbref_id[0]}/{bbref_id}.shtml"


#####################################################################
# Fetchers
#####################################################################


def get_player(bbref_id: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch a player's page and extract every stats table (one request).

    Args:
        bbref_id: Baseball-Reference player id (e.g. ``"troutmi01"``) —
            resolvable from MLBAM via :func:`fungo.lookup.mlbam_to_bbref`.

    Returns:
        Mapping of table id -> rows. Typical ids include
        ``players_standard_batting``, ``players_advanced_batting``,
        ``players_value_batting``, ``players_standard_fielding``,
        ``appearances``, and ``br-salaries``. All values are strings.
    """
    return extract_all_tables(bbref_html(_player_path(bbref_id)))


def get_player_table(bbref_id: str, table_id: str) -> list[dict[str, Any]]:
    """Fetch a player's page and extract one table by id.

    Costs the same single request as :func:`get_player`; prefer that when you
    want more than one table.

    Args:
        bbref_id: Baseball-Reference player id.
        table_id: The table's ``id`` (e.g. ``"players_standard_batting"``).

    Returns:
        Row dicts keyed by ``data-stat``; all values are strings.

    Raises:
        BBRefError: If the table does not exist on the page (the error lists
            what is available).
    """
    return extract_table(bbref_html(_player_path(bbref_id)), table_id)


def get_game_log(
    bbref_id: str,
    year: int,
    *,
    kind: str = "b",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch a player's game log for a season.

    Args:
        bbref_id: Baseball-Reference player id.
        year: Season year.
        kind: ``"b"`` for batting, ``"p"`` for pitching, ``"f"`` for fielding.

    Returns:
        Mapping of table id -> rows for every table on the game-log page.
    """
    html = bbref_html(
        "/players/gl.fcgi",
        {"id": bbref_id, "t": kind, "year": year},
    )
    return extract_all_tables(html)


def get_splits(
    bbref_id: str,
    year: int | str = "Career",
    *,
    kind: str = "b",
) -> dict[str, list[dict[str, Any]]]:
    """Fetch a player's splits (vs hand, home/away, clutch, counts, ...).

    Args:
        bbref_id: Baseball-Reference player id.
        year: Season year, or ``"Career"`` for career splits. Career pages
            carry an extra leading column vs single-season pages.
        kind: ``"b"`` for batting splits, ``"p"`` for pitching splits.

    Returns:
        Mapping of table id -> rows, one table per split family.
    """
    html = bbref_html(
        "/players/split.fcgi",
        {"id": bbref_id, "year": year, "t": kind},
    )
    return extract_all_tables(html)
