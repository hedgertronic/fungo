"""MLB Stats API — schedule, live game feed (GUMBO), and per-game endpoints.

The live game feed uses ``/api/v1.1/game/{gamePk}/feed/live``; nearly every
other endpoint here uses ``/api/v1``. Omitting all date params on the schedule
returns the current day's games.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fungo.mlb.stats_api import _csv, _fmt_date, mlb_api

#####################################################################
# Schedule
#####################################################################


def get_schedule(
    sport_id: int | str | None = None,
    game_pks: int | str | list[int | str] | None = None,
    date: str | date | datetime | None = None,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
    team_id: int | str | None = None,
    opponent_id: int | str | None = None,
    league_id: int | str | None = None,
    venue_ids: int | str | list[int | str] | None = None,
    game_types: str | list[str] | None = None,
    schedule_type: str | None = None,
    schedule_types: str | list[str] | None = None,
    event_types: str | list[str] | None = None,
    schedule_event_types: str | list[str] | None = None,
    *,
    use_latest_games: bool | None = None,
    timecode: str | None = None,
    hydrate: str | None = None,
    fields: str | None = None,
    season: int | str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/schedule`` — the game schedule.

    Date inputs are auto-converted to ``MM/DD/YYYY``. Omitting all date params
    returns today's games.

    Args:
        sport_id: Sport/level id.
        game_pks: One or more game primary keys.
        date: Single date.
        start_date: Range start.
        end_date: Range end.
        team_id: Team filter.
        opponent_id: Opponent-team filter.
        league_id: League filter.
        venue_ids: Venue id(s).
        game_types: Game-type code(s).
        schedule_type: Schedule type.
        schedule_types: Schedule type(s).
        event_types: Event type(s).
        schedule_event_types: Schedule event type(s).
        use_latest_games: Return only the latest games when ``True``.
        timecode: Point-in-time timecode (``YYYYMMDD_HHMMSS``).
        hydrate: Optional hydration string (flat, e.g. ``linescore,decisions``).
        fields: Optional sparse-field selection string.
        season: Season year.

    Returns:
        The raw JSON schedule payload.
    """
    params = {
        "sportId": sport_id,
        "gamePks": _csv(game_pks),
        "date": _fmt_date(date),
        "startDate": _fmt_date(start_date),
        "endDate": _fmt_date(end_date),
        "teamId": team_id,
        "opponentId": opponent_id,
        "leagueId": league_id,
        "venueIds": _csv(venue_ids),
        "gameTypes": _csv(game_types),
        "scheduleType": schedule_type,
        "scheduleTypes": _csv(schedule_types),
        "eventTypes": _csv(event_types),
        "scheduleEventTypes": _csv(schedule_event_types),
        "useLatestGames": use_latest_games,
        "timecode": timecode,
        "hydrate": hydrate,
        "fields": fields,
        "season": season,
    }
    return mlb_api("/api/v1/schedule", params)


#####################################################################
# Live game feed (GUMBO)
#####################################################################


def get_gamefeed(
    game_pk: int | str,
    timecode: str | None = None,
    hydrate: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1.1/game/{gamePk}/feed/live`` — the full GUMBO live feed.

    Args:
        game_pk: Game primary key.
        timecode: Point-in-time timecode (``YYYYMMDD_HHMMSS``).
        hydrate: Optional hydration string.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON GUMBO payload.
    """
    params = {"timecode": timecode, "hydrate": hydrate, "fields": fields}
    return mlb_api(f"/api/v1.1/game/{game_pk}/feed/live", params)


def get_gamefeed_diffpatch(
    game_pk: int | str,
    start_timecode: str,
    end_timecode: str,
) -> dict[str, Any]:
    """Fetch ``/api/v1.1/game/{gamePk}/feed/live/diffPatch`` — incremental updates.

    Args:
        game_pk: Game primary key.
        start_timecode: Start timecode (``YYYYMMDD_HHMMSS``).
        end_timecode: End timecode (``YYYYMMDD_HHMMSS``).

    Returns:
        The raw JSON diff-patch payload.
    """
    params = {"startTimecode": start_timecode, "endTimecode": end_timecode}
    return mlb_api(f"/api/v1.1/game/{game_pk}/feed/live/diffPatch", params)


def get_gamefeed_timestamps(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1.1/game/{gamePk}/feed/live/timestamps``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON timestamps payload.
    """
    return mlb_api(f"/api/v1.1/game/{game_pk}/feed/live/timestamps")


#####################################################################
# Per-game standalone endpoints
#####################################################################


def get_boxscore(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/boxscore``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON boxscore payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/boxscore")


def get_linescore(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/linescore``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON linescore payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/linescore")


def get_playbyplay(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/playByPlay``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON play-by-play payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/playByPlay")


def get_game_content(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/content`` — editorial + media.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON content payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/content")


def get_context_metrics(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/contextMetrics``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON context-metrics payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/contextMetrics")


def get_win_probability(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/winProbability``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON win-probability payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/winProbability")


#####################################################################
# Color feed
#####################################################################


def get_color_feed(
    game_pk: int | str,
    timecode: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/feed/color`` — the color-commentary feed.

    Args:
        game_pk: Game primary key.
        timecode: Point-in-time timecode (``YYYYMMDD_HHMMSS``).

    Returns:
        The raw JSON color-feed payload.
    """
    params = {"timecode": timecode}
    return mlb_api(f"/api/v1/game/{game_pk}/feed/color", params)


def get_color_diffpatch(
    game_pk: int | str,
    start_timecode: str,
    end_timecode: str,
) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/feed/color/diffPatch``.

    Args:
        game_pk: Game primary key.
        start_timecode: Start timecode (``YYYYMMDD_HHMMSS``).
        end_timecode: End timecode (``YYYYMMDD_HHMMSS``).

    Returns:
        The raw JSON color diff-patch payload.
    """
    params = {"startTimecode": start_timecode, "endTimecode": end_timecode}
    return mlb_api(f"/api/v1/game/{game_pk}/feed/color/diffPatch", params)


def get_color_timestamps(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/game/{gamePk}/feed/color/timestamps``.

    Args:
        game_pk: Game primary key.

    Returns:
        The raw JSON color-timestamps payload.
    """
    return mlb_api(f"/api/v1/game/{game_pk}/feed/color/timestamps")


#####################################################################
# Game changes + postseason
#####################################################################


def get_game_changes(
    updated_since: str,
    sport_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/game/changes`` — games with non-Statcast data corrections.

    Args:
        updated_since: ISO timestamp; returns games changed since then.
        sport_id: Sport/level id.

    Returns:
        The raw JSON game-changes payload.
    """
    params = {"updatedSince": updated_since, "sportId": sport_id}
    return mlb_api("/api/v1/game/changes", params)


def get_postseason_schedule(
    season: int | str | None = None,
    hydrate: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/schedule/postseason``.

    Args:
        season: Season year.
        hydrate: Optional hydration string.

    Returns:
        The raw JSON postseason-schedule payload.
    """
    params = {"season": season, "hydrate": hydrate}
    return mlb_api("/api/v1/schedule/postseason", params)


def get_postseason_series(season: int | str | None = None) -> dict[str, Any]:
    """Fetch ``/api/v1/schedule/postseason/series`` — postseason matchups.

    Args:
        season: Season year.

    Returns:
        The raw JSON postseason-series payload.
    """
    params = {"season": season}
    return mlb_api("/api/v1/schedule/postseason/series", params)


def get_tied_games(season: int | str | None = None) -> dict[str, Any]:
    """Fetch ``/api/v1/schedule/games/tied`` — tied games in the schedule.

    Args:
        season: Season year.

    Returns:
        The raw JSON tied-games payload.
    """
    params = {"season": season}
    return mlb_api("/api/v1/schedule/games/tied", params)
