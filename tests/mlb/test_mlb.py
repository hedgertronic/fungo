"""Offline tests for the ``fungo.mlb`` subpackage.

Transport is mocked by monkeypatching ``fungo.http.request_json`` (the call
site in ``stats_api.mlb_api`` does attribute lookup on the ``http`` module, so
this interception works). A single ``@pytest.mark.live`` smoke test (deselected
by default) hits the real API.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from fungo import http
from fungo.exceptions import MLBStatsError, ValidationError
from fungo.mlb import discovery, games, misc, people, stats, teams
from fungo.mlb.constants import HYDRATE_SPORT_IDS
from fungo.mlb.stats_api import _fmt_date, mlb_api


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict | None]]:
    """Capture (url, params) for each ``request_json`` call; return ``{}``."""
    calls: list[tuple[str, dict | None]] = []

    def fake_request_json(
        url: str, params: dict[str, Any] | None = None, **_kw: Any
    ) -> dict:
        calls.append((url, params))
        return {}

    monkeypatch.setattr(http, "request_json", fake_request_json)
    return calls


#####################################################################
# build_stats_hydrate
#####################################################################


def test_build_stats_hydrate_scalar() -> None:
    hydrate = stats.build_stats_hydrate(
        group=["hitting", "pitching"], type=["season"], season=2024, sport_id=12
    )
    assert (
        hydrate
        == "stats(group=[hitting,pitching],type=[season],season=2024,sportId=12)"
    )


def test_build_stats_hydrate_all_optional_params() -> None:
    # Exercises every optional emitter: limit, dates, opposing ids, sitCodes,
    # metrics. Scalar group/type pass through _bracket_list unbracketed.
    hydrate = stats.build_stats_hydrate(
        group="hitting",
        type="season",
        limit=5,
        start_date="2024-04-01",
        end_date="2024-04-30",
        opposing_player_id=592450,
        opposing_team_id=147,
        sit_codes=["vsl", "vsr"],
        metrics="launchSpeed",
    )
    assert hydrate == (
        "stats(group=hitting,type=season,limit=5,"
        "startDate=04/01/2024,endDate=04/30/2024,"
        "opposingPlayerId=592450,opposingTeamId=147,"
        "sitCodes=[vsl,vsr],metrics=launchSpeed)"
    )


def test_bracket_list_none_returns_none() -> None:
    assert stats._bracket_list(None) is None


def test_build_stats_hydrate_list_sport_id_raises() -> None:
    # sportId inside stats(...) is scalar-only; a list silently returns empty.
    with pytest.raises(ValueError):
        stats.build_stats_hydrate(group=["hitting"], sport_id=[11, 12])
    # ValidationError is a ValueError subclass — assert the specific type too.
    with pytest.raises(ValidationError):
        stats.build_stats_hydrate(group=["hitting"], sport_id=(11, 12))


#####################################################################
# _fmt_date
#####################################################################


def test_fmt_date_iso() -> None:
    assert _fmt_date("2024-07-04") == "07/04/2024"


def test_fmt_date_already_us() -> None:
    assert _fmt_date("07/04/2024") == "07/04/2024"


def test_fmt_date_date_and_datetime() -> None:
    assert _fmt_date(date(2024, 7, 4)) == "07/04/2024"
    assert _fmt_date(datetime(2024, 7, 4, 13, 5)) == "07/04/2024"


def test_fmt_date_none() -> None:
    assert _fmt_date(None) is None


def test_fmt_date_bad_type() -> None:
    with pytest.raises(TypeError):
        _fmt_date(12345)  # type: ignore[arg-type]


def test_fmt_date_isoformat_fallback() -> None:
    # Not a 10-char US/ISO string, but parseable by fromisoformat.
    assert _fmt_date("2024-07-04T13:05:00") == "07/04/2024"


def test_fmt_date_unparseable_passthrough() -> None:
    # Unrecognized string is returned unchanged.
    assert _fmt_date("not a date") == "not a date"


#####################################################################
# URL / param construction
#####################################################################


def test_get_roster_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_roster(147, roster_type="40Man", season=2024, date="2024-07-04")
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/147/roster")
    assert params is not None
    assert params["rosterType"] == "40Man"
    assert params["season"] == 2024
    assert params["date"] == "07/04/2024"


def test_get_roster_invalid_type_raises() -> None:
    with pytest.raises(ValidationError):
        teams.get_roster(147, roster_type="bogus")


def test_get_schedule_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_schedule(
        sport_id=1, start_date="2024-04-01", end_date="2024-04-05", team_id=147
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/schedule")
    assert params is not None
    assert params["sportId"] == 1
    assert params["startDate"] == "04/01/2024"
    assert params["endDate"] == "04/05/2024"
    assert params["teamId"] == 147


def test_get_gamefeed_uses_v11(capture: list[tuple[str, dict | None]]) -> None:
    games.get_gamefeed(745444)
    url, _ = capture[0]
    assert url.endswith("/api/v1.1/game/745444/feed/live")


#####################################################################
# Resolvers (against mocked search payload)
#####################################################################


def test_resolve_player_id_prefers_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "people": [
            {"id": 999999, "active": False},
            {"id": 100, "active": True},
            {"id": 592450, "active": True},
        ]
    }
    monkeypatch.setattr(http, "request_json", lambda *a, **k: payload)
    # Inactive 999999 is ignored; among actives the largest id wins.
    assert people.resolve_player_id("Aaron Judge") == 592450


def test_resolve_player_id_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http, "request_json", lambda *a, **k: {"people": [{"id": 660271}]}
    )
    assert people.resolve_player_id("Shohei Ohtani") == 660271


def test_resolve_player_id_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http, "request_json", lambda *a, **k: {"people": []})
    assert people.resolve_player_id("Nobody Here") is None


def test_resolve_team_id() -> None:
    assert teams.resolve_team_id("Yankees") == 147
    assert teams.resolve_team_id("NYY") == 147
    assert teams.resolve_team_id("new york yankees") == 147
    assert teams.resolve_team_id("Bogus") is None
    assert teams.resolve_team_id("") is None


#####################################################################
# Fan-out
#####################################################################


def test_get_player_stats_all_sports_fans_out(
    capture: list[tuple[str, dict | None]],
) -> None:
    result = people.get_player_stats_all_sports(660271, season=2024)
    # One call per sport id.
    assert len(capture) == len(HYDRATE_SPORT_IDS)
    assert set(result["by_sport"].keys()) == set(HYDRATE_SPORT_IDS)
    assert result["person_id"] == 660271
    # Each call carried a scalar sportId inside the hydrate.
    for _url, params in capture:
        assert params is not None
        assert "sportId=" in params["hydrate"]


#####################################################################
# mlb_api low-level entry point
#####################################################################


def test_mlb_api_builds_full_url(capture: list[tuple[str, dict | None]]) -> None:
    mlb_api("/api/v1/anything", {"foo": "bar"})
    url, params = capture[0]
    assert url == "https://statsapi.mlb.com/api/v1/anything"
    assert params == {"foo": "bar"}


def test_mlb_api_non_dict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # The wrapper guarantees a dict; a top-level array is an error.
    monkeypatch.setattr(http, "request_json", lambda *a, **k: [1, 2, 3])
    with pytest.raises(MLBStatsError):
        mlb_api("/api/v1/anything")


#####################################################################
# people
#####################################################################


def test_get_people_csv_joins_list(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.get_people([1, 2, 3], hydrate="stats(group=[hitting])", season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/people")
    assert params is not None
    # _csv joins a list to a comma-separated string (not a bracketed list).
    assert params["personIds"] == "1,2,3"
    assert params["hydrate"] == "stats(group=[hitting])"
    assert params["season"] == 2024


def test_get_people_scalar_passthrough(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.get_people(592450)
    _url, params = capture[0]
    assert params is not None
    assert params["personIds"] == 592450


def test_get_person_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.get_person(660271, hydrate="currentTeam", fields="people")
    url, params = capture[0]
    assert url.endswith("/api/v1/people/660271")
    assert params == {"hydrate": "currentTeam", "fields": "people"}


def test_search_players_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.search_players(
        names="Judge",
        person_ids=[1, 2],
        active=True,
        current_team_id=147,
        sport_id=1,
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/people/search")
    assert params is not None
    assert params["names"] == "Judge"
    assert params["personIds"] == "1,2"
    assert params["active"] is True
    assert params["currentTeamId"] == 147
    assert params["sportId"] == 1


def test_search_player_matches_passes_sport_id(
    capture: list[tuple[str, dict | None]],
) -> None:
    # search_player_matches returns [] from the empty mock; assert sportId scope.
    assert people.search_player_matches("Judge", sport_id=11) == []
    url, params = capture[0]
    assert url.endswith("/api/v1/people/search")
    assert params is not None
    assert params["names"] == "Judge"
    assert params["sportId"] == 11


def test_find_player_aliases_search_player_matches(
    capture: list[tuple[str, dict | None]],
) -> None:
    assert people.find_player("Judge", sport_id=11) == []
    url, params = capture[0]
    assert url.endswith("/api/v1/people/search")
    assert params is not None
    assert params["names"] == "Judge"
    assert params["sportId"] == 11


def test_get_player_changes_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.get_player_changes("2024-07-04T00:00:00Z", limit=10, offset=5)
    url, params = capture[0]
    assert url.endswith("/api/v1/people/changes")
    assert params is not None
    assert params["updatedSince"] == "2024-07-04T00:00:00Z"
    assert params["limit"] == 10
    assert params["offset"] == 5


def test_get_free_agents_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    people.get_free_agents(2024, order="desc")
    url, params = capture[0]
    assert url.endswith("/api/v1/people/freeAgents")
    assert params == {"season": 2024, "order": "desc"}


#####################################################################
# teams
#####################################################################


def test_get_teams_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_teams(
        season=2024,
        sport_ids=[1, 11],
        active_status="Y",
        all_star_statuses=["Y", "N"],
        league_ids=[103, 104],
        game_type="R",
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/teams")
    assert params is not None
    assert params["season"] == 2024
    assert params["sportIds"] == "1,11"
    assert params["activeStatus"] == "Y"
    assert params["allStarStatuses"] == "Y,N"
    assert params["leagueIds"] == "103,104"
    assert params["gameType"] == "R"


def test_get_team_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team(147, season=2024, sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/147")
    assert params is not None
    assert params["season"] == 2024
    assert params["sportId"] == 1


def test_get_team_history_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_history([147, 111], start_season=2000, end_season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/history")
    assert params is not None
    assert params["teamIds"] == "147,111"
    assert params["startSeason"] == 2000
    assert params["endSeason"] == 2024


def test_get_team_stats_arg_to_key_mapping(
    capture: list[tuple[str, dict | None]],
) -> None:
    # stat_group -> group, stats -> stats: the swappable mapping.
    teams.get_team_stats(
        season=2024,
        stat_group="hitting",
        stats="season",
        sport_ids=[1],
        start_date="2024-04-01",
        end_date="2024-04-30",
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/stats")
    assert params is not None
    assert params["group"] == "hitting"
    assert params["stats"] == "season"
    assert params["sportIds"] == "1"
    assert params["startDate"] == "04/01/2024"
    assert params["endDate"] == "04/30/2024"


def test_get_team_leaders_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_leaders(
        ["homeRuns", "wins"], season=2024, sport_id=1, game_types=["R", "P"]
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/stats/leaders")
    assert params is not None
    assert params["leaderCategories"] == "homeRuns,wins"
    assert params["gameTypes"] == "R,P"
    assert params["sportId"] == 1


def test_get_team_affiliates_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_affiliates([147], sport_id=1, season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/affiliates")
    assert params is not None
    assert params["teamIds"] == "147"
    assert params["sportId"] == 1


def test_get_team_specific_leaders_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_specific_leaders(
        147, ["homeRuns"], season=2024, leader_game_types=["R"]
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/147/leaders")
    assert params is not None
    assert params["leaderCategories"] == "homeRuns"
    assert params["leaderGameTypes"] == "R"


def test_get_team_specific_stats_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_specific_stats(147, season=2024, group="hitting", stats="season")
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/147/stats")
    assert params is not None
    assert params["group"] == "hitting"
    assert params["stats"] == "season"


def test_get_team_alumni_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    teams.get_team_alumni(147, 2024, group="hitting")
    url, params = capture[0]
    assert url.endswith("/api/v1/teams/147/alumni")
    assert params is not None
    assert params["season"] == 2024
    assert params["group"] == "hitting"


#####################################################################
# games
#####################################################################


def test_get_schedule_csv_and_date_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_schedule(
        game_pks=[745444, 745445],
        venue_ids=[1, 2],
        game_types=["R", "P"],
        date="2024-07-04",
    )
    _url, params = capture[0]
    assert params is not None
    assert params["gamePks"] == "745444,745445"
    assert params["venueIds"] == "1,2"
    assert params["gameTypes"] == "R,P"
    assert params["date"] == "07/04/2024"


def test_get_gamefeed_params(capture: list[tuple[str, dict | None]]) -> None:
    games.get_gamefeed(745444, timecode="20240704_180000", hydrate="credits")
    _url, params = capture[0]
    assert params is not None
    assert params["timecode"] == "20240704_180000"
    assert params["hydrate"] == "credits"


def test_get_gamefeed_diffpatch_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_gamefeed_diffpatch(745444, "20240704_180000", "20240704_190000")
    url, params = capture[0]
    assert url.endswith("/api/v1.1/game/745444/feed/live/diffPatch")
    assert params is not None
    assert params["startTimecode"] == "20240704_180000"
    assert params["endTimecode"] == "20240704_190000"


def test_get_gamefeed_timestamps_uses_v11(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_gamefeed_timestamps(745444)
    url, _ = capture[0]
    assert url.endswith("/api/v1.1/game/745444/feed/live/timestamps")


def test_get_color_feed_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_color_feed(745444, timecode="20240704_180000")
    url, params = capture[0]
    assert url.endswith("/api/v1/game/745444/feed/color")
    assert params == {"timecode": "20240704_180000"}


def test_get_color_diffpatch_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_color_diffpatch(745444, "20240704_180000", "20240704_190000")
    url, params = capture[0]
    assert url.endswith("/api/v1/game/745444/feed/color/diffPatch")
    assert params is not None
    assert params["startTimecode"] == "20240704_180000"
    assert params["endTimecode"] == "20240704_190000"


def test_get_color_timestamps_url(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_color_timestamps(745444)
    url, _ = capture[0]
    assert url.endswith("/api/v1/game/745444/feed/color/timestamps")


def test_get_game_changes_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_game_changes("2024-07-04T00:00:00Z", sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/game/changes")
    assert params is not None
    assert params["updatedSince"] == "2024-07-04T00:00:00Z"
    assert params["sportId"] == 1


def test_get_postseason_schedule_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_postseason_schedule(season=2024, hydrate="team")
    url, params = capture[0]
    assert url.endswith("/api/v1/schedule/postseason")
    assert params == {"season": 2024, "hydrate": "team"}


def test_get_postseason_series_url(
    capture: list[tuple[str, dict | None]],
) -> None:
    games.get_postseason_series(season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/schedule/postseason/series")
    assert params == {"season": 2024}


def test_get_tied_games_url(capture: list[tuple[str, dict | None]]) -> None:
    games.get_tied_games(season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/schedule/games/tied")
    assert params == {"season": 2024}


@pytest.mark.parametrize(
    ("func", "suffix"),
    [
        (games.get_boxscore, "/api/v1/game/745444/boxscore"),
        (games.get_linescore, "/api/v1/game/745444/linescore"),
        (games.get_playbyplay, "/api/v1/game/745444/playByPlay"),
        (games.get_game_content, "/api/v1/game/745444/content"),
        (games.get_context_metrics, "/api/v1/game/745444/contextMetrics"),
        (games.get_win_probability, "/api/v1/game/745444/winProbability"),
    ],
)
def test_per_game_getters(
    capture: list[tuple[str, dict | None]],
    func: Any,
    suffix: str,
) -> None:
    func(745444)
    url, _ = capture[0]
    assert url.endswith(suffix)


#####################################################################
# stats
#####################################################################


def test_get_stats_arg_to_key_mapping(
    capture: list[tuple[str, dict | None]],
) -> None:
    stats.get_stats(
        stats=["season", "career"],
        group=["hitting", "pitching"],
        season=2024,
        sport_ids=[1, 11],
        person_ids=[592450, 660271],
        team_ids=147,
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/stats")
    assert params is not None
    assert params["stats"] == "season,career"
    assert params["group"] == "hitting,pitching"
    assert params["sportIds"] == "1,11"
    assert params["personIds"] == "592450,660271"
    assert params["teamIds"] == 147


def test_get_stat_leaders_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    stats.get_stat_leaders(["homeRuns"], season=2024, sport_id=1, stat_group="hitting")
    url, params = capture[0]
    assert url.endswith("/api/v1/stats/leaders")
    assert params is not None
    assert params["leaderCategories"] == "homeRuns"
    assert params["statGroup"] == "hitting"
    assert params["sportId"] == 1


def test_get_streaks_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    stats.get_streaks(
        "hittingStreakOverall", "season", season=2024, sport_id=1, limit=10
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/stats/streaks")
    assert params is not None
    assert params["streakType"] == "hittingStreakOverall"
    assert params["streakSpan"] == "season"
    assert params["season"] == 2024
    assert params["sportId"] == 1
    assert params["limit"] == 10


def test_get_streaks_invalid_type_raises() -> None:
    with pytest.raises(ValidationError):
        stats.get_streaks("bogus", "season", season=2024, sport_id=1, limit=10)


def test_get_streaks_invalid_span_raises() -> None:
    with pytest.raises(ValidationError):
        stats.get_streaks(
            "hittingStreakOverall", "bogus", season=2024, sport_id=1, limit=10
        )


#####################################################################
# misc
#####################################################################


def test_get_draft_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_draft(2024, round="1")
    url, params = capture[0]
    assert url.endswith("/api/v1/draft/2024")
    assert params == {"round": "1"}


def test_get_draft_prospects_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_draft_prospects(
        2024, school_year="HS", state="CA", country="USA", position="P"
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/draft/prospects/2024")
    assert params is not None
    assert params["schoolYear"] == "HS"
    assert params["state"] == "CA"
    assert params["country"] == "USA"
    assert params["position"] == "P"


def test_get_award_recipients_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_award_recipients("MLBMVP", season=2024, sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/awards/MLBMVP/recipients")
    assert params is not None
    assert params["season"] == 2024
    assert params["sportId"] == 1


def test_get_transactions_date_formatting(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_transactions(team_id=147, start_date="2024-07-04", end_date="2024-07-31")
    url, params = capture[0]
    assert url.endswith("/api/v1/transactions")
    assert params is not None
    assert params["teamId"] == 147
    # _fmt_date applied to a body param.
    assert params["startDate"] == "07/04/2024"
    assert params["endDate"] == "07/31/2024"


def test_get_venues_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_venues(venue_ids=[1, 2], season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/venues")
    assert params is not None
    assert params["venueIds"] == "1,2"
    assert params["season"] == 2024


def test_get_standings_csv_and_date(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_standings(
        [103, 104], season=2024, standings_types=["regularSeason"], date="2024-07-04"
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/standings")
    assert params is not None
    assert params["leagueId"] == "103,104"
    assert params["standingsTypes"] == "regularSeason"
    assert params["date"] == "07/04/2024"


def test_get_leagues_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_leagues(sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/league")
    assert params == {"sportId": 1}


def test_get_divisions_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_divisions(division_id=200, league_id=103, sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/divisions")
    assert params is not None
    assert params["divisionId"] == 200
    assert params["leagueId"] == 103
    assert params["sportId"] == 1


def test_get_seasons_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_seasons(sport_id=1, season=2024, with_game_type_dates=True)
    url, params = capture[0]
    assert url.endswith("/api/v1/seasons")
    assert params is not None
    assert params["sportId"] == 1
    assert params["season"] == 2024
    assert params["withGameTypeDates"] is True


def test_get_attendance_csv_and_date(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_attendance(
        team_id=147, league_id=[103, 104], season=2024, date="2024-07-04"
    )
    url, params = capture[0]
    assert url.endswith("/api/v1/attendance")
    assert params is not None
    assert params["teamId"] == 147
    assert params["leagueId"] == "103,104"
    assert params["date"] == "07/04/2024"


def test_get_sports_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_sports(sport_id=1, active_status="Y")
    url, params = capture[0]
    assert url.endswith("/api/v1/sports")
    assert params is not None
    assert params["sportId"] == 1
    assert params["activeStatus"] == "Y"


def test_get_sport_players_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_sport_players(11, 2024, game_type="R")
    url, params = capture[0]
    assert url.endswith("/api/v1/sports/11/players")
    assert params is not None
    assert params["season"] == 2024
    assert params["gameType"] == "R"


def test_get_umpires_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_umpires(sport_id=1, date="2024-07-04", season=2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/jobs/umpires")
    assert params is not None
    assert params["sportId"] == 1
    assert params["date"] == "07/04/2024"
    assert params["season"] == 2024


def test_get_high_low_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_high_low("player", sort_stat="homeRuns", season=2024, sport_id=1)
    url, params = capture[0]
    assert url.endswith("/api/v1/highLow/player")
    assert params is not None
    assert params["sortStat"] == "homeRuns"
    assert params["season"] == 2024
    assert params["sportId"] == 1


def test_get_game_pace_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_game_pace(season=2024, sport_id=1, game_type="R")
    url, params = capture[0]
    assert url.endswith("/api/v1/gamePace")
    assert params is not None
    assert params["season"] == 2024
    assert params["sportId"] == 1
    assert params["gameType"] == "R"


def test_get_uniforms_game_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_uniforms_game([745444, 745445])
    url, params = capture[0]
    assert url.endswith("/api/v1/uniforms/game")
    assert params == {"gamePks": "745444,745445"}


def test_get_uniforms_team_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_uniforms_team([147, 111], 2024)
    url, params = capture[0]
    assert url.endswith("/api/v1/uniforms/team")
    assert params is not None
    assert params["teamIds"] == "147,111"
    assert params["season"] == 2024


@pytest.mark.parametrize(
    ("func", "arg", "suffix"),
    [
        (misc.get_venue, 1, "/api/v1/venues/1"),
        (misc.get_league, 103, "/api/v1/league/103"),
        (misc.get_season, 2024, "/api/v1/seasons/2024"),
        (misc.get_sport, 1, "/api/v1/sports/1"),
        (misc.get_home_run_derby, 511101, "/api/v1/homeRunDerby/511101"),
        (misc.get_derby_bracket, 511101, "/api/v1/homeRunDerby/511101/bracket"),
        (misc.get_derby_pool, 511101, "/api/v1/homeRunDerby/511101/pool"),
    ],
)
def test_misc_single_id_getters(
    capture: list[tuple[str, dict | None]],
    func: Any,
    arg: int,
    suffix: str,
) -> None:
    func(arg)
    url, _ = capture[0]
    assert url.endswith(suffix)


@pytest.mark.parametrize(
    ("func", "suffix"),
    [
        (misc.get_official_scorers, "/api/v1/jobs/officialScorers"),
        (misc.get_datacasters, "/api/v1/jobs/datacasters"),
        (misc.get_conferences, "/api/v1/conferences"),
    ],
)
def test_misc_no_arg_getters(
    capture: list[tuple[str, dict | None]],
    func: Any,
    suffix: str,
) -> None:
    func()
    url, params = capture[0]
    assert url.endswith(suffix)
    assert params is None


def test_get_broadcasts_url_and_params(
    capture: list[tuple[str, dict | None]],
) -> None:
    misc.get_broadcasts(sport_id=1, date="2024-07-04", team_id=147)
    url, params = capture[0]
    assert url.endswith("/api/v1/schedule/broadcasts")
    assert params is not None
    assert params["sportId"] == 1
    assert params["date"] == "07/04/2024"
    assert params["teamId"] == 147


#####################################################################
# discovery (no-arg meta endpoints)
#####################################################################


@pytest.mark.parametrize(
    ("func", "suffix"),
    [
        (discovery.get_stat_types, "/api/v1/statTypes"),
        (discovery.get_stat_groups, "/api/v1/statGroups"),
        (discovery.get_game_types, "/api/v1/gameTypes"),
        (discovery.get_positions, "/api/v1/positions"),
        (discovery.get_situation_codes, "/api/v1/situationCodes"),
        (discovery.get_metrics, "/api/v1/metrics"),
        (discovery.get_league_leader_types, "/api/v1/leagueLeaderTypes"),
        (discovery.get_sports_discovery, "/api/v1/sports"),
        (discovery.get_baseball_stats, "/api/v1/baseballStats"),
        (discovery.get_roster_types, "/api/v1/rosterTypes"),
        (discovery.get_standings_types, "/api/v1/standingsTypes"),
        (discovery.get_game_status, "/api/v1/gameStatus"),
        (discovery.get_pitch_types, "/api/v1/pitchTypes"),
        (discovery.get_hit_trajectories, "/api/v1/hitTrajectories"),
        (discovery.get_event_types, "/api/v1/eventTypes"),
        (discovery.get_schedule_event_types, "/api/v1/scheduleEventTypes"),
        (discovery.get_wind_direction, "/api/v1/windDirection"),
        (discovery.get_sky, "/api/v1/sky"),
        (discovery.get_job_types, "/api/v1/jobTypes"),
        (discovery.get_languages, "/api/v1/languages"),
        (discovery.get_platforms, "/api/v1/platforms"),
    ],
)
def test_discovery_endpoints(
    capture: list[tuple[str, dict | None]],
    func: Any,
    suffix: str,
) -> None:
    func()
    url, _ = capture[0]
    assert url.endswith(suffix)


#####################################################################
# get_hydrations
#####################################################################


def test_get_hydrations_top_level(monkeypatch: pytest.MonkeyPatch) -> None:
    # /api/v1/people/{id} places the array at the response top level (and
    # again inside each person object); the top-level copy wins.
    payload = {
        "hydrations": ["currentTeam", "team", "stats"],
        "people": [{"id": 545361, "hydrations": ["currentTeam", "team", "stats"]}],
    }
    monkeypatch.setattr(http, "request_json", lambda *a, **k: payload)
    assert discovery.get_hydrations("/api/v1/people/545361") == [
        "currentTeam",
        "team",
        "stats",
    ]


def test_get_hydrations_nested_retries_without_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # /api/v1/teams/{id} places the array only inside each team object, and
    # fields=hydrations strips the whole payload there — the empty first
    # response triggers one retry without fields.
    calls: list[dict | None] = []

    def fake_request_json(
        url: str, params: dict[str, Any] | None = None, **_kw: Any
    ) -> dict:
        calls.append(params)
        if params is not None and "fields" in params:
            return {}
        return {"teams": [{"id": 119, "hydrations": ["venue", "league"]}]}

    monkeypatch.setattr(http, "request_json", fake_request_json)
    assert discovery.get_hydrations("/api/v1/teams/119") == ["venue", "league"]
    assert len(calls) == 2
    assert calls[0] is not None and calls[0]["fields"] == "hydrations"
    assert calls[1] is not None and "fields" not in calls[1]
    assert calls[1]["hydrate"] == "hydrations"


def test_get_hydrations_params_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict | None]] = []

    def fake_request_json(
        url: str, params: dict[str, Any] | None = None, **_kw: Any
    ) -> dict:
        calls.append((url, params))
        return {"hydrations": ["venue"]}

    monkeypatch.setattr(http, "request_json", fake_request_json)
    user_params = {"sportId": 1, "hydrate": "ignored"}
    discovery.get_hydrations("/api/v1/teams/119", user_params)
    url, params = calls[0]
    assert url.endswith("/api/v1/teams/119")
    assert params is not None
    # User params are preserved; hydrate/fields are forced to "hydrations".
    assert params["sportId"] == 1
    assert params["hydrate"] == "hydrations"
    assert params["fields"] == "hydrations"
    # The caller's dict is not mutated.
    assert user_params == {"sportId": 1, "hydrate": "ignored"}


def test_get_hydrations_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # No hydrations list anywhere in the payload names the path in the error.
    monkeypatch.setattr(
        http, "request_json", lambda *a, **k: {"copyright": "x", "people": [{}]}
    )
    with pytest.raises(MLBStatsError, match="/api/v1/people/545361"):
        discovery.get_hydrations("/api/v1/people/545361")


#####################################################################
# Live smoke tests (deselected by default)
#####################################################################


@pytest.mark.live
def test_live_get_hydrations_smoke() -> None:
    assert "currentTeam" in discovery.get_hydrations("/api/v1/people/545361")


@pytest.mark.live
def test_live_schedule_smoke() -> None:
    data = games.get_schedule(
        sport_id=1, season=2024, start_date="2024-04-01", end_date="2024-04-01"
    )
    assert isinstance(data, dict)
    assert "dates" in data
