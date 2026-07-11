"""Offline tests for the ``fungo`` CLI.

Underlying library functions are monkeypatched in the ``fungo.cli`` namespace,
so nothing here touches the network. Each test exercises rendering, format
defaults, passthrough parsing, or dispatch — never live data.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from fungo import cli

#####################################################################
# Fixtures / helpers
#####################################################################

ROWS: list[dict[str, Any]] = [
    {"player_id": "1", "name": "A", "velo": "95"},
    {"player_id": "2", "name": "B", "velo": "97"},
]


def _capture(monkeypatch, name: str) -> dict[str, Any]:
    """Patch ``cli.<name>`` with a recorder returning ``ROWS``; return the call log."""
    log: dict[str, Any] = {}

    def fake(*args: Any, **kwargs: Any) -> list[dict]:
        log["args"] = args
        log["kwargs"] = kwargs
        return ROWS

    monkeypatch.setattr(cli, name, fake)
    return log


#####################################################################
# Rendering
#####################################################################


def test_csv_rendering(monkeypatch, capsys):
    _capture(monkeypatch, "lookup")
    assert cli.main(["lookup", "--name", "trout"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "player_id,name,velo"
    assert out[1] == "1,A,95"
    assert out[2] == "2,B,97"


def test_json_rendering(monkeypatch, capsys):
    _capture(monkeypatch, "lookup")
    cli.main(["lookup", "--name", "trout", "--format", "json"])
    assert json.loads(capsys.readouterr().out) == ROWS


def test_csv_fieldnames_union(monkeypatch, capsys):
    def fake(*a: Any, **k: Any) -> list[dict]:
        return [{"x": "1"}, {"x": "2", "y": "3"}]

    monkeypatch.setattr(cli, "lookup", fake)
    cli.main(["lookup"])
    header = capsys.readouterr().out.splitlines()[0]
    assert header == "x,y"


def test_empty_list_notes_stderr(monkeypatch, capsys):
    monkeypatch.setattr(cli, "lookup", lambda *a, **k: [])
    cli.main(["lookup"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no rows" in captured.err


#####################################################################
# Format defaults
#####################################################################


def test_search_default_format_is_csv(monkeypatch, capsys):
    _capture(monkeypatch, "search_pitches")
    cli.main(["search", "--start", "2024-04-01", "--end", "2024-04-01"])
    assert capsys.readouterr().out.splitlines()[0] == "player_id,name,velo"


def test_mlb_default_format_is_json(monkeypatch, capsys):
    monkeypatch.setattr(cli.mlb, "get_person", lambda **k: {"id": 1, "name": "X"})
    monkeypatch.setattr(cli.mlb, "__all__", ["get_person"])
    cli.main(["mlb", "get_person", "--person-id", "545361"])
    assert json.loads(capsys.readouterr().out) == {"id": 1, "name": "X"}


#####################################################################
# Argument parsing
#####################################################################


def test_season_comma_list_parsed(monkeypatch):
    log = _capture(monkeypatch, "get_leaderboard")
    cli.main(["leaderboard", "bat-tracking", "--season", "2023,2024"])
    assert log["kwargs"]["year"] == [2023, 2024]


def test_season_single_is_int(monkeypatch):
    log = _capture(monkeypatch, "get_leaderboard")
    cli.main(["leaderboard", "exit-velocity-barrels", "--season", "2024"])
    assert log["kwargs"]["year"] == 2024


def test_search_passthrough_pipe_joined(monkeypatch):
    log = _capture(monkeypatch, "search_pitches")
    cli.main(
        [
            "search",
            "--start",
            "2024-04-01",
            "--end",
            "2024-04-01",
            "--pitch-type",
            "FF,SL",
        ]
    )
    # comma -> pipe, and key dash -> underscore
    assert log["kwargs"]["pitch_type"] == "FF|SL"


def test_search_passthrough_equals_form(monkeypatch):
    log = _capture(monkeypatch, "search_pitches")
    cli.main(
        ["search", "--start", "2024-04-01", "--end", "2024-04-01", "--hfTeam=LAD|"]
    )
    assert log["kwargs"]["hfTeam"] == "LAD|"


def test_search_passthrough_malformed_token_errors():
    with pytest.raises(SystemExit, match="unexpected argument"):
        cli.main(["search", "--start", "2024-04-01", "--end", "2024-04-01", "oops"])


def test_search_passthrough_missing_value_errors():
    with pytest.raises(SystemExit, match="missing value"):
        cli.main(["search", "--start", "2024-04-01", "--end", "2024-04-01", "--hfTeam"])


def test_leaderboard_passthrough_not_pipe_joined(monkeypatch):
    log = _capture(monkeypatch, "get_leaderboard")
    cli.main(["leaderboard", "custom", "--season", "2024", "--custom-col", "a,b,c"])
    # leaderboard passthrough is verbatim (no pipe-join)
    assert log["kwargs"]["custom_col"] == "a,b,c"


def test_lookup_rejects_passthrough_extras(monkeypatch):
    _capture(monkeypatch, "lookup")
    with pytest.raises(SystemExit, match="unexpected arguments"):
        cli.main(["lookup", "--name", "trout", "--extra-filter", "x"])


def test_leaderboard_missing_slug_errors():
    with pytest.raises(SystemExit, match="slug is required"):
        cli.main(["leaderboard"])


def test_leaderboard_type_and_player_id(monkeypatch):
    log = _capture(monkeypatch, "get_leaderboard")
    cli.main(
        [
            "leaderboard",
            "bat-tracking",
            "--type",
            "batter",
            "--player-id",
            "545361",
        ]
    )
    assert log["kwargs"]["type"] == "batter"
    assert log["kwargs"]["player_id"] == "545361"


def test_mlb_passthrough_verbatim(monkeypatch):
    log: dict[str, Any] = {}
    monkeypatch.setattr(
        cli.mlb,
        "get_people",
        lambda **k: log.update(k) or {"ok": True},
    )
    monkeypatch.setattr(cli.mlb, "__all__", ["get_people"])
    cli.main(["mlb", "get_people", "--person-ids=605151,592450"])
    assert log["person_ids"] == "605151,592450"


#####################################################################
# Errors and listing
#####################################################################


def test_csv_on_nested_dict_errors(monkeypatch):
    monkeypatch.setattr(cli.mlb, "get_person", lambda **k: {"id": 1})
    monkeypatch.setattr(cli.mlb, "__all__", ["get_person"])
    with pytest.raises(SystemExit, match="json"):
        cli.main(["mlb", "get_person", "--format", "csv"])


def test_mlb_unknown_function_errors():
    with pytest.raises(SystemExit, match="unknown function"):
        cli.main(["mlb", "not_a_real_function"])


def test_mlb_missing_function_errors():
    with pytest.raises(SystemExit, match="function name is required"):
        cli.main(["mlb"])


def test_fungo_error_reported_cleanly(monkeypatch, capsys):
    # A FungoError from the library is caught at the main() boundary: clean
    # one-line `error:` on stderr + exit 1, no traceback.
    from fungo.exceptions import ValidationError

    def boom(*a: Any, **k: Any) -> list[dict]:
        raise ValidationError("nope", "slug")

    monkeypatch.setattr(cli, "get_leaderboard", boom)
    assert cli.main(["leaderboard", "nope"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")


def test_unexpected_exception_propagates(monkeypatch):
    # A non-FungoError (a real bug) is NOT swallowed — it surfaces a traceback.
    def boom(*a: Any, **k: Any) -> list[dict]:
        raise KeyError("bug")

    monkeypatch.setattr(cli, "lookup", boom)
    with pytest.raises(KeyError):
        cli.main(["lookup", "--name", "x"])


def test_leaderboard_list(capsys):
    assert cli.main(["leaderboard", "--list"]) == 0
    out = capsys.readouterr().out
    assert "slug" in out
    assert "bat-tracking" in out


def test_mlb_list(capsys):
    assert cli.main(["mlb", "--list"]) == 0
    out = capsys.readouterr().out
    assert "function" in out
    assert "get_person" in out


#####################################################################
# Output file
#####################################################################


def test_output_to_file(monkeypatch, tmp_path):
    _capture(monkeypatch, "lookup")
    target = tmp_path / "out.csv"
    cli.main(["lookup", "--name", "x", "-o", str(target)])
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "player_id,name,velo"
    assert "1,A,95" in text


#####################################################################
# fangraphs / bbref subcommands
#####################################################################


def test_fangraphs_list(capsys):
    assert cli.main(["fangraphs", "--list"]) == 0
    out = capsys.readouterr().out
    assert "get_leaders" in out
    # Non-callable __all__ entries (STAT_GROUPS, SPLIT_MONTHS) are excluded.
    assert "STAT_GROUPS" not in out


def test_bbref_list(capsys):
    assert cli.main(["bbref", "--list"]) == 0
    out = capsys.readouterr().out
    assert "get_player" in out
    assert "get_war_daily" in out


def test_fangraphs_dispatch_and_json_default(monkeypatch, capsys):
    def fake(**kwargs: Any) -> list[dict]:
        assert kwargs == {"stats": "pit", "start_season": "2025"}
        return ROWS

    monkeypatch.setattr(cli.fangraphs, "get_leaders", fake)
    argv = ["fangraphs", "get_leaders", "--stats=pit", "--start-season=2025"]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == ROWS


def test_fangraphs_unknown_function_exits():
    with pytest.raises(SystemExit, match="unknown function"):
        cli.main(["fangraphs", "get_nonsense"])


def test_fangraphs_non_callable_all_entry_exits():
    with pytest.raises(SystemExit, match="unknown function"):
        cli.main(["fangraphs", "STAT_GROUPS"])


def test_bbref_dispatch(monkeypatch, capsys):
    def fake(**kwargs: Any) -> list[dict]:
        assert kwargs == {"bbref_id": "troutmi01"}
        return ROWS

    monkeypatch.setattr(cli.bbref, "get_player", fake)
    assert cli.main(["bbref", "get_player", "--bbref-id=troutmi01"]) == 0
    assert json.loads(capsys.readouterr().out) == ROWS


def test_retrosheet_list(capsys):
    assert cli.main(["retrosheet", "--list"]) == 0
    out = capsys.readouterr().out
    assert "get_game_logs" in out
    assert "get_plays" in out
    # Non-callable __all__ entries (the field constants) are excluded.
    assert "GAME_LOG_FIELDS" not in out


def test_lahman_list(capsys):
    assert cli.main(["lahman", "--list"]) == 0
    out = capsys.readouterr().out
    assert "get_table" in out
    assert "list_tables" in out


def test_retrosheet_dispatch_and_csv_default(monkeypatch, capsys):
    def fake(**kwargs: Any) -> list[dict]:
        assert kwargs == {"year": "2024"}
        return ROWS

    monkeypatch.setattr(cli.retrosheet, "get_game_logs", fake)
    assert cli.main(["retrosheet", "get_game_logs", "--year=2024"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "player_id,name,velo"


def test_bool_extras_coerce_for_bool_annotated_params(monkeypatch):
    seen: dict[str, Any] = {}

    def fake(*, force_refresh: bool = False) -> list[dict]:
        seen["force_refresh"] = force_refresh
        return ROWS

    monkeypatch.setattr(cli.retrosheet, "get_biofile", fake)
    assert cli.main(["retrosheet", "get_biofile", "--force-refresh=false"]) == 0
    assert seen["force_refresh"] is False  # the bool-annotated param gets a bool
    assert cli.main(["retrosheet", "get_biofile", "--force-refresh=true"]) == 0
    assert seen["force_refresh"] is True


def test_bool_extras_invalid_value_errors(monkeypatch):
    def fake(*, force_refresh: bool = False) -> list[dict]:
        return ROWS

    monkeypatch.setattr(cli.retrosheet, "get_biofile", fake)
    with pytest.raises(SystemExit, match="expects true/false"):
        cli.main(["retrosheet", "get_biofile", "--force-refresh=maybe"])


def test_unknown_extra_arg_errors_cleanly(monkeypatch):
    # The param is optional so the bind failure is the typo itself (bind
    # reports a missing required argument before an unexpected one).
    def fake(*, year: int | str = 2024) -> list[dict]:
        return ROWS

    monkeypatch.setattr(cli.retrosheet, "get_game_logs", fake)
    with pytest.raises(SystemExit, match="unexpected keyword argument 'yeear'"):
        cli.main(["retrosheet", "get_game_logs", "--yeear=2024"])


def test_missing_required_arg_errors_cleanly():
    # Bind-checked against the real lahman.get_table signature; the check
    # fails before dispatch, so no network is touched.
    with pytest.raises(SystemExit, match="missing a required argument: 'name'"):
        cli.main(["lahman", "get_table"])


def test_bool_strings_pass_through_for_non_bool_params(monkeypatch, capsys):
    # "true" as a value for a non-bool parameter stays a string.
    def fake(**kwargs: Any) -> list[dict]:
        assert kwargs == {"name": "true"}
        return ROWS

    monkeypatch.setattr(cli.lahman, "get_table", fake)
    assert cli.main(["lahman", "get_table", "--name=true"]) == 0


def test_lahman_dispatch_and_csv_default(monkeypatch, capsys):
    def fake(**kwargs: Any) -> list[dict]:
        assert kwargs == {"name": "Batting"}
        return ROWS

    monkeypatch.setattr(cli.lahman, "get_table", fake)
    assert cli.main(["lahman", "get_table", "--name=Batting"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "player_id,name,velo"
