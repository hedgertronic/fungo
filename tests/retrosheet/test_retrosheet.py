"""Offline tests for fungo.retrosheet.

Mocks fungo.http.request_bytes (patched on the http module, as
tests/test_lookup.py does) with small synthetic zips built via zipfile +
io.BytesIO, and redirects the cache to a tmp dir so the real
~/.cache/fungo/retrosheet is never touched.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from fungo import http, retrosheet
from fungo.exceptions import RequestError, ValidationError
from fungo.retrosheet import files as files_mod

#####################################################################
# Synthetic fixtures
#####################################################################

SEASON_TABLES = (
    "gameinfo",
    "teamstats",
    "batting",
    "pitching",
    "fielding",
    "allplayers",
    "plays",
)


def _zip_bytes(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buf.getvalue()


def _game_log_text(n_rows: int = 2) -> str:
    # Headerless positional CSV, 161 fields per record (glfields.txt).
    buf = io.StringIO()
    writer = csv.writer(buf)
    for i in range(n_rows):
        record = [f"v{i}_{j}" for j in range(161)]
        record[0] = "20240320"
        record[3] = "LAN"
        writer.writerow(record)
    return buf.getvalue()


_SCHEDULE_HEADER = (
    "Date,Num,Day,Visitor,League,Game,Home,League,Game,"
    "Day/Night,Location,Postponed,Makeup"
)
_SCHEDULE_ROWS = (
    "20260325,0,Wednesday,NYA,AL,1,SFN,NL,1,d,SFO03,,\n"
    "20260326,0,Thursday,NYA,AL,2,SFN,NL,2,n,SFO03,,\n"
)
_SCHEDULE_TEXT = f"{_SCHEDULE_HEADER}\n{_SCHEDULE_ROWS}"

_PLAYS_TEXT = "gid,event,inning,batter\nSDN202403200,W,1,bettm001\n"

_BIOFILE_MEMBERS = {
    "biofile.csv": ('PLAYERID,LAST,FIRST\n"aardd001","Aardsma","David Allan"\n'),
    "biofile0.csv": "id,lastname,usename\naardd001,Aardsma,David\n",
    "coaches.csv": (
        "id,year,team,role,start,end\naarot101,1979,ATL,C,04/06/1979,09/30/1979\n"
    ),
    "relatives.csv": "id1,relation,id2\naaroh101,Brother,aarot101\n",
}


def _fake_zip_for(url: str) -> bytes:
    if "/gamelogs/gl" in url:
        return _zip_bytes({"gl2024.txt": _game_log_text()})
    if "/downloads/plays/" in url:
        return _zip_bytes({"2024plays.csv": _PLAYS_TEXT})
    if "SKED.zip" in url:
        return _zip_bytes({"2026schedule.csv": _SCHEDULE_TEXT})
    if "biofile.zip" in url:
        return _zip_bytes(_BIOFILE_MEMBERS)
    if "csvs.zip" in url:
        return _zip_bytes(
            {
                f"2024{table}.csv": f"gid,id\nSDN202403200,{table}\n"
                for table in SEASON_TABLES
            }
        )
    raise AssertionError(f"unexpected URL: {url}")


@pytest.fixture
def mock_retrosheet(monkeypatch, tmp_path):
    """Redirect the cache to tmp and serve synthetic zips, recording URLs."""
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path / "retrosheet")

    calls: list[str] = []

    def fake_request_bytes(url, params=None, **kw):
        calls.append(url)
        return _fake_zip_for(url)

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    return calls


#####################################################################
# Field constants
#####################################################################


def test_game_log_fields_shape():
    assert len(retrosheet.GAME_LOG_FIELDS) == 161
    assert len(set(retrosheet.GAME_LOG_FIELDS)) == 161
    assert retrosheet.GAME_LOG_FIELDS[0] == "date"
    assert retrosheet.GAME_LOG_FIELDS[-1] == "acquisition_info"


def test_schedule_fields_shape():
    assert len(retrosheet.SCHEDULE_FIELDS) == 13
    assert len(set(retrosheet.SCHEDULE_FIELDS)) == 13


#####################################################################
# Game logs
#####################################################################


def test_get_game_logs_zips_field_constant(mock_retrosheet):
    rows = retrosheet.get_game_logs(2024)
    assert len(rows) == 2
    assert list(rows[0]) == list(retrosheet.GAME_LOG_FIELDS)
    assert rows[0]["date"] == "20240320"
    assert rows[0]["visiting_team"] == "LAN"
    assert all(isinstance(v, str) for v in rows[0].values())


def test_get_game_logs_cached_second_call_no_download(mock_retrosheet):
    retrosheet.get_game_logs(2024)
    assert len(mock_retrosheet) == 1
    retrosheet.get_game_logs(2024)
    assert len(mock_retrosheet) == 1


def test_get_game_logs_force_refresh_redownloads(mock_retrosheet):
    retrosheet.get_game_logs(2024)
    retrosheet.get_game_logs(2024, force_refresh=True)
    assert len(mock_retrosheet) == 2


def test_get_game_logs_year_validation(mock_retrosheet):
    with pytest.raises(ValidationError):
        retrosheet.get_game_logs(1870)
    assert mock_retrosheet == []  # validated before any network I/O


def test_get_game_logs_accepts_string_year(mock_retrosheet):
    # The CLI passthrough forwards --year=2024 as a string; year coerces to int.
    rows = retrosheet.get_game_logs("2024")
    assert rows[0]["date"] == "20240320"


def test_get_game_logs_normalizes_year_for_member_name(mock_retrosheet):
    # Coercion happens before the member filename is built, so any int()-able
    # spelling resolves to the same cache member (gl2024.txt, not "gl 2024.txt").
    rows = retrosheet.get_game_logs(" 2024")
    assert rows[0]["date"] == "20240320"
    assert len(mock_retrosheet) == 1
    retrosheet.get_game_logs(2024)  # served from the same cache member
    assert len(mock_retrosheet) == 1


def test_get_game_logs_non_numeric_year_raises(mock_retrosheet):
    with pytest.raises(ValidationError):
        retrosheet.get_game_logs("last-season")
    assert mock_retrosheet == []


def test_string_year_below_coverage_raises(mock_retrosheet):
    # Coercion happens before the coverage check, so "1870" < 1871 still fails.
    with pytest.raises(ValidationError):
        retrosheet.get_game_logs("1870")
    assert mock_retrosheet == []


def test_get_game_logs_bad_field_count_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        http,
        "request_bytes",
        lambda url, **kw: _zip_bytes({"gl2024.txt": "only,three,fields\n"}),
    )
    with pytest.raises(RequestError, match="expected 161"):
        retrosheet.get_game_logs(2024)


#####################################################################
# Plays
#####################################################################


def test_get_plays_uses_source_header(mock_retrosheet):
    rows = retrosheet.get_plays(2024)
    assert rows == [
        {"gid": "SDN202403200", "event": "W", "inning": "1", "batter": "bettm001"}
    ]


def test_get_plays_year_validation(mock_retrosheet):
    with pytest.raises(ValidationError):
        retrosheet.get_plays(1902)
    assert mock_retrosheet == []


#####################################################################
# Schedules
#####################################################################


def test_get_schedule_drops_colliding_header(mock_retrosheet):
    rows = retrosheet.get_schedule(2026)
    assert len(rows) == 2
    assert list(rows[0]) == list(retrosheet.SCHEDULE_FIELDS)
    assert rows[0]["date"] == "20260325"
    assert rows[0]["visiting_league"] == "AL"
    assert rows[0]["home_league"] == "NL"
    assert rows[0]["park_id"] == "SFO03"
    assert rows[0]["postponed"] == ""


def test_get_schedule_headerless_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        http,
        "request_bytes",
        lambda url, **kw: _zip_bytes({"2026schedule.csv": _SCHEDULE_ROWS}),
    )
    rows = retrosheet.get_schedule(2026)
    assert len(rows) == 2
    assert rows[0]["date"] == "20260325"


def test_get_schedule_year_validation(mock_retrosheet):
    with pytest.raises(ValidationError):
        retrosheet.get_schedule(1876)
    assert mock_retrosheet == []


#####################################################################
# Biofile family
#####################################################################


def test_biofile_family_shares_one_download(mock_retrosheet):
    people = retrosheet.get_biofile()
    coaches = retrosheet.get_coaches()
    relatives = retrosheet.get_relatives()
    assert len(mock_retrosheet) == 1

    assert people[0]["PLAYERID"] == "aardd001"
    assert coaches[0] == {
        "id": "aarot101",
        "year": "1979",
        "team": "ATL",
        "role": "C",
        "start": "04/06/1979",
        "end": "09/30/1979",
    }
    assert relatives[0]["relation"] == "Brother"


def test_biofile_force_refresh_redownloads(mock_retrosheet):
    retrosheet.get_biofile()
    retrosheet.get_biofile(force_refresh=True)
    assert len(mock_retrosheet) == 2


#####################################################################
# Per-season bundle
#####################################################################


def test_season_bundle_shares_one_download(mock_retrosheet):
    accessors = {
        "gameinfo": retrosheet.get_gameinfo,
        "batting": retrosheet.get_batting,
        "pitching": retrosheet.get_pitching,
        "fielding": retrosheet.get_fielding,
        "teamstats": retrosheet.get_teamstats,
        "allplayers": retrosheet.get_allplayers,
    }
    for table, accessor in accessors.items():
        rows = accessor(2024)
        assert rows == [{"gid": "SDN202403200", "id": table}]
    assert len(mock_retrosheet) == 1


def test_season_bundle_year_validation(mock_retrosheet):
    with pytest.raises(ValidationError):
        retrosheet.get_gameinfo(1902)
    assert mock_retrosheet == []


#####################################################################
# Cache management
#####################################################################


def test_refresh_redownloads_and_returns_paths(mock_retrosheet):
    retrosheet.get_game_logs(2024)
    paths = retrosheet.refresh("game_logs", 2024)
    assert len(mock_retrosheet) == 2
    assert [p.name for p in paths] == ["gl2024.txt"]
    assert all(p.exists() for p in paths)


def test_refresh_biofile_needs_no_year(mock_retrosheet):
    paths = retrosheet.refresh("biofile")
    assert sorted(p.name for p in paths) == sorted(_BIOFILE_MEMBERS)


def test_refresh_unknown_dataset_suggests(mock_retrosheet):
    with pytest.raises(ValidationError, match="game_logs"):
        retrosheet.refresh("game_log", 2024)
    assert mock_retrosheet == []


def test_refresh_year_required_for_year_scoped_dataset(mock_retrosheet):
    with pytest.raises(ValidationError, match="required"):
        retrosheet.refresh("game_logs")
    assert mock_retrosheet == []


def test_clear_cache_counts_and_forces_redownload(mock_retrosheet):
    retrosheet.get_game_logs(2024)
    retrosheet.get_biofile()
    # game_logs zip has 1 member; biofile.zip has 4.
    assert retrosheet.clear_cache() == 5
    assert retrosheet.clear_cache() == 0

    retrosheet.get_game_logs(2024)
    assert len(mock_retrosheet) == 3


def test_clear_cache_missing_dir_returns_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path / "nonexistent")
    assert retrosheet.clear_cache() == 0


#####################################################################
# Failure modes
#####################################################################


def test_missing_member_raises_requesterror(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        http,
        "request_bytes",
        lambda url, **kw: _zip_bytes({"unexpected.csv": "a,b\n1,2\n"}),
    )
    with pytest.raises(RequestError, match="not a member"):
        retrosheet.get_game_logs(2024)


def test_non_zip_response_raises_requesterror(monkeypatch, tmp_path):
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(http, "request_bytes", lambda url, **kw: b"<html>nope</html>")
    with pytest.raises(RequestError, match="not a zip archive"):
        retrosheet.get_biofile()


def test_extract_zip_skips_directory_members(monkeypatch, tmp_path):
    # A zip can carry directory entries ("2024/"); extraction writes only
    # real file members into the flat cache dir.
    monkeypatch.setattr(files_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        http,
        "request_bytes",
        lambda url, **kw: _zip_bytes({"2024/": "", "gl2024.txt": _game_log_text()}),
    )
    rows = retrosheet.get_game_logs(2024)
    assert rows[0]["date"] == "20240320"
    extracted = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert extracted == ["gl2024.txt"]
