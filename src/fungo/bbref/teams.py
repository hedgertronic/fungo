"""Baseball-Reference team pages — schedule & results, season pages."""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_html
from fungo.bbref.tables import extract_all_tables

#####################################################################
# Fetchers
#####################################################################


def get_team_schedule(team: str, year: int) -> dict[str, list[dict[str, Any]]]:
    """Fetch a team's schedule & results page for a season.

    Args:
        team: B-R franchise code (``"NYY"``, ``"TEX"``, ...). Note B-R uses
            its own historical codes for some clubs (e.g. the Yankees' box
            scores live under ``NYA``) — the schedule pages use the modern
            three-letter code.
        year: Season year.

    Returns:
        Mapping of table id -> rows for every table on the page.
    """
    html = bbref_html(f"/teams/{team.upper()}/{year}-schedule-scores.shtml")
    return extract_all_tables(html)


def get_team_season(team: str, year: int) -> dict[str, list[dict[str, Any]]]:
    """Fetch a team's season page (roster, team batting/pitching, ...).

    Args:
        team: B-R franchise code (``"NYY"``, ``"TEX"``, ...).
        year: Season year.

    Returns:
        Mapping of table id -> rows for every table on the page.
    """
    html = bbref_html(f"/teams/{team.upper()}/{year}.shtml")
    return extract_all_tables(html)
