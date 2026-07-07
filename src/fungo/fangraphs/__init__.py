"""FanGraphs data access — leaderboards, player stats, RosterResource,
Guts!, and THE BOARD.

Everything rides FanGraphs' JSON API (or, for RosterResource, the JSON embedded
in server-rendered pages) through the stdlib transport in :mod:`fungo.http`.
JSON endpoints return raw payloads with native numeric values — unlike fungo's
CSV sources, values are NOT all strings. The Guts! HTML tables follow the CSV
convention (all values strings).

Access depends on Cloudflare exempting the FanGraphs mobile app's HTTP client
(see :mod:`fungo.fangraphs.api`); a withdrawn exemption raises
:class:`~fungo.exceptions.FangraphsError` on every call. FanGraphs states that
automated access is "not supported" — endpoints may change without notice. Be
polite: fetch what you need, cache locally, don't loop over the league.
"""

from __future__ import annotations

from fungo.fangraphs.api import fg_html, fg_json, fg_json_post, fg_page_data
from fungo.fangraphs.guts import (
    get_guts_constants,
    get_park_factors,
    get_park_factors_by_handedness,
)
from fungo.fangraphs.leaders import (
    SPLIT_MONTHS,
    STAT_GROUPS,
    fetch_leaders,
    get_leaders,
    get_splits,
)
from fungo.fangraphs.players import get_game_log, get_player_stats
from fungo.fangraphs.projections import (
    PROJECTION_SYSTEMS,
    ROS_PROJECTION_SYSTEMS,
    get_projections,
)
from fungo.fangraphs.prospects import get_prospect_board
from fungo.fangraphs.roster_resource import get_depth_chart, get_roster_resource
from fungo.fangraphs.splits import (
    PITCH_SPLIT_CODE_TABLE,
    PITCH_SPLIT_CODES,
    SPLIT_CODE_TABLE,
    SPLIT_CODES,
    get_split_leaders,
)

__all__ = [
    "PITCH_SPLIT_CODES",
    "PITCH_SPLIT_CODE_TABLE",
    "PROJECTION_SYSTEMS",
    "ROS_PROJECTION_SYSTEMS",
    "SPLIT_CODES",
    "SPLIT_CODE_TABLE",
    "SPLIT_MONTHS",
    "STAT_GROUPS",
    "fetch_leaders",
    "fg_html",
    "fg_json",
    "fg_json_post",
    "fg_page_data",
    "get_depth_chart",
    "get_game_log",
    "get_guts_constants",
    "get_leaders",
    "get_park_factors",
    "get_park_factors_by_handedness",
    "get_player_stats",
    "get_projections",
    "get_prospect_board",
    "get_roster_resource",
    "get_split_leaders",
    "get_splits",
]
