"""MLB Stats API — stats, leaders, and streaks endpoints.

Also exposes :func:`build_stats_hydrate` for constructing the ``stats(...)``
hydration string used on ``/api/v1/people``. The builder enforces the most
important gotcha: ``sportId`` inside
``stats(...)`` is scalar-only — a comma or bracketed list silently returns
empty results. Fan out one request per ``sportId`` instead (see
:func:`fungo.mlb.people.get_player_stats_all_sports`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fungo.exceptions import ValidationError
from fungo.mlb.stats_api import _csv, _fmt_date, mlb_api

#####################################################################
# Streak enumerations
#####################################################################

_VALID_STREAK_TYPES = [
    "hittingStreakOverall", "hittingStreakHome", "hittingStreakAway",
    "onBaseOverall", "onBaseHome", "onBaseAway",
]  # fmt: skip

_VALID_STREAK_SPANS = [
    "career", "season", "currentStreak", "currentStreakInSeason", "notable",
    "notableInSeason",
]  # fmt: skip


#####################################################################
# Hydrate builder
#####################################################################


def _bracket_list(values: Any) -> str | None:
    """Format a list/tuple as ``[a,b,c]``; scalars pass through as ``str``.

    Args:
        values: A list/tuple to bracket, a scalar to stringify, or ``None``.

    Returns:
        The bracketed list string, the stringified scalar, or ``None``.
    """
    if values is None:
        return None
    if isinstance(values, (list, tuple)):
        return "[" + ",".join(str(v) for v in values) + "]"
    return str(values)


def build_stats_hydrate(
    group: str | list[str] | None = None,
    type: str | list[str] | None = None,
    season: int | str | None = None,
    sport_id: int | str | None = None,
    limit: int | None = None,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
    opposing_player_id: int | str | None = None,
    opposing_team_id: int | str | None = None,
    sit_codes: str | list[str] | None = None,
    metrics: str | list[str] | None = None,
) -> str:
    """Build a ``stats(...)`` hydrate string for ``/api/v1/people``.

    Scalars are emitted unbracketed; lists are emitted bracket-comma
    (``[a,b]``). ``group`` and ``type`` accept bracketed lists, but ``sportId``
    does **not** — a list (comma- or bracket-form) silently returns empty
    results because the hydrate grammar treats commas as argument delimiters.
    Fan out one request per ``sportId`` and merge client-side instead (see
    :func:`fungo.mlb.people.get_player_stats_all_sports`).

    Args:
        group: Stat group(s) (e.g. ``hitting``, ``pitching``).
        type: Stat type(s) (e.g. ``season``, ``gameLog``).
        season: Season year.
        sport_id: A single sport/level id (scalar only).
        limit: Row limit.
        start_date: Range start (formatted to ``MM/DD/YYYY``).
        end_date: Range end (formatted to ``MM/DD/YYYY``).
        opposing_player_id: Opponent player id for matchup splits.
        opposing_team_id: Opponent team id for matchup splits.
        sit_codes: Situation split code(s).
        metrics: Statcast metric name(s).

    Returns:
        A ``stats(...)`` hydration string.

    Raises:
        ValidationError: If ``sport_id`` is a list/tuple/set (scalar only).
    """
    if isinstance(sport_id, (list, tuple, set)):
        raise ValidationError(sport_id, "sport_id")

    parts: list[str] = []
    if group is not None:
        parts.append(f"group={_bracket_list(group)}")
    if type is not None:
        parts.append(f"type={_bracket_list(type)}")
    if season is not None:
        parts.append(f"season={season}")
    if sport_id is not None:
        parts.append(f"sportId={sport_id}")
    if limit is not None:
        parts.append(f"limit={limit}")
    if start_date is not None:
        parts.append(f"startDate={_fmt_date(start_date)}")
    if end_date is not None:
        parts.append(f"endDate={_fmt_date(end_date)}")
    if opposing_player_id is not None:
        parts.append(f"opposingPlayerId={opposing_player_id}")
    if opposing_team_id is not None:
        parts.append(f"opposingTeamId={opposing_team_id}")
    if sit_codes is not None:
        parts.append(f"sitCodes={_bracket_list(sit_codes)}")
    if metrics is not None:
        parts.append(f"metrics={_bracket_list(metrics)}")

    return f"stats({','.join(parts)})"


#####################################################################
# Stats / leaders / streaks
#####################################################################


def get_stats(
    stats: str | list[str],
    group: str | list[str],
    season: int | str | None = None,
    sport_ids: int | list[int] | None = None,
    game_type: str | None = None,
    player_pool: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    order: str | None = None,
    sort_stat: str | None = None,
    person_ids: int | str | list[int | str] | None = None,
    team_ids: int | str | list[int | str] | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/stats`` — general player or team stats.

    Args:
        stats: Stat type(s) (e.g. ``season``, ``career``).
        group: Stat group(s) (e.g. ``hitting``, ``pitching``).
        season: Season year.
        sport_ids: Sport/level id(s).
        game_type: Game-type code.
        player_pool: Player pool (e.g. ``all``, ``qualified``).
        limit: Page size.
        offset: Page offset.
        order: Sort direction.
        sort_stat: Stat field to sort by.
        person_ids: Player id(s) to filter by.
        team_ids: Team id(s) to filter by.

    Returns:
        The raw JSON stats payload.
    """
    params = {
        "stats": _csv(stats),
        "group": _csv(group),
        "season": season,
        "sportIds": _csv(sport_ids),
        "gameType": game_type,
        "playerPool": player_pool,
        "limit": limit,
        "offset": offset,
        "order": order,
        "sortStat": sort_stat,
        "personIds": _csv(person_ids),
        "teamIds": _csv(team_ids),
    }
    return mlb_api("/api/v1/stats", params)


def get_stat_leaders(
    leader_categories: str | list[str],
    season: int | str | None = None,
    sport_id: int | str | None = None,
    game_types: str | list[str] | None = None,
    stat_group: str | None = None,
    leader_game_types: str | list[str] | None = None,
    player_pool: str | None = None,
    limit: int | None = None,
    stat_type: str | None = None,
    sit_codes: str | list[str] | None = None,
    hydrate: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/stats/leaders`` — league-wide stat leaders.

    Args:
        leader_categories: Leader category name(s).
        season: Season year.
        sport_id: Sport/level id.
        game_types: Game-type code(s).
        stat_group: Stat group.
        leader_game_types: Leader game-type code(s).
        player_pool: Player pool.
        limit: Page size.
        stat_type: Stat type.
        sit_codes: Situation split code(s).
        hydrate: Optional hydration string.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON leaders payload.
    """
    params = {
        "leaderCategories": _csv(leader_categories),
        "season": season,
        "sportId": sport_id,
        "gameTypes": _csv(game_types),
        "statGroup": stat_group,
        "leaderGameTypes": _csv(leader_game_types),
        "playerPool": player_pool,
        "limit": limit,
        "statType": stat_type,
        "sitCodes": _csv(sit_codes),
        "hydrate": hydrate,
        "fields": fields,
    }
    return mlb_api("/api/v1/stats/leaders", params)


def get_streaks(
    streak_type: str,
    streak_span: str,
    season: int | str,
    sport_id: int | str,
    limit: int | str,
    game_type: str | None = None,
    hydrate: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/stats/streaks`` — hitting / on-base streaks.

    Args:
        streak_type: One of :data:`_VALID_STREAK_TYPES`.
        streak_span: One of :data:`_VALID_STREAK_SPANS`.
        season: Season year.
        sport_id: Sport/level id.
        limit: Row limit.
        game_type: Game-type code.
        hydrate: Optional hydration string.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON streaks payload.

    Raises:
        ValidationError: If ``streak_type`` or ``streak_span`` is invalid.
    """
    if streak_type not in _VALID_STREAK_TYPES:
        raise ValidationError(streak_type, "streak_type", _VALID_STREAK_TYPES)
    if streak_span not in _VALID_STREAK_SPANS:
        raise ValidationError(streak_span, "streak_span", _VALID_STREAK_SPANS)
    params = {
        "streakType": streak_type,
        "streakSpan": streak_span,
        "season": season,
        "sportId": sport_id,
        "limit": limit,
        "gameType": game_type,
        "hydrate": hydrate,
        "fields": fields,
    }
    return mlb_api("/api/v1/stats/streaks", params)
