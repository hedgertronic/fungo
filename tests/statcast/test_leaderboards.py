"""Offline tests for fungo.statcast.leaderboards.

Focus: the load-bearing ``year_format`` param emission across ALL FOUR formats,
the percentile ``999999`` drop, and per-board ``player_id`` handling. Transport
is mocked at ``fungo.http.request_bytes``.
"""

from __future__ import annotations

import pytest

from fungo import http
from fungo.exceptions import SavantError, ValidationError
from fungo.statcast import leaderboards as lb


def _capture(monkeypatch, body=b"id,name\n1,x\n"):
    """Capture the params dict request_bytes receives; return ``body`` as CSV."""
    captured: dict = {}

    def fake_request_bytes(url, params=None, **kw):
        captured["url"] = url
        captured["params"] = dict(params) if params else {}
        return body

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    return captured


#####################################################################
# year_format param emission — all four formats
#####################################################################


def test_year_format_int_emits_year(monkeypatch):
    cap = _capture(monkeypatch)
    lb.fetch_leaderboard("exit-velocity-barrels", year=2024)
    assert cap["params"]["year"] == "2024"
    assert "seasonStart" not in cap["params"]
    assert "season[]" not in cap["params"]


def test_year_format_special_emits_composite_year(monkeypatch):
    cap = _capture(monkeypatch)
    lb.fetch_leaderboard("active-spin", year="2024_spin-based")
    assert cap["params"]["year"] == "2024_spin-based"
    assert "seasonStart" not in cap["params"]


def test_year_format_camelcase_emits_season_start_end_not_year(monkeypatch):
    cap = _capture(monkeypatch)
    lb.fetch_leaderboard("bat-tracking", year=2024)
    assert cap["params"]["seasonStart"] == "2024"
    assert cap["params"]["seasonEnd"] == "2024"
    assert "year" not in cap["params"]  # the load-bearing assertion


def test_swing_path_attack_angle_also_camelcase(monkeypatch):
    cap = _capture(monkeypatch)
    lb.fetch_leaderboard("bat-tracking/swing-path-attack-angle", year=2024)
    assert cap["params"]["seasonStart"] == "2024"
    assert cap["params"]["seasonEnd"] == "2024"
    assert "year" not in cap["params"]


def test_year_format_season_array_emits_season_bracket(monkeypatch):
    cap = _capture(monkeypatch)
    lb.fetch_leaderboard("bat-tracking/swing-timing-miss-distance", year=2024)
    assert cap["params"]["season[]"] == ["2024"]
    assert "year" not in cap["params"]
    assert "seasonStart" not in cap["params"]


#####################################################################
# _emit_year — multi-year semantics (camelCase range vs season[] array)
#####################################################################


def test_emit_year_camelcase_single_int_equal_start_end():
    query: dict = {}
    lb._emit_year(query, "bat-tracking", 2024)
    assert query["seasonStart"] == "2024"
    assert query["seasonEnd"] == "2024"


def test_emit_year_camelcase_tuple_range_min_max():
    query: dict = {}
    lb._emit_year(query, "bat-tracking", (2025, 2023))
    assert query["seasonStart"] == "2023"  # min
    assert query["seasonEnd"] == "2025"  # max
    assert "year" not in query


def test_emit_year_camelcase_empty_sequence_raises():
    with pytest.raises(ValidationError):
        lb._emit_year({}, "bat-tracking", [])


def test_emit_year_season_array_scalar_wraps_in_list():
    query: dict = {}
    lb._emit_year(query, "bat-tracking/swing-timing-miss-distance", 2024)
    assert query["season[]"] == ["2024"]


def test_emit_year_season_array_multi_list():
    query: dict = {}
    lb._emit_year(query, "bat-tracking/swing-timing-miss-distance", [2023, 2024])
    assert query["season[]"] == ["2023", "2024"]
    assert "year" not in query


def test_season_array_emits_list_value_through_transport(monkeypatch):
    # The final params handed to request_bytes must carry a LIST for season[],
    # so urlencode(doseq=True) repeats the key (season[]=2023&season[]=2024).
    cap = _capture(monkeypatch)
    lb.get_swing_timing_miss_distance([2023, 2024], min="q")
    assert cap["params"]["season[]"] == ["2023", "2024"]
    assert isinstance(cap["params"]["season[]"], list)


def test_camelcase_tuple_range_through_transport(monkeypatch):
    cap = _capture(monkeypatch)
    lb.get_bat_tracking((2023, 2025), min_swings="q")
    assert cap["params"]["seasonStart"] == "2023"
    assert cap["params"]["seasonEnd"] == "2025"
    assert "year" not in cap["params"]


@pytest.mark.parametrize("multi", [[2023, 2024], (2023, 2024)])
def test_multiyear_on_int_board_raises_fail_loud(multi):
    # Only the bat-tracking boards support multi-year. An int/special board must
    # reject list/tuple years rather than send str([2023, 2024]) as year=.
    with pytest.raises(ValidationError):
        lb._emit_year({}, "expected_statistics", multi)


def test_multiyear_via_get_leaderboard_raises_before_network():
    # _emit_year validates the year before any request, so this needs no mock.
    with pytest.raises(ValidationError):
        lb.get_leaderboard("expected_statistics", year=[2023, 2024])


#####################################################################
# typed wrappers carry the correct min param + emit correct season
#####################################################################


def test_get_bat_tracking_uses_minswings_and_season_range(monkeypatch):
    cap = _capture(monkeypatch)
    lb.get_bat_tracking(2024, min_swings="q")
    assert cap["params"]["minSwings"] == "q"
    assert cap["params"]["seasonStart"] == "2024"
    assert "year" not in cap["params"]


def test_get_swing_timing_miss_distance_uses_min_and_season_array(monkeypatch):
    cap = _capture(monkeypatch)
    lb.get_swing_timing_miss_distance(2024, min="q")
    assert cap["params"]["min"] == "q"
    assert cap["params"]["season[]"] == ["2024"]
    assert "minSwings" not in cap["params"]
    assert "year" not in cap["params"]


#####################################################################
# player_id handling
#####################################################################


def test_breaks_endpoint_omits_player_id_from_url(monkeypatch):
    # active-spin "breaks" on player_id — must not appear in the query
    cap = _capture(monkeypatch, body=b"pitcher_id,active_spin\n543037,0.9\n")
    lb.fetch_leaderboard("active-spin", year="2024_spin-based", player_id=543037)
    assert "player_id" not in cap["params"]


def test_bat_tracking_player_id_filters_on_id_column(monkeypatch):
    # bat-tracking is "ignored": server returns all rows under an `id` column.
    # Client-side filter must match `id` (not `player_id`) -> non-empty result.
    body = b"id,name,avg_bat_speed\n543037,Cole,75.0\n665742,Soto,72.1\n"
    _capture(monkeypatch, body=body)
    rows = lb.fetch_leaderboard("bat-tracking", year=2024, player_id=543037)
    assert len(rows) == 1
    assert rows[0]["id"] == "543037"


#####################################################################
# percentile rankings drops the 999999 placeholder
#####################################################################


def test_percentile_rankings_drops_999999(monkeypatch):
    body = b"player_id,xwoba\n543037,0.350\n999999,0.310\n"
    _capture(monkeypatch, body=body)
    rows = lb.get_percentile_rankings(year=2024)
    assert [r["player_id"] for r in rows] == ["543037"]


#####################################################################
# registry introspection + guards
#####################################################################


def test_get_leaderboard_unknown_slug_raises():
    with pytest.raises(ValidationError, match="not a valid leaderboard"):
        lb.get_leaderboard("nope")


def test_get_leaderboard_html_only_raises():
    with pytest.raises(ValidationError, match="not a valid leaderboard"):
        lb.get_leaderboard("statcast-park-factors", year=2024)


def test_get_leaderboard_special_int_year_raises():
    with pytest.raises(ValidationError, match="not a valid year"):
        lb.get_leaderboard("active-spin", year=2024)


def test_active_spin_year_composes():
    assert lb.active_spin_year(2024, "spin-based") == "2024_spin-based"
    assert lb.active_spin_year(2024, "observed") == "2024_observed"
    with pytest.raises(ValueError):
        lb.active_spin_year(2024, "bogus")


def test_cast_numeric_auto_detects_columns_and_preserves_input():
    rows = [
        {"name": "Judge", "barrels": "28", "rate": "12.5", "blank": ""},
        {"name": "Cole", "barrels": "not numeric", "rate": None, "blank": "x"},
    ]

    out = lb._cast_numeric(rows)

    assert out == [
        {"name": "Judge", "barrels": 28.0, "rate": 12.5, "blank": None},
        {"name": "Cole", "barrels": "not numeric", "rate": None, "blank": "x"},
    ]
    assert rows[0]["barrels"] == "28"


def test_cast_numeric_empty_and_selected_columns():
    assert lb._cast_numeric([]) == []
    out = lb._cast_numeric([{"a": "1", "b": "2"}], cols=["b", "missing"])
    assert out == [{"a": "1", "b": 2.0}]


def test_list_and_describe():
    assert "bat-tracking/swing-timing-miss-distance" in lb.list_leaderboards("batting")
    meta = lb.describe_leaderboard("bat-tracking")
    assert meta["year_format"] == "camelCase_season"
    with pytest.raises(ValidationError):
        lb.describe_leaderboard("nope")


def test_all_four_year_formats_present_in_registry():
    formats = {m["year_format"] for m in lb.LEADERBOARDS.values()}
    assert {"int", "special", "camelCase_season", "season_array"} <= formats


#####################################################################
# _fetch_html_json
#####################################################################


def test_fetch_html_json_extracts_array(monkeypatch):
    html = b'<html><script>var data = [{"venue":"Coors","pf":112}];</script></html>'
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: html)
    out = lb._fetch_html_json("https://x", var_name="data")
    assert out == [{"venue": "Coors", "pf": 112}]


def test_fetch_html_json_extracts_object_from_const(monkeypatch):
    html = (
        b"<script>const rolling = {"
        b'"windows":[{"label":"7","rows":[{"name":"A"}]}],'
        b'"meta":{"source":"fixture"}'
        b"};</script>"
    )
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: html)
    out = lb._fetch_html_json("https://x", var_name="rolling")
    assert out == {
        "windows": [{"label": "7", "rows": [{"name": "A"}]}],
        "meta": {"source": "fixture"},
    }


def test_fetch_html_json_brace_match_ignores_brackets_inside_strings(monkeypatch):
    html = (
        b"<script>let data = [{"
        b'"name":"A ] fake close",'
        b'"note":"escaped \\" quote and { brace",'
        b'"values":[1,2,3]'
        b"}];</script>"
    )
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: html)
    out = lb._fetch_html_json("https://x", var_name="data")
    assert out == [
        {
            "name": "A ] fake close",
            "note": 'escaped " quote and { brace',
            "values": [1, 2, 3],
        }
    ]


def test_fetch_html_json_missing_var_raises(monkeypatch):
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: b"<html></html>")
    with pytest.raises(SavantError, match="not found"):
        lb._fetch_html_json("https://x", var_name="data")


def test_fetch_html_json_invalid_json_raises(monkeypatch):
    monkeypatch.setattr(http, "request_bytes", lambda *a, **k: b"var data = ['x'];")
    with pytest.raises(SavantError, match="Failed to parse JSON"):
        lb._fetch_html_json("https://x", var_name="data")


def test_brace_match_unterminated_raises():
    with pytest.raises(SavantError, match="Unterminated"):
        lb._brace_match("[1, 2", 0, "[", "]")


#####################################################################
# Typed CSV leaderboard wrappers
#####################################################################


@pytest.mark.parametrize(
    ("func_name", "args", "kwargs", "expected"),
    [
        (
            "get_exit_velocity_barrels",
            (2024,),
            {"min_bbe": 25, "player_id": 1, "extra": "x"},
            {
                "name": "exit-velocity-barrels",
                "year": 2024,
                "player_id": 1,
                "params": {"type": "batter", "min_bbe": 25, "extra": "x"},
            },
        ),
        (
            "get_expected_statistics",
            (2024,),
            {"type": "pitcher", "min_pa": 50, "player_id": 2},
            {
                "name": "expected_statistics",
                "year": 2024,
                "player_id": 2,
                "params": {"type": "pitcher", "min_pa": 50},
            },
        ),
        (
            "get_bat_tracking",
            ((2025, 2023),),
            {"type": "league", "min_swings": "q", "player_id": 3},
            {
                "name": "bat-tracking",
                "year": (2025, 2023),
                "player_id": 3,
                "params": {"type": "league", "minSwings": "q"},
            },
        ),
        (
            "get_swing_path_attack_angle",
            (2024,),
            {"min_swings": 10, "player_id": 4},
            {
                "name": "bat-tracking/swing-path-attack-angle",
                "year": 2024,
                "player_id": 4,
                "params": {"type": "batter", "minSwings": 10},
            },
        ),
        (
            "get_swing_timing_miss_distance",
            ([2023, 2024],),
            {"min": 5, "player_id": 5},
            {
                "name": "bat-tracking/swing-timing-miss-distance",
                "year": [2023, 2024],
                "player_id": 5,
                "params": {"type": "batter", "min": 5},
            },
        ),
        (
            "get_batted_ball",
            (2024,),
            {"min_bbe": 40, "player_id": 6},
            {
                "name": "batted-ball",
                "year": 2024,
                "player_id": 6,
                "params": {"type": "batter", "min_bbe": 40},
            },
        ),
        (
            "get_pitch_arsenal_stats",
            (2024,),
            {"min_pa": 20, "pitch_type": "FF", "player_id": 7},
            {
                "name": "pitch-arsenal-stats",
                "year": 2024,
                "player_id": 7,
                "params": {"type": "pitcher", "min_pa": 20, "pitch_type": "FF"},
            },
        ),
        (
            "get_home_runs",
            (2024,),
            {"type": "pitcher", "player_id": 8},
            {
                "name": "home-runs",
                "year": 2024,
                "player_id": 8,
                "params": {"type": "pitcher"},
            },
        ),
        (
            "get_year_to_year",
            (2024,),
            {"year_pair": "2023-2024", "min_pa": 100, "player_id": 9},
            {
                "name": "statcast-year-to-year",
                "year": 2024,
                "player_id": 9,
                "params": {"type": "batter", "year_pair": "2023-2024", "min_pa": 100},
            },
        ),
        (
            "get_pitch_tempo",
            (2024,),
            {"min_pa": 20, "player_id": 10},
            {
                "name": "pitch-tempo",
                "year": 2024,
                "player_id": 10,
                "params": {"type": "pitcher", "min_pa": 20},
            },
        ),
        (
            "get_active_spin",
            (2024,),
            {"method": "observed", "min_pitches": 50, "player_id": 11},
            {
                "name": "active-spin",
                "year": "2024_observed",
                "player_id": 11,
                "params": {"min_pitches": 50},
            },
        ),
        (
            "get_pitch_movement",
            (2024, "FF"),
            {"pitcher_throws": "R", "min_pitches": 100, "player_id": 12},
            {
                "name": "pitch-movement",
                "year": 2024,
                "player_id": 12,
                "params": {
                    "pitch_type": "FF",
                    "pitcher_throws": "R",
                    "min_pitches": 100,
                },
            },
        ),
        (
            "get_pitch_arsenals",
            (2024,),
            {"min_pitches": 100, "player_id": 13},
            {
                "name": "pitch-arsenals",
                "year": 2024,
                "player_id": 13,
                "params": {"type": "pitcher", "min_pitches": 100},
            },
        ),
        (
            "get_spin_direction",
            (2024, "SL"),
            {"min_pitches": 30, "player_id": 14},
            {
                "name": "spin-direction-pitches",
                "year": 2024,
                "player_id": 14,
                "params": {"type": "pitcher", "pitch_type": "SL", "min_pitches": 30},
            },
        ),
        (
            "get_arm_angles",
            (2024,),
            {"min_pitches": 30, "player_id": 15},
            {
                "name": "pitcher-arm-angles",
                "year": 2024,
                "player_id": 15,
                "params": {"type": "pitcher", "min_pitches": 30},
            },
        ),
        (
            "get_pitcher_running_game",
            (2024,),
            {"min_attempts": 10, "player_id": 16},
            {
                "name": "pitcher-running-game",
                "year": 2024,
                "player_id": 16,
                "params": {"type": "pitcher", "min_attempts": 10},
            },
        ),
        (
            "get_outs_above_average",
            (2024,),
            {"position": "OF", "min_attempts": 25, "player_id": 17},
            {
                "name": "outs_above_average",
                "year": 2024,
                "player_id": 17,
                "params": {"type": "fielder", "position": "OF", "min_attempts": 25},
            },
        ),
        (
            "get_fielding_run_value",
            (2024,),
            {"position": "SS", "min_inn": 300, "player_id": 18},
            {
                "name": "fielding-run-value",
                "year": 2024,
                "player_id": 18,
                "params": {"type": "fielder", "position": "SS", "min_inn": 300},
            },
        ),
        (
            "get_catch_probability",
            (2024,),
            {
                "min_attempts": 25,
                "star_min": 1,
                "star_max": 5,
                "player_id": 19,
            },
            {
                "name": "catch-probability-alt",
                "year": 2024,
                "player_id": 19,
                "params": {
                    "type": "fielder",
                    "min_attempts": 25,
                    "star_min": 1,
                    "star_max": 5,
                },
            },
        ),
        (
            "get_directional_oaa",
            (2024,),
            {"position": "OF", "min_attempts": 25, "player_id": 20},
            {
                "name": "directional-oaa",
                "year": 2024,
                "player_id": 20,
                "params": {"position": "OF", "min_attempts": 25},
            },
        ),
        (
            "get_outfield_jump",
            (2024,),
            {"min_opportunities": 20, "player_id": 21},
            {
                "name": "outfield_jump",
                "year": 2024,
                "player_id": 21,
                "params": {"type": "fielder", "min_opportunities": 20},
            },
        ),
        (
            "get_arm_strength",
            (2024,),
            {"position": "OF", "min_throws": 20, "player_id": 22},
            {
                "name": "arm-strength",
                "year": 2024,
                "player_id": 22,
                "params": {"type": "fielder", "position": "OF", "min_throws": 20},
            },
        ),
        (
            "get_baserunning",
            (2024,),
            {"type": "Fld", "position": "OF", "min_opportunities": 20, "player_id": 23},
            {
                "name": "baserunning",
                "year": 2024,
                "player_id": 23,
                "params": {"type": "Fld", "position": "OF", "min_opportunities": 20},
            },
        ),
        (
            "get_catcher_framing",
            (2024,),
            {"min_pitches": 100, "player_id": 24},
            {
                "name": "catcher-framing",
                "year": 2024,
                "player_id": 24,
                "params": {"type": "catcher", "min_pitches": 100},
            },
        ),
        (
            "get_poptime",
            (2024,),
            {
                "min_attempts": 5,
                "exchange_min": 0.6,
                "exchange_max": 0.8,
                "player_id": 25,
            },
            {
                "name": "poptime",
                "year": 2024,
                "player_id": 25,
                "params": {
                    "type": "catcher",
                    "min_attempts": 5,
                    "exchange_min": 0.6,
                    "exchange_max": 0.8,
                },
            },
        ),
        (
            "get_catcher_blocking",
            (2024,),
            {"min_blocks": 50, "player_id": 26},
            {
                "name": "catcher-blocking",
                "year": 2024,
                "player_id": 26,
                "params": {"type": "catcher", "min_blocks": 50},
            },
        ),
        (
            "get_catcher_throwing",
            (2024,),
            {"min_attempts": 5, "player_id": 27},
            {
                "name": "catcher-throwing",
                "year": 2024,
                "player_id": 27,
                "params": {"type": "catcher", "min_attempts": 5},
            },
        ),
        (
            "get_catcher_stance",
            (2024,),
            {"min_pitches": 100, "player_id": 28},
            {
                "name": "catcher-stance",
                "year": 2024,
                "player_id": 28,
                "params": {"type": "catcher", "min_pitches": 100},
            },
        ),
        (
            "get_sprint_speed",
            (2024,),
            {"min_opportunities": 10, "player_id": 29},
            {
                "name": "sprint_speed",
                "year": 2024,
                "player_id": 29,
                "params": {"min_opportunities": 10},
            },
        ),
        (
            "get_running_splits",
            (2024,),
            {"min_opportunities": 10, "player_id": 30},
            {
                "name": "running-splits",
                "year": 2024,
                "player_id": 30,
                "params": {"min_opportunities": 10},
            },
        ),
        (
            "get_baserunning_run_value",
            (2024,),
            {"min_opportunities": 10, "player_id": 31},
            {
                "name": "baserunning-run-value",
                "year": 2024,
                "player_id": 31,
                "params": {"min_opportunities": 10},
            },
        ),
        (
            "get_basestealing_run_value",
            (2024,),
            {"min_attempts": 5, "player_id": 32},
            {
                "name": "basestealing-run-value",
                "year": 2024,
                "player_id": 32,
                "params": {"min_attempts": 5},
            },
        ),
        (
            "get_custom_leaderboard",
            (2024,),
            {"custom_col": "xwoba,barrels", "min_pa": 100, "player_id": 33},
            {
                "name": "custom",
                "year": 2024,
                "player_id": 33,
                "params": {
                    "type": "batter",
                    "custom_col": "xwoba,barrels",
                    "min_pa": 100,
                },
            },
        ),
        (
            "get_game_scores",
            (2024,),
            {"min_gs": 10, "player_id": 34},
            {
                "name": "game-scores",
                "year": 2024,
                "player_id": 34,
                "params": {"min_gs": 10},
            },
        ),
        (
            "get_abs_challenges",
            (2024,),
            {"player_id": 35, "foo": "bar"},
            {
                "name": "abs-challenges",
                "year": 2024,
                "player_id": 35,
                "params": {"foo": "bar"},
            },
        ),
        (
            "get_timer_infractions",
            (2024,),
            {"player_id": 36, "type": "batter", "foo": "bar"},
            {
                "name": "pitch-timer-infractions",
                "year": 2024,
                "player_id": 36,
                "params": {"foo": "bar"},
            },
        ),
        (
            "get_swing_take",
            (2024,),
            {"player_id": 37, "foo": "bar"},
            {
                "name": "swing-take",
                "year": 2024,
                "player_id": 37,
                "params": {"foo": "bar"},
            },
        ),
    ],
)
def test_typed_csv_wrappers_call_expected_leaderboard(
    monkeypatch, func_name, args, kwargs, expected
):
    calls = []

    def fake_fetch_leaderboard(name, year=None, player_id=None, **params):
        calls.append(
            {
                "name": name,
                "year": year,
                "player_id": player_id,
                "params": params,
            }
        )
        return [{"ok": "1"}]

    monkeypatch.setattr(lb, "fetch_leaderboard", fake_fetch_leaderboard)
    assert getattr(lb, func_name)(*args, **kwargs) == [{"ok": "1"}]
    assert calls == [expected]


#####################################################################
# HTML-backed leaderboard wrappers
#####################################################################


@pytest.mark.parametrize(
    ("func_name", "args", "kwargs", "expected_path", "expected_var", "expected_params"),
    [
        (
            "get_park_factors",
            (2024,),
            {},
            "/leaderboard/statcast-park-factors",
            "data",
            {
                "year": "2024",
                "type": "year",
                "bat_side": "R",
                "condition": "All",
                "stat": "index_wOBA",
            },
        ),
        (
            "get_hot_stove",
            (2024,),
            {"side": "pitcher"},
            "/leaderboard/hot-stove",
            "HOT_STOVE_PITCHER_DATA",
            {"year": "2024"},
        ),
        (
            "get_rolling_windows",
            (2024,),
            {"metric": "xwoba", "days": 30, "empty": None},
            "/leaderboard/rolling",
            "rolling",
            {"year": "2024", "metric": "xwoba", "days": "30"},
        ),
    ],
)
def test_html_backed_wrappers_call_expected_scraper(
    monkeypatch, func_name, args, kwargs, expected_path, expected_var, expected_params
):
    calls = []

    def fake_fetch_html_json(url, var_name="data", params=None, **kw):
        calls.append(
            {
                "url": url,
                "var_name": var_name,
                "params": params,
            }
        )
        return [{"ok": True}]

    monkeypatch.setattr(lb, "_fetch_html_json", fake_fetch_html_json)
    assert getattr(lb, func_name)(*args, **kwargs) == [{"ok": True}]
    assert calls == [
        {
            "url": f"{lb.BASE_URL}{expected_path}",
            "var_name": expected_var,
            "params": expected_params,
        }
    ]
