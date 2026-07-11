"""MLB Stats API — miscellaneous endpoints.

Draft, awards, transactions, venues, standings, leagues, divisions, seasons,
attendance, sports, jobs, broadcasts, conferences, highLow, home-run derby,
game pace, and uniforms.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fungo.mlb.stats_api import _csv, _fmt_date, mlb_api

#####################################################################
# Draft + awards
#####################################################################


def get_draft(year: int | str, round: str | int | None = None) -> dict[str, Any]:
    """Fetch ``/api/v1/draft/{year}`` — draft results by year.

    Args:
        year: Draft year.
        round: Optional round filter.

    Returns:
        The raw JSON draft payload.
    """
    params = {"round": round}
    return mlb_api(f"/api/v1/draft/{year}", params)


def get_draft_prospects(
    year: int | str,
    school_year: str | None = None,
    state: str | None = None,
    country: str | None = None,
    position: str | None = None,
    team_id: int | str | None = None,
    round: str | int | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/draft/prospects/{year}``.

    Args:
        year: Draft year.
        school_year: School-year filter.
        state: State filter.
        country: Country filter.
        position: Position filter.
        team_id: Team filter.
        round: Round filter.

    Returns:
        The raw JSON draft-prospects payload.
    """
    params = {
        "schoolYear": school_year,
        "state": state,
        "country": country,
        "position": position,
        "teamId": team_id,
        "round": round,
    }
    return mlb_api(f"/api/v1/draft/prospects/{year}", params)


def get_award_recipients(
    award_id: str,
    season: int | str | None = None,
    sport_id: int | str | None = None,
    league_id: int | str | None = None,
    hydrate: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/awards/{awardId}/recipients``.

    Args:
        award_id: Award identifier.
        season: Season year.
        sport_id: Sport/level id.
        league_id: League id.
        hydrate: Optional hydration string.

    Returns:
        The raw JSON award-recipients payload.
    """
    params = {
        "season": season,
        "sportId": sport_id,
        "leagueId": league_id,
        "hydrate": hydrate,
    }
    return mlb_api(f"/api/v1/awards/{award_id}/recipients", params)


#####################################################################
# Transactions
#####################################################################


def get_transactions(
    team_id: int | str | None = None,
    player_id: int | str | None = None,
    date: str | date | datetime | None = None,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/transactions`` — trades, signings, DFAs, etc.

    Args:
        team_id: Team filter.
        player_id: Player filter.
        date: Single date (formatted to ``MM/DD/YYYY``).
        start_date: Range start (formatted to ``MM/DD/YYYY``).
        end_date: Range end (formatted to ``MM/DD/YYYY``).

    Returns:
        The raw JSON transactions payload.
    """
    params = {
        "teamId": team_id,
        "playerId": player_id,
        "date": _fmt_date(date),
        "startDate": _fmt_date(start_date),
        "endDate": _fmt_date(end_date),
    }
    return mlb_api("/api/v1/transactions", params)


#####################################################################
# Venues
#####################################################################


def get_venues(
    venue_ids: int | str | list[int | str] | None = None,
    season: int | str | None = None,
    hydrate: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/venues`` — the venue directory.

    Args:
        venue_ids: One or more venue ids.
        season: Season year.
        hydrate: Optional hydration string.

    Returns:
        The raw JSON venues payload.
    """
    params = {"venueIds": _csv(venue_ids), "season": season, "hydrate": hydrate}
    return mlb_api("/api/v1/venues", params)


def get_venue(venue_id: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/venues/{venueId}``.

    Args:
        venue_id: Venue id.

    Returns:
        The raw JSON venue payload.
    """
    return mlb_api(f"/api/v1/venues/{venue_id}")


#####################################################################
# Standings
#####################################################################


def get_standings(
    league_id: int | str | list[int | str],
    season: int | str | None = None,
    standings_types: str | list[str] | None = None,
    date: str | date | datetime | None = None,
    hydrate: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/standings``.

    Args:
        league_id: League id or list of league ids.
        season: Season year.
        standings_types: Standings type(s).
        date: As-of date (formatted to ``MM/DD/YYYY``).
        hydrate: Optional hydration string.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON standings payload.
    """
    params = {
        "leagueId": _csv(league_id),
        "season": season,
        "standingsTypes": _csv(standings_types),
        "date": _fmt_date(date),
        "hydrate": hydrate,
        "fields": fields,
    }
    return mlb_api("/api/v1/standings", params)


#####################################################################
# Leagues / divisions
#####################################################################


def get_leagues(sport_id: int | str | None = None) -> dict[str, Any]:
    """Fetch ``/api/v1/league`` — all leagues, optionally filtered by sport.

    Args:
        sport_id: Sport/level id.

    Returns:
        The raw JSON leagues payload.
    """
    params = {"sportId": sport_id}
    return mlb_api("/api/v1/league", params)


def get_league(league_id: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/league/{leagueId}``.

    Args:
        league_id: League id.

    Returns:
        The raw JSON league payload.
    """
    return mlb_api(f"/api/v1/league/{league_id}")


def get_divisions(
    division_id: int | str | None = None,
    league_id: int | str | None = None,
    sport_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/divisions``.

    Args:
        division_id: Division id.
        league_id: League id.
        sport_id: Sport/level id.

    Returns:
        The raw JSON divisions payload.
    """
    params = {
        "divisionId": division_id,
        "leagueId": league_id,
        "sportId": sport_id,
    }
    return mlb_api("/api/v1/divisions", params)


#####################################################################
# Seasons
#####################################################################


def get_seasons(
    sport_id: int | str | None = None,
    season: int | str | None = None,
    *,
    with_game_type_dates: bool | None = None,
    division_id: int | str | None = None,
    league_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/seasons`` — season date boundaries.

    Args:
        sport_id: Sport/level id.
        season: Season year.
        with_game_type_dates: Include per-game-type date boundaries.
        division_id: Division id.
        league_id: League id.

    Returns:
        The raw JSON seasons payload.
    """
    params = {
        "sportId": sport_id,
        "season": season,
        "withGameTypeDates": with_game_type_dates,
        "divisionId": division_id,
        "leagueId": league_id,
    }
    return mlb_api("/api/v1/seasons", params)


def get_season(season_id: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/seasons/{seasonId}``.

    Args:
        season_id: Season id (year).

    Returns:
        The raw JSON season payload.
    """
    return mlb_api(f"/api/v1/seasons/{season_id}")


#####################################################################
# Attendance
#####################################################################


def get_attendance(
    team_id: int | str | None = None,
    league_id: int | str | list[int | str] | None = None,
    season: int | str | None = None,
    date: str | date | datetime | None = None,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
    league_list_id: str | None = None,
    game_type: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/attendance``.

    Args:
        team_id: Team filter.
        league_id: League id or list of ids.
        season: Season year.
        date: Single date (formatted to ``MM/DD/YYYY``).
        start_date: Range start (formatted to ``MM/DD/YYYY``).
        end_date: Range end (formatted to ``MM/DD/YYYY``).
        league_list_id: Predefined league-list id.
        game_type: Game-type code.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON attendance payload.
    """
    params = {
        "teamId": team_id,
        "leagueId": _csv(league_id),
        "season": season,
        "date": _fmt_date(date),
        "startDate": _fmt_date(start_date),
        "endDate": _fmt_date(end_date),
        "leagueListId": league_list_id,
        "gameType": game_type,
        "fields": fields,
    }
    return mlb_api("/api/v1/attendance", params)


#####################################################################
# Sports / players
#####################################################################


def get_sports(
    sport_id: int | str | None = None,
    active_status: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/sports``.

    Args:
        sport_id: Sport/level id.
        active_status: Active-status filter.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON sports payload.
    """
    params = {"sportId": sport_id, "activeStatus": active_status, "fields": fields}
    return mlb_api("/api/v1/sports", params)


def get_sport(sport_id: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/sports/{sportId}``.

    Args:
        sport_id: Sport/level id.

    Returns:
        The raw JSON sport payload.
    """
    return mlb_api(f"/api/v1/sports/{sport_id}")


def get_sport_players(
    sport_id: int | str,
    season: int | str,
    game_type: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/sports/{sportId}/players`` — all players at a level.

    Args:
        sport_id: Sport/level id.
        season: Season year.
        game_type: Game-type code.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON sport-players payload.
    """
    params = {"season": season, "gameType": game_type, "fields": fields}
    return mlb_api(f"/api/v1/sports/{sport_id}/players", params)


#####################################################################
# Jobs
#####################################################################


def get_umpires(
    sport_id: int | str | None = None,
    date: str | date | datetime | None = None,
    season: int | str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/jobs/umpires``.

    Args:
        sport_id: Sport/level id.
        date: As-of date (formatted to ``MM/DD/YYYY``).
        season: Season year.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON umpires payload.
    """
    params = {
        "sportId": sport_id,
        "date": _fmt_date(date),
        "season": season,
        "fields": fields,
    }
    return mlb_api("/api/v1/jobs/umpires", params)


def get_official_scorers() -> dict[str, Any]:
    """Fetch ``/api/v1/jobs/officialScorers``.

    Returns:
        The raw JSON official-scorers payload.
    """
    return mlb_api("/api/v1/jobs/officialScorers")


def get_datacasters() -> dict[str, Any]:
    """Fetch ``/api/v1/jobs/datacasters``.

    Returns:
        The raw JSON datacasters payload.
    """
    return mlb_api("/api/v1/jobs/datacasters")


#####################################################################
# Broadcasts + conferences
#####################################################################


def get_broadcasts(
    sport_id: int | str | None = None,
    date: str | date | datetime | None = None,
    team_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/schedule/broadcasts``.

    Args:
        sport_id: Sport/level id.
        date: As-of date (formatted to ``MM/DD/YYYY``).
        team_id: Team filter.

    Returns:
        The raw JSON broadcasts payload.
    """
    params = {"sportId": sport_id, "date": _fmt_date(date), "teamId": team_id}
    return mlb_api("/api/v1/schedule/broadcasts", params)


def get_conferences() -> dict[str, Any]:
    """Fetch ``/api/v1/conferences``.

    Returns:
        The raw JSON conferences payload.
    """
    return mlb_api("/api/v1/conferences")


#####################################################################
# High/low + derby + game pace + uniforms
#####################################################################


def get_high_low(
    org_type: str,
    sort_stat: str | None = None,
    season: int | str | None = None,
    sport_id: int | str | None = None,
    game_type: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/highLow/{orgType}`` — record-setting stats.

    Args:
        org_type: Organization scope (e.g. ``player``, ``team``, ``game``).
        sort_stat: Stat field to rank by.
        season: Season year.
        sport_id: Sport/level id.
        game_type: Game-type code.

    Returns:
        The raw JSON high-low payload.
    """
    params = {
        "sortStat": sort_stat,
        "season": season,
        "sportId": sport_id,
        "gameType": game_type,
    }
    return mlb_api(f"/api/v1/highLow/{org_type}", params)


def get_home_run_derby(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/homeRunDerby/{gamePk}``.

    Args:
        game_pk: Home Run Derby game primary key.

    Returns:
        The raw JSON Home Run Derby payload.
    """
    return mlb_api(f"/api/v1/homeRunDerby/{game_pk}")


def get_derby_bracket(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/homeRunDerby/{gamePk}/bracket``.

    Args:
        game_pk: Home Run Derby game primary key.

    Returns:
        The raw JSON derby-bracket payload.
    """
    return mlb_api(f"/api/v1/homeRunDerby/{game_pk}/bracket")


def get_derby_pool(game_pk: int | str) -> dict[str, Any]:
    """Fetch ``/api/v1/homeRunDerby/{gamePk}/pool``.

    Args:
        game_pk: Home Run Derby game primary key.

    Returns:
        The raw JSON derby-pool payload.
    """
    return mlb_api(f"/api/v1/homeRunDerby/{game_pk}/pool")


def get_game_pace(
    season: int | str | None = None,
    sport_id: int | str | None = None,
    game_type: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/gamePace``.

    Args:
        season: Season year.
        sport_id: Sport/level id.
        game_type: Game-type code.

    Returns:
        The raw JSON game-pace payload.
    """
    params = {"season": season, "sportId": sport_id, "gameType": game_type}
    return mlb_api("/api/v1/gamePace", params)


def get_uniforms_game(
    game_pks: int | str | list[int | str],
) -> dict[str, Any]:
    """Fetch ``/api/v1/uniforms/game`` — uniform info for specific games.

    Args:
        game_pks: One or more game primary keys.

    Returns:
        The raw JSON game-uniforms payload.
    """
    params = {"gamePks": _csv(game_pks)}
    return mlb_api("/api/v1/uniforms/game", params)


def get_uniforms_team(
    team_ids: int | str | list[int | str],
    season: int | str,
) -> dict[str, Any]:
    """Fetch ``/api/v1/uniforms/team`` — uniform info for teams.

    Args:
        team_ids: One or more team ids.
        season: Season year.

    Returns:
        The raw JSON team-uniforms payload.
    """
    params = {"teamIds": _csv(team_ids), "season": season}
    return mlb_api("/api/v1/uniforms/team", params)
