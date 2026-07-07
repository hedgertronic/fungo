"""Baseball-Reference box scores and daily scoreboards.

Box-score URLs use Retrosheet-style home-team codes, which differ from B-R's
franchise codes for 12 of 30 clubs (Yankees box scores live under ``NYA``, not
``NYY``). :data:`BOX_SCORE_TEAM_CODES` maps the differences; the fetchers
accept either form.

A box score's team batting/pitching table ids embed the club's *name as used
that season* with spaces stripped (``BaltimoreOriolesbatting``) — never derive
them from a static map; enumerate them from the returned dict. The linescore
table carries no id and is returned under the ``"linescore"`` key.
"""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_html
from fungo.bbref.tables import _rows_from_table, _soup, extract_all_tables

#####################################################################
# Team-code mapping (franchise code -> Retrosheet-style box-score code)
#####################################################################

BOX_SCORE_TEAM_CODES: dict[str, str] = {
    "CHC": "CHN",
    "CHW": "CHA",
    "KCR": "KCA",
    "LAA": "ANA",
    "LAD": "LAN",
    "NYM": "NYN",
    "NYY": "NYA",
    "SDP": "SDN",
    "SFG": "SFN",
    "STL": "SLN",
    "TBR": "TBA",
    "WSN": "WAS",
}


#####################################################################
# Fetchers
#####################################################################


def get_box_score(
    home_team: str, date: str, *, game: int = 0
) -> dict[str, list[dict[str, Any]]]:
    """Fetch one game's box score.

    Args:
        home_team: Home team as a B-R franchise code (``"NYY"``) or a
            Retrosheet-style box-score code (``"NYA"``) — franchise codes are
            mapped automatically.
        date: Game date, ``YYYY-MM-DD``.
        game: ``0`` for a single game; ``1``/``2`` for doubleheader games.

    Returns:
        Mapping of table id -> rows: per-team ``<Name>batting`` /
        ``<Name>pitching`` tables, ``play_by_play``, ``top_plays``, plus the
        id-less linescore under ``"linescore"``.
    """
    code = BOX_SCORE_TEAM_CODES.get(home_team.upper(), home_team.upper())
    ymd = date.replace("-", "")
    html = bbref_html(f"/boxes/{code}/{code}{ymd}{game}.shtml")

    tables = extract_all_tables(html)
    linescore = _soup(html).find("table", class_="linescore")
    if linescore is not None:
        tables["linescore"] = _rows_from_table(linescore)
    return tables


def get_daily(date: str) -> dict[str, Any]:
    """Fetch the daily scoreboard: standings through/after a date + game links.

    Args:
        date: Date, ``YYYY-MM-DD``.

    Returns:
        A dict with ``"box_score_paths"`` (site paths of that day's box
        scores, usable with :func:`fungo.bbref.session.bbref_html`) and
        ``"tables"`` — the sixteen standings tables with stable ids
        ``standings-{upto|after}-{AL|NL}-{E|C|W|overall}`` ("upto" = season
        through that date, "after" = rest of season).
    """
    html = bbref_html("/boxes/", {"date": date})
    doc = _soup(html)
    paths = [
        str(a["href"])
        for a in doc.select("div.game_summary a[href]")
        if str(a["href"]).startswith("/boxes/") and str(a["href"]).endswith(".shtml")
    ]
    return {
        "box_score_paths": sorted(set(paths)),
        "tables": extract_all_tables(html),
    }
