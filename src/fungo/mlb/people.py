"""MLB Stats API — people endpoints (players, coaches, umpires).

Includes :func:`get_player_stats_all_sports`, the fan-out helper for the known
gotcha that ``sportId`` inside ``stats(...)`` is scalar-only — a comma or
bracketed list silently returns empty results, so full MLB+MiLB coverage
requires one request per ``sportId`` (see ``references/gotchas.md``, section A).
"""

from __future__ import annotations

from typing import Any

from fungo import http
from fungo.mlb.constants import HYDRATE_SPORT_IDS
from fungo.mlb.stats_api import _csv, mlb_api

#####################################################################
# People
#####################################################################


def get_people(
    person_ids: int | str | list[int | str],
    hydrate: str | None = None,
    season: int | str | None = None,
    app_context: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/people`` — bio + hydrations for one or more people.

    Args:
        person_ids: A single MLBAM person id or a list of ids.
        hydrate: Optional hydration string (e.g. a ``stats(...)`` expression
            built by :func:`fungo.mlb.stats.build_stats_hydrate`).
        season: Optional season context for the hydrations.
        app_context: Optional ``appContext`` value.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON ``people`` payload.
    """
    params = {
        "personIds": _csv(person_ids),
        "hydrate": hydrate,
        "season": season,
        "appContext": app_context,
        "fields": fields,
    }
    return mlb_api("/api/v1/people", params)


def get_person(
    person_id: int | str,
    hydrate: str | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/people/{personId}`` — a single person by id.

    Gotcha: ``currentTeam.sport`` can come back as an empty object ``{}`` even
    for an affiliated player. Do not rely solely on ``currentTeam.sport.id`` to
    determine a player's level — cross-check the team's own sport mapping.

    Args:
        person_id: MLBAM person id.
        hydrate: Optional hydration string.
        fields: Optional sparse-field selection string.

    Returns:
        The raw JSON payload for the person.
    """
    params = {"hydrate": hydrate, "fields": fields}
    return mlb_api(f"/api/v1/people/{person_id}", params)


def search_players(
    names: str | None = None,
    person_ids: int | str | list[int | str] | None = None,
    *,
    active: bool | None = None,
    current_team_id: int | str | None = None,
    sport_id: int | str | None = None,
) -> dict[str, Any]:
    """Search ``/api/v1/people/search`` by name or attributes.

    Args:
        names: Free-text name query.
        person_ids: One or more MLBAM ids to filter by.
        active: Filter to active players when ``True``.
        current_team_id: Filter to a current team.
        sport_id: Filter to a sport/level.

    Returns:
        The raw JSON search payload (contains a ``people`` list).
    """
    params = {
        "names": names,
        "personIds": _csv(person_ids),
        "active": active,
        "currentTeamId": current_team_id,
        "sportId": sport_id,
    }
    return mlb_api("/api/v1/people/search", params)


def search_player_matches(name: str, sport_id: int | str = 1) -> list[dict[str, Any]]:
    """Return the raw ``people`` list from a name search.

    Args:
        name: Player name query.
        sport_id: Sport/level to scope the search (default MLB).

    Returns:
        The list of matching ``people`` dicts (``[]`` if none).
    """
    data = search_players(names=name, sport_id=sport_id)
    return data.get("people", []) or []


def find_player(name: str, sport_id: int | str = 1) -> list[dict[str, Any]]:
    """Alias for :func:`search_player_matches`.

    New code should prefer ``search_player_matches`` because it follows the
    package convention that ``search_*`` helpers return search result rows.
    """
    return search_player_matches(name, sport_id=sport_id)


def resolve_player_id(name: str, sport_id: int | str = 1) -> int | None:
    """Resolve a player name to a single MLBAM id, or ``None``.

    Prefers active players; on ties, returns the most-recent (largest id).

    Args:
        name: Player name query.
        sport_id: Sport/level to scope the search (default MLB).

    Returns:
        The resolved MLBAM id, or ``None`` if no match.
    """
    people = search_player_matches(name, sport_id=sport_id)
    if not people:
        return None
    if len(people) == 1:
        return people[0].get("id")
    actives = [p for p in people if p.get("active")]
    candidates = actives or people
    candidates.sort(key=lambda p: p.get("id", 0), reverse=True)
    return candidates[0].get("id")


def get_player_changes(
    updated_since: str,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Fetch ``/api/v1/people/changes`` — players with bio updates.

    Args:
        updated_since: ISO timestamp; returns players changed since then.
        limit: Optional page size.
        offset: Optional page offset.

    Returns:
        The raw JSON changes payload.
    """
    params = {"updatedSince": updated_since, "limit": limit, "offset": offset}
    return mlb_api("/api/v1/people/changes", params)


def get_free_agents(season: int | str, order: str | None = None) -> dict[str, Any]:
    """Fetch ``/api/v1/people/freeAgents`` — free agents for a season.

    Args:
        season: Season year.
        order: Optional sort order.

    Returns:
        The raw JSON free-agents payload.
    """
    params = {"season": season, "order": order}
    return mlb_api("/api/v1/people/freeAgents", params)


def get_player_stats_all_sports(
    person_id: int | str,
    season: int | str,
    groups: tuple[str, ...] = ("hitting", "pitching"),
    stat_types: tuple[str, ...] = ("season",),
    sport_ids: tuple[int, ...] = HYDRATE_SPORT_IDS,
) -> dict[str, Any]:
    """Fan out one ``get_people()`` call per ``sport_id`` and merge by sport.

    Works around the gotcha that ``sportId`` inside ``stats(...)`` is
    scalar-only — a list silently returns empty results. Requests are issued
    concurrently via :func:`fungo.http.map_concurrent` (bounded thread pool,
    results in input order).

    Args:
        person_id: MLBAM person id.
        season: Season year for the stat hydration.
        groups: Stat groups to hydrate (e.g. ``hitting``, ``pitching``).
        stat_types: Stat types to hydrate (e.g. ``season``, ``gameLog``).
        sport_ids: Sport/level ids to iterate over (default MLB + MiLB).

    Returns:
        ``{"person_id": person_id, "by_sport": {sport_id: payload, ...}}``.
    """
    from fungo.mlb.stats import build_stats_hydrate

    def fetch(sid: int) -> dict[str, Any]:
        hydrate = build_stats_hydrate(
            group=list(groups),
            type=list(stat_types),
            season=season,
            sport_id=sid,
        )
        return get_people(person_id, hydrate=hydrate, season=season)

    payloads = http.map_concurrent(fetch, list(sport_ids))
    by_sport = dict(zip(sport_ids, payloads, strict=True))
    return {"person_id": person_id, "by_sport": by_sport}
