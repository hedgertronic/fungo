"""RosterResource — depth charts, payroll, lineup tracker.

RosterResource pages have no public ``/api/...`` twin; their data ships in the
Next.js ``__NEXT_DATA__`` blob as a dehydrated React-Query cache. One page GET
returns everything the page shows — for a depth chart that means the roster,
projected lineups, probable starters, roster breakdown, recent transactions,
bullpen usage, prospects grid, and pending free agents in a single payload.

No other open-source library exposes this data; the structure was mapped from
live page snapshots (July 2026) and may shift when FanGraphs redeploys.
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import FangraphsError
from fungo.fangraphs.api import fg_page_data

#####################################################################
# Dehydrated-state extraction
#####################################################################


def _dehydrated_queries(path: str) -> list[dict[str, Any]]:
    """Fetch ``path`` and return its dehydrated React-Query cache entries.

    Args:
        path: RosterResource page path.

    Returns:
        The ``queries`` list; each entry has ``queryKey`` and
        ``state.data``.

    Raises:
        FangraphsError: If the page carries no dehydrated state.
    """
    next_data = fg_page_data(path)
    queries = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries", [])
    )
    if not queries:
        raise FangraphsError(f"No dehydrated data found on {path}")
    return list(queries)


def get_roster_resource(page: str) -> dict[str, Any]:
    """Fetch any RosterResource page's primary data payload.

    Args:
        page: Path segment after ``/roster-resource/`` — e.g.
            ``"depth-charts/rangers"``, ``"payroll"``, ``"lineup-tracker"``.

    Returns:
        The first dehydrated query's ``state.data`` — the raw object the page
        renders from.

    Raises:
        FangraphsError: If the page carries no dehydrated data payload.
    """
    queries = _dehydrated_queries(f"/roster-resource/{page.lstrip('/')}")
    data = queries[0].get("state", {}).get("data")
    if not isinstance(data, dict):
        raise FangraphsError(
            f"Unexpected RosterResource payload on {page!r}: {type(data).__name__}"
        )
    return data


def get_depth_chart(team: str) -> dict[str, Any]:
    """Fetch a team's full RosterResource depth chart.

    Args:
        team: Team slug as used in the site URL — lowercase, hyphenated
            (``"rangers"``, ``"red-sox"``, ``"diamondbacks"``).

    Returns:
        Raw payload whose keys include ``dataRoster``, ``dataLineups``,
        ``dataProbableStarters``, ``dataRosterBreakdown``,
        ``dataRecentTransactions``, ``dataBullpenUsage``, ``dataProspectsGrid``,
        and ``dataFreeAgents``.
    """
    return get_roster_resource(f"depth-charts/{team}")
