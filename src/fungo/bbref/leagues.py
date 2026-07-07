"""Baseball-Reference league pages — season standings and the amateur draft."""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_html
from fungo.bbref.tables import extract_all_tables, extract_table

#####################################################################
# Standings
#####################################################################


def get_standings(year: int) -> dict[str, list[dict[str, Any]]]:
    """Fetch a season's standings page.

    Args:
        year: Season year.

    Returns:
        Mapping of table id -> rows. Modern seasons carry the division tables
        twice under the same id — **AL first, NL second in document order** —
        so the NL tables arrive suffixed: ``standings_E`` (AL East),
        ``standings_E_2`` (NL East), and likewise ``_C``/``_W``. The 30-team
        ``expanded_standings_overall`` table (comment-deferred) is included;
        pre-1969 seasons have no division tables and *only* that one. The
        strike-split 1981 season additionally carries half-season tables.
    """
    return extract_all_tables(bbref_html(f"/leagues/MLB/{year}-standings.shtml"))


#####################################################################
# Amateur draft
#####################################################################


def get_draft(
    year: int, draft_round: int, *, draft_type: str = "junreg"
) -> list[dict[str, Any]]:
    """Fetch one round of an amateur draft.

    Args:
        year: Draft year.
        draft_round: Round number (1-based).
        draft_type: Draft phase; ``"junreg"`` (June regular, the main draft)
            is the only phase for modern years.

    Returns:
        One row per pick from the ``draft_stats`` table: overall pick, team,
        signed flag, bonus, player (name may carry a ``" (minors)"`` suffix),
        position, and career-to-date stats. All values are strings.
    """
    html = bbref_html(
        "/draft/",
        {
            "year_ID": year,
            "draft_round": draft_round,
            "draft_type": draft_type,
            "query_type": "year_round",
        },
    )
    return extract_table(html, "draft_stats")


def get_draft_by_team(
    team: str, year: int, *, draft_type: str = "junreg"
) -> list[dict[str, Any]]:
    """Fetch a team's complete draft class for a year.

    Args:
        team: B-R *franchise* code. Note the draft query uses historical
            franchise codes for three clubs: Angels = ``ANA``, Marlins =
            ``FLA``, Rays = ``TBD``; everything else is the modern code.
        year: Draft year.
        draft_type: Draft phase (see :func:`get_draft`).

    Returns:
        One row per pick from the ``draft_stats`` table.
    """
    html = bbref_html(
        "/draft/",
        {
            "team_ID": team.upper(),
            "year_ID": year,
            "draft_type": draft_type,
            "query_type": "franch_year",
        },
    )
    return extract_table(html, "draft_stats")
