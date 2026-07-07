"""Guts! — league constants and park factors.

These are the only FanGraphs endpoints in fungo served as HTML tables rather
than JSON: the React ``/guts`` page ships an empty shell, and the legacy
``guts.aspx`` still carries the real data. Tables are small and stable, so a
stdlib ``html.parser`` extraction suffices — no third-party parser needed.

Following fungo's CSV convention, every cell value is returned as a string
(``""`` for empty cells); callers cast themselves.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from fungo.exceptions import FangraphsError
from fungo.fangraphs.api import fg_html

#####################################################################
# Minimal HTML table extraction (stdlib)
#####################################################################


class _TableParser(HTMLParser):
    """Collect every ``<table>`` on a page as rows of cell strings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_cell = False
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self.tables.append([])
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._in_table = False
        elif self._in_table and tag == "tr":
            if self._row:
                self.tables[-1].append(self._row)
        elif self._in_table and tag in ("td", "th"):
            self._in_cell = False
            self._row.append("".join(self._cell).strip())

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)


def _parse_guts_table(html: str, context: str) -> list[dict[str, Any]]:
    """Extract the data table from a ``guts.aspx`` page as row dicts.

    Picks the largest table whose header row starts with ``Season`` — the
    shape shared by all three Guts boards.

    Args:
        html: Page HTML.
        context: Board name for error messages.

    Returns:
        One dict per row, keyed by the header row; all values are strings.

    Raises:
        FangraphsError: If no Guts-shaped table is found.
    """
    parser = _TableParser()
    parser.feed(html)

    candidates = [
        t
        for t in parser.tables
        if len(t) >= 2 and t[0] and t[0][0].strip().lower() == "season"
    ]
    if not candidates:
        raise FangraphsError(f"No Guts table found on {context}")

    table = max(candidates, key=len)
    header = table[0]
    return [dict(zip(header, row, strict=False)) for row in table[1:]]


#####################################################################
# Fetchers
#####################################################################


def get_guts_constants() -> list[dict[str, Any]]:
    """Fetch seasonal league constants (wOBA weights, FIP constant, run env).

    Returns:
        One row per season with columns like ``Season``, ``lg_woba``,
        ``woba_scale``, ``wBB``, ``wHBP``, ``w1B`` ... ``cFIP``. All values
        are strings.
    """
    html = fg_html("/guts.aspx", {"type": "cn"})
    return _parse_guts_table(html, "guts constants")


def get_park_factors(season: int) -> list[dict[str, Any]]:
    """Fetch park factors for a season.

    Args:
        season: Season year.

    Returns:
        One row per team; all values are strings.
    """
    html = fg_html("/guts.aspx", {"type": "pf", "teamid": 0, "season": season})
    return _parse_guts_table(html, f"park factors {season}")


def get_park_factors_by_handedness(season: int) -> list[dict[str, Any]]:
    """Fetch park factors split by batter handedness for a season.

    Args:
        season: Season year.

    Returns:
        One row per team; all values are strings.
    """
    html = fg_html("/guts.aspx", {"type": "pfh", "teamid": 0, "season": season})
    return _parse_guts_table(html, f"handedness park factors {season}")
