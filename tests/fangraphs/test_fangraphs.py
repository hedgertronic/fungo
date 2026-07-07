"""Offline tests for the FanGraphs module.

Transport is monkeypatched at ``fungo.http`` (the module object the fangraphs
layer routes through), so nothing here touches the network. Live coverage is
in ``test_live.py`` behind the ``live`` marker.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fungo import http
from fungo.exceptions import FangraphsError, RequestError, ValidationError
from fungo.fangraphs import api, guts, leaders, players, roster_resource

#####################################################################
# Helpers
#####################################################################


def _capture_json(monkeypatch, payload: Any) -> dict[str, Any]:
    """Patch ``http.request_json`` with a recorder returning ``payload``."""
    log: dict[str, Any] = {}

    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        log["url"] = url
        log["params"] = params
        log["headers"] = kw.get("headers")
        return payload

    monkeypatch.setattr(http, "request_json", fake)
    return log


def _capture_bytes(monkeypatch, body: bytes) -> dict[str, Any]:
    """Patch ``http.request_bytes`` with a recorder returning ``body``."""
    log: dict[str, Any] = {}

    def fake(url: str, params: Any = None, **kw: Any) -> bytes:
        log["url"] = url
        log["params"] = params
        log["headers"] = kw.get("headers")
        return body

    monkeypatch.setattr(http, "request_bytes", fake)
    return log


LEADERS_PAYLOAD = {"data": [{"PlayerName": "A", "WAR": 1.0}], "totalCount": 1}


#####################################################################
# api: User-Agent and 403 handling
#####################################################################


def test_fg_json_sends_okhttp_user_agent(monkeypatch):
    log = _capture_json(monkeypatch, {})
    api.fg_json("/api/x")
    assert log["headers"] == {"User-Agent": api.FG_USER_AGENT}
    assert api.FG_USER_AGENT.startswith("okhttp/")
    assert log["url"] == f"{api.BASE_URL}/api/x"


def test_fg_json_403_raises_fangraphs_error(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        raise RequestError(f"HTTP 403 for {url}: Forbidden")

    monkeypatch.setattr(http, "request_json", fake)
    with pytest.raises(FangraphsError, match="okhttp"):
        api.fg_json("/api/x")


def test_fg_json_other_errors_propagate(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        raise RequestError(f"HTTP 500 for {url}")

    monkeypatch.setattr(http, "request_json", fake)
    with pytest.raises(RequestError):
        api.fg_json("/api/x")


def test_fg_json_post_403_raises_fangraphs_error(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        raise RequestError(f"HTTP 403 for {url}: Forbidden")

    monkeypatch.setattr(http, "request_json", fake)
    with pytest.raises(FangraphsError, match="okhttp"):
        api.fg_json_post("/api/x", {"key": "val"})


def test_fg_json_post_other_errors_propagate(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        raise RequestError(f"HTTP 500 for {url}")

    monkeypatch.setattr(http, "request_json", fake)
    with pytest.raises(RequestError):
        api.fg_json_post("/api/x", {"key": "val"})


def test_fg_html_success_decodes_response(monkeypatch):
    _capture_bytes(monkeypatch, b"<html>ok</html>")
    assert api.fg_html("/guts.aspx") == "<html>ok</html>"


def test_fg_html_403_raises_fangraphs_error(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> bytes:
        raise RequestError(f"HTTP 403 for {url}: Forbidden")

    monkeypatch.setattr(http, "request_bytes", fake)
    with pytest.raises(FangraphsError, match="okhttp"):
        api.fg_html("/guts.aspx")


def test_fg_html_other_errors_propagate(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> bytes:
        raise RequestError(f"HTTP 500 for {url}")

    monkeypatch.setattr(http, "request_bytes", fake)
    with pytest.raises(RequestError):
        api.fg_html("/guts.aspx")


def test_fg_page_data_403_raises_fangraphs_error(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> bytes:
        raise RequestError(f"HTTP 403 for {url}: Forbidden")

    monkeypatch.setattr(http, "request_bytes", fake)
    with pytest.raises(FangraphsError, match="okhttp"):
        api.fg_page_data("/some/page")


def test_fg_page_data_other_errors_propagate(monkeypatch):
    def fake(url: str, params: Any = None, **kw: Any) -> bytes:
        raise RequestError(f"HTTP 500 for {url}")

    monkeypatch.setattr(http, "request_bytes", fake)
    with pytest.raises(RequestError):
        api.fg_page_data("/some/page")


def test_fg_page_data_invalid_json_raises(monkeypatch):
    _capture_bytes(
        monkeypatch,
        b'<script id="__NEXT_DATA__" type="application/json">not-valid-json</script>',
    )
    with pytest.raises(FangraphsError, match="Unparseable"):
        api.fg_page_data("/some/page")


def test_fg_page_data_extracts_next_data(monkeypatch):
    blob = {"props": {"pageProps": {"x": 1}}}
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(blob)
        + "</script></body></html>"
    )
    _capture_bytes(monkeypatch, html.encode())
    assert api.fg_page_data("/some/page") == blob


def test_fg_page_data_missing_blob_raises(monkeypatch):
    _capture_bytes(monkeypatch, b"<html><body>no data here</body></html>")
    with pytest.raises(FangraphsError, match="__NEXT_DATA__"):
        api.fg_page_data("/some/page")


#####################################################################
# leaders: param emission
#####################################################################


def test_fetch_leaders_inverts_season_params(monkeypatch):
    log = _capture_json(monkeypatch, LEADERS_PAYLOAD)
    leaders.fetch_leaders("bat", 2023, 2025)
    # FanGraphs: season = END year, season1 = START year.
    assert log["params"]["season"] == 2025
    assert log["params"]["season1"] == 2023


def test_fetch_leaders_single_season_fills_both(monkeypatch):
    log = _capture_json(monkeypatch, LEADERS_PAYLOAD)
    leaders.fetch_leaders("pit", start_season=2024)
    assert log["params"]["season"] == 2024
    assert log["params"]["season1"] == 2024


def test_fetch_leaders_minor_league_endpoint(monkeypatch):
    log = _capture_json(monkeypatch, LEADERS_PAYLOAD)
    leaders.fetch_leaders("bat", 2024, league="minor")
    assert "/api/leaders/minor-league/data" in log["url"]


def test_fetch_leaders_requires_a_season():
    with pytest.raises(ValidationError):
        leaders.fetch_leaders("bat")


def test_fetch_leaders_unknown_stats_group():
    with pytest.raises(ValidationError, match="bat"):
        leaders.fetch_leaders("batt", 2024)


def test_get_leaders_returns_rows(monkeypatch):
    _capture_json(monkeypatch, LEADERS_PAYLOAD)
    rows = leaders.get_leaders("bat", 2024)
    assert rows == LEADERS_PAYLOAD["data"]


def test_get_splits_emits_handedness_month(monkeypatch):
    log = _capture_json(monkeypatch, LEADERS_PAYLOAD)
    leaders.get_splits("pit", 2024, "vs_lhp")
    assert log["params"]["month"] == 13


def test_get_splits_unknown_split():
    with pytest.raises(ValidationError, match="vs_lhp"):
        leaders.get_splits("pit", 2024, "vs_lhP")


def test_fetch_leaders_unknown_league():
    with pytest.raises(ValidationError, match="major"):
        leaders.fetch_leaders("bat", 2024, league="aaa")


def test_fetch_leaders_extra_params_merged(monkeypatch):
    log = _capture_json(monkeypatch, LEADERS_PAYLOAD)
    leaders.fetch_leaders("bat", 2024, extra_params={"custom_key": "x"})
    assert log["params"]["custom_key"] == "x"


def test_fetch_leaders_bad_payload_raises(monkeypatch):
    _capture_json(monkeypatch, [1, 2, 3])  # list, not the expected dict
    with pytest.raises(FangraphsError, match="Unexpected leaders payload"):
        leaders.fetch_leaders("bat", 2024)


def test_get_leaders_data_not_list_raises(monkeypatch):
    _capture_json(monkeypatch, {"data": {"key": "val"}, "totalCount": 0})
    with pytest.raises(FangraphsError, match="Expected a list"):
        leaders.get_leaders("bat", 2024)


#####################################################################
# players
#####################################################################


def test_get_player_stats_params(monkeypatch):
    log = _capture_json(monkeypatch, {"playerInfo": {}, "data": []})
    players.get_player_stats(15640, "OF")
    assert log["params"] == {"playerid": 15640, "position": "OF"}
    assert "/api/players/stats" in log["url"]


def test_get_game_log_omits_season_when_none(monkeypatch):
    log = _capture_json(monkeypatch, {"mlb": []})
    players.get_game_log("sa917940", log_type=-1)
    assert "season" not in log["params"]
    assert log["params"]["type"] == -1


def test_get_player_stats_bad_payload_raises(monkeypatch):
    _capture_json(monkeypatch, [1, 2])  # list, not the expected dict
    with pytest.raises(FangraphsError, match="Unexpected player stats payload"):
        players.get_player_stats(15640)


def test_get_game_log_with_season_includes_season(monkeypatch):
    log = _capture_json(monkeypatch, {"mlb": []})
    players.get_game_log(15640, 2024)
    assert log["params"]["season"] == 2024


def test_get_game_log_bad_payload_raises(monkeypatch):
    _capture_json(monkeypatch, [1, 2])  # list, not the expected dict
    with pytest.raises(FangraphsError, match="Unexpected game log payload"):
        players.get_game_log(15640)


#####################################################################
# guts: stdlib HTML table parsing
#####################################################################

GUTS_HTML = """
<html><body><div class="table-scroll"><table>
<thead><tr><th>Season</th><th>wOBA</th><th>cFIP</th></tr></thead>
<tbody>
<tr><td>2026</td><td>.317</td><td>3.110</td></tr>
<tr><td>2025</td><td>.310</td><td>3.255</td></tr>
</tbody>
</table></div></body></html>
"""


def test_guts_constants_parses_table(monkeypatch):
    _capture_bytes(monkeypatch, GUTS_HTML.encode())
    rows = guts.get_guts_constants()
    assert rows == [
        {"Season": "2026", "wOBA": ".317", "cFIP": "3.110"},
        {"Season": "2025", "wOBA": ".310", "cFIP": "3.255"},
    ]


def test_guts_missing_table_raises(monkeypatch):
    _capture_bytes(monkeypatch, b"<html><body><p>maintenance</p></body></html>")
    with pytest.raises(FangraphsError, match="No Guts table"):
        guts.get_guts_constants()


def test_park_factors_params(monkeypatch):
    log = _capture_bytes(monkeypatch, GUTS_HTML.encode())
    guts.get_park_factors(2025)
    assert log["params"] == {"type": "pf", "teamid": 0, "season": 2025}


def test_park_factors_by_handedness_params(monkeypatch):
    log = _capture_bytes(monkeypatch, GUTS_HTML.encode())
    guts.get_park_factors_by_handedness(2025)
    assert log["params"] == {"type": "pfh", "teamid": 0, "season": 2025}


#####################################################################
# roster resource: dehydrated-state walking
#####################################################################


def _rr_html(data: Any) -> bytes:
    blob = {
        "props": {
            "pageProps": {"dehydratedState": {"queries": [{"state": {"data": data}}]}}
        }
    }
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(blob)
        + "</script>"
    ).encode()


def test_get_depth_chart_returns_query_data(monkeypatch):
    payload = {"dataRoster": [{"player": "X"}], "dataLineups": []}
    log = _capture_bytes(monkeypatch, _rr_html(payload))
    assert roster_resource.get_depth_chart("rangers") == payload
    assert "/roster-resource/depth-charts/rangers" in log["url"]


def test_get_roster_resource_no_queries_raises(monkeypatch):
    _capture_bytes(
        monkeypatch,
        b'<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>',
    )
    with pytest.raises(FangraphsError, match="dehydrated"):
        roster_resource.get_roster_resource("payroll")


def test_get_roster_resource_non_dict_data_raises(monkeypatch):
    blob = {
        "props": {
            "pageProps": {
                "dehydratedState": {"queries": [{"state": {"data": [1, 2, 3]}}]}
            }
        }
    }
    _capture_bytes(
        monkeypatch,
        (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(blob)
            + "</script>"
        ).encode(),
    )
    with pytest.raises(FangraphsError, match="Unexpected RosterResource"):
        roster_resource.get_roster_resource("payroll")


#####################################################################
# splits leaderboards (POST)
#####################################################################


def _capture_post(monkeypatch, payload: Any) -> dict[str, Any]:
    """Patch ``http.request_json`` capturing the POST body."""
    log: dict[str, Any] = {}

    def fake(url: str, params: Any = None, **kw: Any) -> Any:
        log["url"] = url
        log["headers"] = kw.get("headers")
        log["body"] = json.loads(kw["data"].decode())
        return payload

    monkeypatch.setattr(http, "request_json", fake)
    return log


SPLITS_PAYLOAD = {"data": [{"playerName": "A", "wOBA": 0.4}], "k": [], "v": []}


def test_split_leaders_body_construction(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    rows = splits.get_split_leaders("B", 2025, ["vs_lhp", 90])
    assert rows == SPLITS_PAYLOAD["data"]
    assert log["url"].endswith("/api/leaders/splits/splits-leaders")
    assert log["headers"]["Content-Type"] == "application/json"
    body = log["body"]
    assert body["strSplitArr"] == [1, 90]  # name resolved + raw int passthrough
    assert body["strPosition"] == "B"
    assert body["strType"] == "2"  # advanced default
    assert body["strStartDate"] == "2025-03-01"
    assert body["strEndDate"] == "2025-11-30"


def test_split_leaders_unknown_split_name(monkeypatch):
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError, match="vs_lhp"):
        splits.get_split_leaders("B", 2025, ["vs_LHP"])


def test_split_leaders_requires_season_or_dates():
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError):
        splits.get_split_leaders("P")


def test_split_leaders_explicit_dates_override_season(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders(
        "P", start_date="2025-06-01", end_date="2025-06-30", splits=["vs_lhh"]
    )
    assert log["body"]["strStartDate"] == "2025-06-01"
    assert log["body"]["strSplitArr"] == [5]


def test_split_leaders_home_resolves_by_position(monkeypatch):
    from fungo.fangraphs import splits

    log_b = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, ["home"])
    assert log_b["body"]["strSplitArr"] == [7]  # batter home

    log_p = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("P", 2025, ["home"])
    assert log_p["body"]["strSplitArr"] == [9]  # pitcher home


def test_split_leaders_away_resolves_by_position(monkeypatch):
    from fungo.fangraphs import splits

    log_b = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, ["away"])
    assert log_b["body"]["strSplitArr"] == [8]  # batter away

    log_p = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("P", 2025, ["away"])
    assert log_p["body"]["strSplitArr"] == [10]  # pitcher away


def test_split_leaders_accepts_bare_scalars(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, "home", pitch_splits="fourseam")
    assert log["body"]["strSplitArr"] == [7]
    assert log["body"]["strSplitArrPitch"] == [1]

    log_int = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, 59, pitch_splits=111)
    assert log_int["body"]["strSplitArr"] == [59]
    assert log_int["body"]["strSplitArrPitch"] == [111]


def test_split_leaders_unknown_pitch_split_name():
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError, match="fourseam"):
        splits.get_split_leaders("B", 2025, pitch_splits=["fastball"])


def test_split_leaders_pitch_splits_name_resolution(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, pitch_splits=["fourseam", "count_3_2"])
    assert log["body"]["strSplitArrPitch"] == [1, 111]


def test_split_leaders_pitch_splits_raw_int_passthrough(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("P", 2025, pitch_splits=[6, 100])
    assert log["body"]["strSplitArrPitch"] == [6, 100]


def test_split_leaders_bad_position():
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError, match="B"):
        splits.get_split_leaders("X", 2025)


def test_split_leaders_bad_stat_group():
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError, match="advanced"):
        splits.get_split_leaders("B", 2025, stat_group="invalid_group")


def test_split_leaders_bad_stat_type():
    from fungo.fangraphs import splits

    with pytest.raises(ValidationError, match="player"):
        splits.get_split_leaders("B", 2025, stat_type="invalid_type")


def test_split_leaders_extra_body_merged(monkeypatch):
    from fungo.fangraphs import splits

    log = _capture_post(monkeypatch, SPLITS_PAYLOAD)
    splits.get_split_leaders("B", 2025, extra_body={"custom_field": "cv"})
    assert log["body"]["custom_field"] == "cv"


def test_split_leaders_bad_payload_raises(monkeypatch):
    from fungo.fangraphs import splits

    _capture_post(monkeypatch, [1, 2, 3])  # list, not the expected dict
    with pytest.raises(FangraphsError, match="Unexpected splits payload"):
        splits.get_split_leaders("B", 2025)


def test_split_leaders_data_not_list_raises(monkeypatch):
    from fungo.fangraphs import splits

    _capture_post(monkeypatch, {"data": {"player": "X"}, "k": [], "v": []})
    with pytest.raises(FangraphsError, match="Expected a list"):
        splits.get_split_leaders("B", 2025)


def test_split_code_table_length():
    from fungo.fangraphs.splits import SPLIT_CODE_TABLE

    assert len(SPLIT_CODE_TABLE) == 292


def test_pitch_split_code_table_length():
    from fungo.fangraphs.splits import PITCH_SPLIT_CODE_TABLE

    assert len(PITCH_SPLIT_CODE_TABLE) == 47


def test_split_code_table_anchors():
    from fungo.fangraphs.splits import SPLIT_CODE_TABLE

    assert "Scoring" in SPLIT_CODE_TABLE[59]  # RISP
    assert "Night" in SPLIT_CODE_TABLE[91]
    assert SPLIT_CODE_TABLE[7] != SPLIT_CODE_TABLE[9]  # home codes disambiguated
    assert "batters" in SPLIT_CODE_TABLE[7]
    assert "pitchers" in SPLIT_CODE_TABLE[9]


def test_split_codes_leaves_in_table():
    from fungo.fangraphs.splits import SPLIT_CODE_TABLE, SPLIT_CODES

    for key, val in SPLIT_CODES.items():
        if isinstance(val, dict):
            for code in val.values():
                assert code in SPLIT_CODE_TABLE, f"{key} -> {code} not in table"
        else:
            assert val in SPLIT_CODE_TABLE, f"{key} -> {val} not in table"


#####################################################################
# projections
#####################################################################


def test_get_projections_params(monkeypatch):
    from fungo.fangraphs import projections

    log = _capture_json(monkeypatch, [{"PlayerName": "A", "WAR": 5.0}])
    rows = projections.get_projections("zips", "pit")
    assert rows == [{"PlayerName": "A", "WAR": 5.0}]
    assert "/api/projections" in log["url"]
    assert log["params"]["type"] == "zips"
    assert log["params"]["stats"] == "pit"


def test_get_projections_unknown_system():
    from fungo.fangraphs import projections

    with pytest.raises(ValidationError, match="steamer"):
        projections.get_projections("steamers")


def test_get_projections_wrapped_payload_raises(monkeypatch):
    from fungo.fangraphs import projections

    _capture_json(monkeypatch, {"data": []})  # dict, not the expected bare list
    with pytest.raises(FangraphsError, match="Unexpected projections"):
        projections.get_projections()


def test_get_projections_bad_stats_group():
    from fungo.fangraphs import projections

    with pytest.raises(ValidationError, match="bat"):
        projections.get_projections("steamer", "batting")


def test_get_projections_extra_params_merged(monkeypatch):
    from fungo.fangraphs import projections

    log = _capture_json(monkeypatch, [])
    projections.get_projections("steamer", extra_params={"foo": "bar"})
    assert log["params"]["foo"] == "bar"


#####################################################################
# prospects: THE BOARD
#####################################################################


def test_get_prospect_board_params(monkeypatch):
    from fungo.fangraphs import prospects

    log = _capture_json(monkeypatch, {"data": []})
    prospects.get_prospect_board(2025)
    assert "/api/prospects/board/data" in log["url"]
    assert log["params"]["draft"] == "2025prospect"
    assert log["params"]["season"] == 2025
