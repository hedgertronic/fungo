"""Offline tests for the Baseball-Reference module.

Transport is monkeypatched at ``fungo.bbref.session._fetch`` (the seam below
the rate limiter), so nothing here touches the network. The one live test is
in ``test_live.py`` behind the ``live`` marker.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from fungo.bbref import players, session, tables, teams, war
from fungo.exceptions import BBRefError, RequestError, ValidationError

#####################################################################
# Helpers
#####################################################################


@pytest.fixture(autouse=True)
def _fast_limiter(monkeypatch):
    """Zero the shared limiter's interval so offline tests don't sleep."""
    monkeypatch.setattr(session._limiter, "interval", 0.0)
    monkeypatch.setattr(session._limiter, "_last_request", 0.0)


def _capture_fetch(monkeypatch, body: bytes) -> dict[str, Any]:
    """Patch the transport seam with a recorder returning ``body``."""
    log: dict[str, Any] = {}

    def fake(url: str, params: Any) -> bytes:
        log["url"] = url
        log["params"] = params
        return body

    monkeypatch.setattr(session, "_fetch", fake)
    return log


# A page with one live table, one comment-deferred table (B-R's pattern), an
# in-body repeated header row, and a cell without data-stat (ignored).
PAGE_HTML = """
<html><body>
<table class="stats_table" id="players_standard_batting">
<thead>
<tr><th data-stat="year_id">Season</th><th data-stat="b_war">WAR</th></tr>
</thead>
<tbody>
<tr><th data-stat="year_id">2011</th><td data-stat="b_war">0.5</td><td>junk</td></tr>
<tr class="thead"><th data-stat="year_id">Season</th><td data-stat="b_war">WAR</td></tr>
<tr><th data-stat="year_id">2012</th><td data-stat="b_war">10.5</td></tr>
</tbody>
</table>
<div id="all_br-salaries" class="section_wrapper setup_commented commented">
<div class="placeholder"></div>
<!--
<div class="section_content">
<table id="br-salaries">
<tbody>
<tr><th data-stat="year_ID">2012</th><td data-stat="Salary">$480,000</td></tr>
</tbody>
</table>
</div>
-->
</div>
</body></html>
"""


#####################################################################
# Rate limiter
#####################################################################


def test_rate_limiter_enforces_interval():
    limiter = session._RateLimiter(0.05)
    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start >= 0.05


def test_rate_limiter_no_wait_after_interval_elapsed():
    limiter = session._RateLimiter(0.01)
    limiter.wait()
    time.sleep(0.02)
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start < 0.01


#####################################################################
# session: block mapping
#####################################################################


@pytest.mark.parametrize("code", [403, 429])
def test_blocked_status_raises_bbref_error(monkeypatch, code):
    def fake(url: str, params: Any) -> bytes:
        raise RequestError(f"HTTP {code} for {url}")

    monkeypatch.setattr(session, "_fetch", fake)
    with pytest.raises(BBRefError, match="do NOT retry"):
        session.bbref_bytes("/players/t/troutmi01.shtml")


def test_other_errors_propagate(monkeypatch):
    def fake(url: str, params: Any) -> bytes:
        raise RequestError(f"HTTP 500 for {url}")

    monkeypatch.setattr(session, "_fetch", fake)
    with pytest.raises(RequestError):
        session.bbref_bytes("/players/t/troutmi01.shtml")


def test_bbref_bytes_builds_url(monkeypatch):
    log = _capture_fetch(monkeypatch, b"ok")
    assert session.bbref_bytes("/x", {"a": 1}) == b"ok"
    assert log["url"] == f"{session.BASE_URL}/x"
    assert log["params"] == {"a": 1}


#####################################################################
# tables: comment-aware extraction, data-stat addressing
#####################################################################


def test_extract_live_table():
    rows = tables.extract_table(PAGE_HTML, "players_standard_batting")
    assert rows == [
        {"year_id": "2011", "b_war": "0.5"},
        {"year_id": "2012", "b_war": "10.5"},
    ]


def test_extract_commented_table():
    rows = tables.extract_table(PAGE_HTML, "br-salaries")
    assert rows == [{"year_ID": "2012", "Salary": "$480,000"}]


def test_repeated_header_rows_skipped():
    rows = tables.extract_table(PAGE_HTML, "players_standard_batting")
    assert all(r["year_id"] != "Season" for r in rows)


def test_missing_table_lists_available():
    with pytest.raises(BBRefError) as exc_info:
        tables.extract_table(PAGE_HTML, "nope")
    assert "players_standard_batting" in str(exc_info.value)
    assert "br-salaries" in str(exc_info.value)


def test_extract_all_tables():
    out = tables.extract_all_tables(PAGE_HTML)
    assert set(out) == {"players_standard_batting", "br-salaries"}


def test_list_tables_document_order():
    assert tables.list_tables(PAGE_HTML) == [
        "players_standard_batting",
        "br-salaries",
    ]


#####################################################################
# war: flat-file CSV
#####################################################################


def test_get_war_daily_parses_csv(monkeypatch):
    log = _capture_fetch(
        monkeypatch, b"name_common,WAR\nMike Trout,10.5\nAaron Judge,11.2\n"
    )
    rows = war.get_war_daily("bat")
    assert rows == [
        {"name_common": "Mike Trout", "WAR": "10.5"},
        {"name_common": "Aaron Judge", "WAR": "11.2"},
    ]
    assert log["url"].endswith("/data/war_daily_bat.txt")


def test_get_war_daily_unknown_kind():
    with pytest.raises(ValidationError, match="pitch"):
        war.get_war_daily("pitching")


#####################################################################
# players / teams: path building
#####################################################################


def test_get_player_path(monkeypatch):
    log = _capture_fetch(monkeypatch, PAGE_HTML.encode())
    out = players.get_player("troutmi01")
    assert log["url"].endswith("/players/t/troutmi01.shtml")
    assert "players_standard_batting" in out


def test_get_game_log_params(monkeypatch):
    log = _capture_fetch(monkeypatch, PAGE_HTML.encode())
    players.get_game_log("troutmi01", 2024, kind="p")
    assert log["url"].endswith("/players/gl.fcgi")
    assert log["params"] == {"id": "troutmi01", "t": "p", "year": 2024}


def test_get_splits_defaults_to_career(monkeypatch):
    log = _capture_fetch(monkeypatch, PAGE_HTML.encode())
    players.get_splits("troutmi01")
    assert log["params"] == {"id": "troutmi01", "year": "Career", "t": "b"}


def test_get_team_schedule_uppercases(monkeypatch):
    log = _capture_fetch(monkeypatch, PAGE_HTML.encode())
    teams.get_team_schedule("nyy", 2024)
    assert log["url"].endswith("/teams/NYY/2024-schedule-scores.shtml")


#####################################################################
# duplicate table ids (standings page pattern)
#####################################################################

DUP_HTML = """
<table id="standings_E"><tbody>
<tr><th data-stat="team_ID">NYY</th><td data-stat="W">94</td></tr>
</tbody></table>
<table id="standings_E"><tbody>
<tr><th data-stat="team_ID">ATL</th><td data-stat="W">89</td></tr>
</tbody></table>
"""


def test_extract_all_tables_suffixes_duplicate_ids():
    out = tables.extract_all_tables(DUP_HTML)
    # AL table first in document order, NL suffixed — neither dropped.
    assert out["standings_E"][0]["team_ID"] == "NYY"
    assert out["standings_E_2"][0]["team_ID"] == "ATL"


#####################################################################
# leagues: standings + draft
#####################################################################


def test_get_standings_url(monkeypatch):
    from fungo.bbref import leagues

    log = _capture_fetch(monkeypatch, DUP_HTML.encode())
    out = leagues.get_standings(1955)
    assert log["url"].endswith("/leagues/MLB/1955-standings.shtml")
    assert "standings_E" in out


DRAFT_HTML = """
<table id="draft_stats"><tbody>
<tr><th data-stat="year_ID">2022</th><td data-stat="player">Druw Jones (minors)</td>
<td data-stat="overall_pick">2</td></tr>
</tbody></table>
"""


def test_get_draft_params(monkeypatch):
    from fungo.bbref import leagues

    log = _capture_fetch(monkeypatch, DRAFT_HTML.encode())
    rows = leagues.get_draft(2022, 1)
    assert rows[0]["overall_pick"] == "2"
    assert log["params"] == {
        "year_ID": 2022,
        "draft_round": 1,
        "draft_type": "junreg",
        "query_type": "year_round",
    }


def test_get_draft_by_team_params(monkeypatch):
    from fungo.bbref import leagues

    log = _capture_fetch(monkeypatch, DRAFT_HTML.encode())
    leagues.get_draft_by_team("tbd", 2011)
    assert log["params"]["team_ID"] == "TBD"
    assert log["params"]["query_type"] == "franch_year"


#####################################################################
# boxes: team-code mapping, linescore, daily links
#####################################################################

BOX_HTML = """
<table class="linescore nohover stats_table no_freeze"><tbody>
<tr><th data-stat="team">NYA</th><td data-stat="R">5</td></tr>
</tbody></table>
<table id="NewYorkYankeesbatting"><tbody>
<tr><th data-stat="player">Judge</th><td data-stat="HR">2</td></tr>
</tbody></table>
"""


def test_get_box_score_maps_franchise_code(monkeypatch):
    from fungo.bbref import boxes

    log = _capture_fetch(monkeypatch, BOX_HTML.encode())
    out = boxes.get_box_score("NYY", "2024-10-30")
    assert log["url"].endswith("/boxes/NYA/NYA202410300.shtml")
    assert out["NewYorkYankeesbatting"][0]["HR"] == "2"
    assert out["linescore"][0]["R"] == "5"  # id-less table, special-cased


def test_get_box_score_accepts_retrosheet_code(monkeypatch):
    from fungo.bbref import boxes

    log = _capture_fetch(monkeypatch, BOX_HTML.encode())
    boxes.get_box_score("sln", "2024-06-01", game=2)
    assert log["url"].endswith("/boxes/SLN/SLN202406012.shtml")


DAILY_HTML = """
<div class="game_summary">
<a href="/boxes/BAL/BAL202406150.shtml">Final</a>
<a href="/previews/x.shtml">ignore</a>
</div>
<div class="game_summary"><a href="/boxes/NYA/NYA202406150.shtml">Final</a></div>
<table id="standings-upto-AL-E"><tbody>
<tr><th data-stat="team_ID">NYY</th><td data-stat="W">50</td></tr>
</tbody></table>
"""


def test_get_daily_paths_and_tables(monkeypatch):
    from fungo.bbref import boxes

    log = _capture_fetch(monkeypatch, DAILY_HTML.encode())
    out = boxes.get_daily("2024-06-15")
    assert log["params"] == {"date": "2024-06-15"}
    assert out["box_score_paths"] == [
        "/boxes/BAL/BAL202406150.shtml",
        "/boxes/NYA/NYA202406150.shtml",
    ]
    assert "standings-upto-AL-E" in out["tables"]


#####################################################################
# register
#####################################################################


def test_get_register_player_params(monkeypatch):
    from fungo.bbref import register

    log = _capture_fetch(monkeypatch, PAGE_HTML.encode())
    register.get_register_player("baez--001ben")
    assert log["url"].endswith("/register/player.fcgi")
    assert log["params"] == {"id": "baez--001ben"}


#####################################################################
# cache: response caching
#####################################################################


@pytest.fixture()
def _cache_dir(tmp_path):
    """Enable cache in a temp dir; disable unconditionally on teardown."""
    from fungo.bbref import cache

    p = tmp_path / "bbref_cache"
    cache.enable_cache(path=p)
    yield p
    cache.disable_cache()


def _counting_fetch(monkeypatch, body: bytes) -> dict[str, int]:
    """Patch the transport seam with a call counter returning ``body``."""
    counter: dict[str, int] = {"calls": 0}

    def fake(url: str, params: Any) -> bytes:
        counter["calls"] += 1
        return body

    monkeypatch.setattr(session, "_fetch", fake)
    return counter


def test_cache_disabled_by_default(monkeypatch):
    """Two identical bbref_bytes calls with no cache enabled → _fetch called twice."""
    from fungo.bbref import cache

    assert not cache._CACHE_ENABLED
    counter = _counting_fetch(monkeypatch, b"page")
    session.bbref_bytes("/x")
    session.bbref_bytes("/x")
    assert counter["calls"] == 2


def test_cache_hit_skips_fetch(monkeypatch, _cache_dir):
    """Second identical call returns cached bytes; _fetch is called once."""
    counter = _counting_fetch(monkeypatch, b"content")
    r1 = session.bbref_bytes("/y")
    r2 = session.bbref_bytes("/y")
    assert counter["calls"] == 1
    assert r1 == r2 == b"content"


def test_cache_different_params_are_separate_entries(monkeypatch, _cache_dir):
    """Different params produce different cache keys; both calls fetch from network."""
    counter = _counting_fetch(monkeypatch, b"data")
    session.bbref_bytes("/z", {"a": 1})
    session.bbref_bytes("/z", {"a": 2})
    assert counter["calls"] == 2


def test_cache_ttl_expiry_refetches(monkeypatch, tmp_path):
    """An entry older than TTL is considered stale and re-fetched from the network."""
    import os

    from fungo.bbref import cache

    p = tmp_path / "bbref_ttl"
    cache.enable_cache(ttl=60.0, path=p)
    try:
        counter = _counting_fetch(monkeypatch, b"fresh")
        session.bbref_bytes("/w")
        assert counter["calls"] == 1

        # Backdate the mtime by 120 seconds — beyond the 60s TTL.
        key = cache._cache_key(f"{session.BASE_URL}/w", None)
        entry = p / key
        old_mtime = entry.stat().st_mtime - 120
        os.utime(entry, (old_mtime, old_mtime))

        session.bbref_bytes("/w")
        assert counter["calls"] == 2
    finally:
        cache.disable_cache()


def test_clear_cache_deletes_entries_and_refetches(monkeypatch, _cache_dir):
    """clear_cache deletes all cache files, returns count; next call refetches."""
    from fungo.bbref import cache

    counter = _counting_fetch(monkeypatch, b"rows")
    session.bbref_bytes("/a")
    session.bbref_bytes("/b", {"k": "v"})
    assert counter["calls"] == 2

    deleted = cache.clear_cache()
    assert deleted == 2
    assert list(_cache_dir.iterdir()) == []

    # Cache is still enabled but empty; next call must fetch from network.
    session.bbref_bytes("/a")
    assert counter["calls"] == 3


def test_errors_not_cached(monkeypatch, _cache_dir):
    """A failing _fetch writes no cache file; the next successful call fetches live."""
    from fungo.bbref import cache

    calls: list[str] = []

    def fake(url: str, params: Any) -> bytes:
        calls.append(url)
        if len(calls) == 1:
            raise RequestError(f"HTTP 500 for {url}")
        return b"recovered"

    monkeypatch.setattr(session, "_fetch", fake)

    with pytest.raises(RequestError):
        session.bbref_bytes("/err")

    # No cache file should have been written.
    key = cache._cache_key(f"{session.BASE_URL}/err", None)
    assert not (_cache_dir / key).exists()

    # A later successful call must fetch from the network, not a phantom cache entry.
    result = session.bbref_bytes("/err")
    assert result == b"recovered"
    assert len(calls) == 2
