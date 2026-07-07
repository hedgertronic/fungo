"""Baseball-Reference data access — polite, on-demand, single-page fetchers.

Sports Reference tolerates rate-limited automated access (their bot policy
publishes the limits) but prohibits bulk harvesting and redistribution. This
subpackage is built for the tolerated pattern: every request routes through a
process-wide rate limiter (~9 req/min, under both their stated 20/min and the
community-tested 10/min ceiling), one page fetch yields all of its tables at
once, and blocks raise :class:`~fungo.exceptions.BBRefError` with guidance
instead of retrying. Never loop these calls over a league — for bulk data use
the WAR daily files here, or Retrosheet/Lahman/Chadwick.

Parsing uses ``beautifulsoup4`` and transport uses ``curl_cffi`` with Chrome
TLS impersonation (B-R's Cloudflare fingerprint-blocked generic Python clients
for months in 2025) — both are core fungo dependencies.
"""

from __future__ import annotations

from fungo.bbref.boxes import BOX_SCORE_TEAM_CODES, get_box_score, get_daily
from fungo.bbref.cache import clear_cache, disable_cache, enable_cache
from fungo.bbref.leagues import get_draft, get_draft_by_team, get_standings
from fungo.bbref.players import (
    get_game_log,
    get_player,
    get_player_table,
    get_splits,
)
from fungo.bbref.register import get_register_player
from fungo.bbref.session import bbref_bytes, bbref_html
from fungo.bbref.tables import extract_all_tables, extract_table, list_tables
from fungo.bbref.teams import get_team_schedule, get_team_season
from fungo.bbref.war import (
    get_war_daily,
    get_war_daily_batting,
    get_war_daily_pitching,
)

__all__ = [
    "BOX_SCORE_TEAM_CODES",
    "bbref_bytes",
    "bbref_html",
    "clear_cache",
    "disable_cache",
    "enable_cache",
    "extract_all_tables",
    "extract_table",
    "get_box_score",
    "get_daily",
    "get_draft",
    "get_draft_by_team",
    "get_game_log",
    "get_player",
    "get_player_table",
    "get_register_player",
    "get_splits",
    "get_standings",
    "get_team_schedule",
    "get_team_season",
    "get_war_daily",
    "get_war_daily_batting",
    "get_war_daily_pitching",
    "list_tables",
]
