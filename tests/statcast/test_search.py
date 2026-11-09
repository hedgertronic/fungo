"""Offline tests for fungo.statcast.search.

Transport is mocked by monkeypatching ``fungo.http.request_bytes`` (the choke
point both search and leaderboards route through).
"""

from __future__ import annotations

import pytest

from fungo import http
from fungo.exceptions import SavantError, ValidationError
from fungo.statcast import search

CSV_ONE_ROW = b"pitch_type,player_name\nFF,Cole\n"


def _record(monkeypatch):
    """Patch request_bytes to record calls and return a one-row CSV each time."""
    calls: list[dict] = []

    def fake_request_bytes(url, params=None, **kw):
        calls.append({"url": url, "params": dict(params) if params else {}})
        return CSV_ONE_ROW

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    return calls


#####################################################################
# _fetch_csv: HTML detection
#####################################################################


def test_fetch_csv_html_raises_savant_error(monkeypatch):
    monkeypatch.setattr(
        http, "request_bytes", lambda *a, **k: b"<!DOCTYPE html><html>nope</html>"
    )
    with pytest.raises(SavantError, match="HTML instead of CSV"):
        search._fetch_csv("https://x")


def test_fetch_csv_parses_csv(monkeypatch):
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: CSV_ONE_ROW)
    rows = search._fetch_csv("https://x")
    assert rows == [{"pitch_type": "FF", "player_name": "Cole"}]


#####################################################################
# Day-chunk boundary: <=5 days -> 1 fetch; >5 days -> N fetches
#####################################################################


def test_search_5_day_span_single_request(monkeypatch):
    calls = _record(monkeypatch)
    # 2024-06-01 -> 2024-06-06 is .days == 5 -> single request
    search.search_pitches("2024-06-01", "2024-06-06")
    assert len(calls) == 1
    assert calls[0]["params"]["game_date_gt"] == "2024-06-01"
    assert calls[0]["params"]["game_date_lt"] == "2024-06-06"


def test_statcast_search_aliases_search_pitches(monkeypatch):
    calls = _record(monkeypatch)
    search.statcast_search("2024-06-01", "2024-06-06")
    assert len(calls) == 1
    assert calls[0]["params"]["game_date_gt"] == "2024-06-01"
    assert calls[0]["params"]["game_date_lt"] == "2024-06-06"


def test_search_6_day_span_chunks_into_7_daily_requests(monkeypatch):
    calls = _record(monkeypatch)
    # 2024-06-01 -> 2024-06-07 is .days == 6 -> chunked, 7 inclusive days
    rows = search.search_pitches("2024-06-01", "2024-06-07", delay=0.0)
    assert len(calls) == 7
    # each chunk targets a single day (gt == lt)
    days = sorted(c["params"]["game_date_gt"] for c in calls)
    assert days == [
        "2024-06-01",
        "2024-06-02",
        "2024-06-03",
        "2024-06-04",
        "2024-06-05",
        "2024-06-06",
        "2024-06-07",
    ]
    for c in calls:
        assert c["params"]["game_date_gt"] == c["params"]["game_date_lt"]
    # 7 daily fetches, each returning one row, flattened in order
    assert len(rows) == 7


def test_search_chunks_follow_default_chunk_days(monkeypatch):
    calls = _record(monkeypatch)
    monkeypatch.setattr(search, "DEFAULT_CHUNK_DAYS", 3)
    rows = search.search_pitches("2024-06-01", "2024-06-07", delay=0.0)
    ranges = sorted(
        (c["params"]["game_date_gt"], c["params"]["game_date_lt"]) for c in calls
    )
    assert ranges == [
        ("2024-06-01", "2024-06-03"),
        ("2024-06-04", "2024-06-06"),
        ("2024-06-07", "2024-06-07"),
    ]
    assert len(rows) == 3


def test_search_start_after_end_raises(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(SavantError, match="after end_date"):
        search.search_pitches("2024-06-10", "2024-06-01")


def test_search_bad_date_format_raises_validation_error(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(ValidationError):
        search.search_pitches("06/01/2024", "2024-06-06")


def test_search_bad_end_date_format_raises_validation_error(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(ValidationError):
        search.search_pitches("2024-06-01", "06/06/2024")


def test_search_invalid_level_raises_validation_error(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(ValidationError):
        search.search_pitches("2024-06-01", "2024-06-02", level="college")


def test_search_game_invalid_level_raises_validation_error():
    with pytest.raises(ValidationError):
        search.search_game(123, level="college")


#####################################################################
# player_id -> lookup param per player_type
#####################################################################


def test_search_invalid_player_type_raises_validation_error(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(ValidationError):
        search.search_pitches("2024-06-01", "2024-06-02", player_type="fielder")


def test_search_pitcher_id_uses_pitchers_lookup(monkeypatch):
    calls = _record(monkeypatch)
    search.search_pitches(
        "2024-06-01", "2024-06-02", player_type="pitcher", player_id=543037
    )
    assert calls[0]["params"]["pitchers_lookup[]"] == "543037"


def test_search_batter_id_uses_batters_lookup(monkeypatch):
    calls = _record(monkeypatch)
    search.search_pitches(
        "2024-06-01", "2024-06-02", player_type="batter", player_id=665742
    )
    assert calls[0]["params"]["batters_lookup[]"] == "665742"


#####################################################################
# search_team resolves the team argument
#####################################################################


def test_search_team_invalid_side_raises_validation_error(monkeypatch):
    _record(monkeypatch)
    with pytest.raises(ValidationError):
        search.search_team("LAD", "2024-06-01", "2024-06-02", side="neutral")


def test_search_team_resolves_alias(monkeypatch):
    calls = _record(monkeypatch)
    search.search_team("Dodgers", "2024-06-01", "2024-06-02")
    assert calls[0]["params"]["hfTeam"] == "LAD|"


def test_search_team_home_side(monkeypatch):
    calls = _record(monkeypatch)
    search.search_team("NYY", "2024-06-01", "2024-06-02", side="home")
    assert calls[0]["params"]["home_team"] == "NYY"


def test_search_team_away_side(monkeypatch):
    calls = _record(monkeypatch)
    search.search_team("NYY", "2024-06-01", "2024-06-02", side="away")
    assert calls[0]["params"]["away_team"] == "NYY"
    assert "hfTeam" not in calls[0]["params"]


#####################################################################
# search_game / search_matchup wrappers
#####################################################################


def test_search_game_passes_game_pk_and_path(monkeypatch):
    calls = _record(monkeypatch)
    rows = search.search_game(745432)
    assert len(calls) == 1
    assert calls[0]["url"] == f"{search.BASE_URL}{search.SEARCH_PATH_MLB}"
    assert calls[0]["params"]["game_pk"] == "745432"
    # base search params are still present
    assert calls[0]["params"]["type"] == "details"
    assert rows == [{"pitch_type": "FF", "player_name": "Cole"}]


def test_search_game_milb_uses_minors_path(monkeypatch):
    calls = _record(monkeypatch)
    search.search_game(123, level="milb")
    assert calls[0]["url"] == f"{search.BASE_URL}{search.SEARCH_PATH_MILB}"


def test_search_matchup_sends_both_lookups(monkeypatch):
    calls = _record(monkeypatch)
    # <=5 day span stays a single request
    search.search_matchup(543037, 665742, "2024-06-01", "2024-06-03")
    assert len(calls) == 1
    params = calls[0]["params"]
    assert params["pitchers_lookup[]"] == "543037"
    assert params["batters_lookup[]"] == "665742"
    assert params["player_type"] == "pitcher"


#####################################################################
# _coerce_float / _mean helpers (edge cases)
#####################################################################


def test_coerce_float_blank_and_none_are_none():
    assert search._coerce_float("") is None
    assert search._coerce_float(None) is None


def test_coerce_float_zero_is_zero_not_none():
    # only "" and None are blank; 0 must coerce to 0.0
    assert search._coerce_float("0") == 0.0
    assert search._coerce_float(0) == 0.0


def test_coerce_float_non_numeric_is_none():
    assert search._coerce_float("abc") is None
    assert search._coerce_float(object()) is None


def test_coerce_float_numeric_string():
    assert search._coerce_float("93.4") == 93.4


def test_mean_skips_none_values():
    assert search._mean([1.0, None, 3.0]) == 2.0


def test_mean_all_none_returns_none():
    assert search._mean([None, None]) is None


def test_mean_empty_returns_none():
    assert search._mean([]) is None


#####################################################################
# aggregate_pitcher_arsenal (pure function — no transport)
#####################################################################


def _arsenal_rows():
    """Three FF + two SL for one pitcher; known release_speed/spin values."""
    return [
        {
            "pitcher": "543037",
            "pitch_type": "FF",
            "player_name": "Cole",
            "p_throws": "R",
            "release_speed": "97.0",
            "release_spin_rate": "2400",
            "spin_axis": "210",
        },
        {
            "pitcher": "543037",
            "pitch_type": "FF",
            "player_name": "Cole",
            "p_throws": "R",
            "release_speed": "99.0",
            "release_spin_rate": "2500",
            "spin_axis": "210",
        },
        {
            "pitcher": "543037",
            "pitch_type": "FF",
            "player_name": "Cole",
            "p_throws": "R",
            "release_speed": "",  # blank -> skipped by _mean
            "release_spin_rate": "2600",
            "spin_axis": "210",
        },
        {
            "pitcher": "543037",
            "pitch_type": "SL",
            "player_name": "Cole",
            "p_throws": "R",
            "release_speed": "88.0",
            "release_spin_rate": "",  # all SL spin blank
            "spin_axis": "",  # all SL axis blank
        },
        {
            "pitcher": "543037",
            "pitch_type": "SL",
            "player_name": "Cole",
            "p_throws": "R",
            "release_speed": "86.0",
            "release_spin_rate": "",
            "spin_axis": "",
        },
    ]


def test_aggregate_one_row_per_pitch_type():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    assert len(out) == 2
    by_type = {r["pitch_type"]: r for r in out}
    assert set(by_type) == {"FF", "SL"}


def test_aggregate_usage_pct_is_percentage():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    by_type = {r["pitch_type"]: r for r in out}
    # 3 FF + 2 SL = 5 total for the one pitcher
    assert by_type["FF"]["n_pitches"] == 3
    assert by_type["SL"]["n_pitches"] == 2
    assert by_type["FF"]["usage_pct"] == 60.0
    assert by_type["SL"]["usage_pct"] == 40.0


def test_aggregate_mean_skips_blank_values():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    by_type = {r["pitch_type"]: r for r in out}
    # FF release_speed: (97 + 99) / 2 = 98.0 (third row blank, skipped)
    assert by_type["FF"]["avg_release_speed"] == 98.0
    # FF spin: (2400 + 2500 + 2600) / 3 = 2500.0
    assert by_type["FF"]["avg_release_spin_rate"] == 2500.0
    # SL release_speed: (88 + 86) / 2 = 87.0
    assert by_type["SL"]["avg_release_speed"] == 87.0


def test_aggregate_all_blank_metric_is_none():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    by_type = {r["pitch_type"]: r for r in out}
    # every SL release_spin_rate is blank -> None
    assert by_type["SL"]["avg_release_spin_rate"] is None


def test_aggregate_carries_player_name_and_throws():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    for r in out:
        assert r["player_name"] == "Cole"
        assert r["p_throws"] == "R"


def test_aggregate_tilt_present_when_spin_axis_present():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    by_type = {r["pitch_type"]: r for r in out}
    # FF has spin_axis on every row -> avg_spin_axis set -> avg_tilt present
    assert by_type["FF"]["avg_spin_axis"] == 210.0
    assert "avg_tilt" in by_type["FF"]
    assert by_type["FF"]["avg_tilt"] == search.axis_to_clock(210.0)


def test_aggregate_tilt_absent_when_spin_axis_all_blank():
    out = search.aggregate_pitcher_arsenal(_arsenal_rows())
    by_type = {r["pitch_type"]: r for r in out}
    # all SL spin_axis blank -> avg_spin_axis None -> no avg_tilt key
    assert by_type["SL"]["avg_spin_axis"] is None
    assert "avg_tilt" not in by_type["SL"]


def test_aggregate_no_usage_pct_when_not_grouping_on_pitcher():
    rows = _arsenal_rows()
    out = search.aggregate_pitcher_arsenal(rows, group_by=("pitch_type",))
    for r in out:
        assert "usage_pct" not in r
        assert "pitch_type" in r


def test_get_pitcher_arsenal_wires_date_range_and_player_id(monkeypatch):
    calls = _record(monkeypatch)

    # one-row CSV per fetch is fine; we assert the request wiring, not the math
    def fake_request_bytes(url, params=None, **kw):
        calls.append({"url": url, "params": dict(params) if params else {}})
        return b"pitcher,pitch_type,player_name\n543037,FF,Cole\n"

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)

    out = search.get_pitcher_arsenal(543037, "2024-06-01", "2024-06-03")
    assert len(calls) == 1
    params = calls[0]["params"]
    assert params["pitchers_lookup[]"] == "543037"
    assert params["game_date_gt"] == "2024-06-01"
    assert params["game_date_lt"] == "2024-06-03"
    assert params["player_type"] == "pitcher"
    # aggregation ran: one group for the single FF row
    assert len(out) == 1
    assert out[0]["pitch_type"] == "FF"
    assert out[0]["n_pitches"] == 1
    assert out[0]["usage_pct"] == 100.0
