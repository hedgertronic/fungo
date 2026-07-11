"""Tests for the Chadwick lookup.

The offline tests mock fungo.http.request_bytes and redirect the cache to a
tmp dir so the real ~/.cache/fungo register is never touched. The fixtures
also patch fungo.http.request_json to raise, proving that offline paths (and
converters with the register value present or live_fallback=False) never hit
the MLB Stats API; xref-fallback tests re-patch it with a canned payload. A
live test that hits GitHub is behind @pytest.mark.live.
"""

from __future__ import annotations

import os
import time
import warnings

import pytest

from fungo import http
from fungo import lookup as lookup_mod
from fungo.exceptions import StaleCacheWarning

_HEADER = (
    "key_mlbam,key_fangraphs,key_bbref,key_bbref_minors,key_retro,"
    "name_first,name_last,name_given,mlb_played_first,mlb_played_last"
)
_ROW = "545361,15640,troutmi01,,troum001,Mike,Trout,Michael Nelson,2011,2024"


_XREF_PAYLOAD = {
    "people": [
        {
            "id": 999999,
            "xrefIds": [
                {"xrefId": "31234", "xrefType": "fangraphs"},
                {"xrefId": "newbie01", "xrefType": "lahman"},
                {"xrefId": "newbn001", "xrefType": "retrosheet"},
            ],
        }
    ]
}


def _register_row(**overrides):
    row = dict(zip(_HEADER.split(","), _ROW.split(","), strict=True))
    row.update(overrides)
    return row


def _forbid_request_json(url, params=None, **kw):
    raise AssertionError(f"unexpected http.request_json call: {url}")


@pytest.fixture
def mock_register(monkeypatch, tmp_path):
    cache_file = tmp_path / "chadwick_people.csv"
    monkeypatch.setattr(lookup_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(lookup_mod, "CACHE_FILE", cache_file)
    monkeypatch.setattr(lookup_mod, "_ROWS", None)
    monkeypatch.setattr(lookup_mod.time, "sleep", lambda *_: None)

    # One shard returns header+row; the rest return just the header.
    shard_bodies = iter(
        [f"{_HEADER}\n{_ROW}\n".encode()]
        + [f"{_HEADER}\n".encode()] * (len(lookup_mod.CHADWICK_SHARDS) - 1)
    )

    def fake_request_bytes(url, params=None, **kw):
        return next(shard_bodies)

    # Per the build spec, mock transport at fungo.http.request_bytes; lookup
    # calls it via the http module so the patch takes effect. request_json is
    # forbidden here — offline paths must never hit the MLB Stats API; xref
    # tests re-patch it with a canned payload.
    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(http, "request_json", _forbid_request_json)
    return cache_file


def test_lookup_by_name(mock_register):
    matches = lookup_mod.lookup(name="trout")
    assert len(matches) == 1
    assert matches[0]["key_mlbam"] == "545361"


def test_lookup_caches_to_disk(mock_register):
    lookup_mod.lookup(name="trout")
    assert mock_register.exists()


def test_id_converters(mock_register):
    assert lookup_mod.mlbam_to_fangraphs("545361") == "15640"
    assert lookup_mod.mlbam_to_bbref("545361") == "troutmi01"
    assert lookup_mod.fangraphs_to_mlbam("15640") == "545361"
    assert lookup_mod.bbref_to_mlbam("troutmi01") == "545361"


def test_converter_miss_returns_none(mock_register):
    # live_fallback=False keeps a register miss fully offline; the fixture's
    # forbidden request_json would fail the test if the fallback fired.
    assert lookup_mod.mlbam_to_fangraphs("0", live_fallback=False) is None
    assert lookup_mod.fangraphs_to_mlbam("0") is None


def test_lookup_by_each_id_field(mock_register):
    # Exercises each per-field filter branch (fangraphs/bbref/retro) and a miss.
    assert lookup_mod.lookup(fangraphs="15640")[0]["key_mlbam"] == "545361"
    assert lookup_mod.lookup(bbref="troutmi01")[0]["key_mlbam"] == "545361"
    assert lookup_mod.lookup(retro="troum001")[0]["key_mlbam"] == "545361"
    assert lookup_mod.lookup(fangraphs="0") == []


def test_lookup_by_bbref_minors_and_retro(monkeypatch):
    monkeypatch.setattr(
        lookup_mod,
        "_ROWS",
        [
            _register_row(key_bbref_minors="troutmi01-minors"),
            _register_row(
                key_mlbam="0",
                key_bbref_minors="other-minors",
                key_retro="other001",
            ),
        ],
    )

    assert (
        lookup_mod.lookup(bbref_minors="troutmi01-minors")[0]["key_mlbam"] == "545361"
    )
    assert lookup_mod.lookup(retro="troum001")[0]["key_mlbam"] == "545361"


def test_lookup_mlb_only_excludes_non_mlb_rows(monkeypatch):
    monkeypatch.setattr(
        lookup_mod,
        "_ROWS",
        [
            _register_row(key_mlbam="1"),
            _register_row(key_mlbam="2", mlb_played_first="", mlb_played_last=""),
        ],
    )

    assert [r["key_mlbam"] for r in lookup_mod.lookup(name="trout")] == ["1"]
    all_matches = lookup_mod.lookup(name="trout", mlb_only=False)
    assert [r["key_mlbam"] for r in all_matches] == [
        "1",
        "2",
    ]


def test_lookup_name_no_match_returns_empty(mock_register):
    assert lookup_mod.lookup(name="nonexistent") == []


def test_mlbam_to_bbref_empty_value_returns_none(monkeypatch, mock_register):
    row_no_bbref = dict(zip(_HEADER.split(","), _ROW.split(","), strict=True))
    row_no_bbref["key_bbref"] = ""
    monkeypatch.setattr(lookup_mod, "_ROWS", [row_no_bbref])
    assert lookup_mod.mlbam_to_bbref("545361", live_fallback=False) is None


def test_converters_accept_int_input(mock_register):
    # Integer IDs are coerced to str for comparison against register values.
    assert lookup_mod.mlbam_to_fangraphs(545361) == "15640"
    assert lookup_mod.fangraphs_to_mlbam(15640) == "545361"


def test_bbref_converters_miss_return_none(mock_register):
    assert lookup_mod.mlbam_to_bbref("0", live_fallback=False) is None
    assert lookup_mod.bbref_to_mlbam("nobody00") is None


def test_converter_empty_value_returns_none(monkeypatch, mock_register):
    # A matched row whose target key is "" yields None, not "".
    row_no_fg = dict(zip(_HEADER.split(","), _ROW.split(","), strict=True))
    row_no_fg["key_fangraphs"] = ""
    monkeypatch.setattr(lookup_mod, "_ROWS", [row_no_fg])
    assert lookup_mod.mlbam_to_fangraphs("545361", live_fallback=False) is None


@pytest.fixture
def counting_register(monkeypatch, tmp_path):
    """Like mock_register but counts downloads and serves shards cyclically.

    Each full download consumes ``len(CHADWICK_SHARDS)`` request_bytes calls, so
    the cyclic body generator supports an unbounded number of refresh cycles.
    """
    cache_file = tmp_path / "chadwick_people.csv"
    monkeypatch.setattr(lookup_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(lookup_mod, "CACHE_FILE", cache_file)
    monkeypatch.setattr(lookup_mod, "_ROWS", None)
    monkeypatch.setattr(lookup_mod.time, "sleep", lambda *_: None)

    calls = {"count": 0}

    def fake_request_bytes(url, params=None, **kw):
        # First shard of each cycle carries the data row; rest are header-only.
        first_of_cycle = calls["count"] % len(lookup_mod.CHADWICK_SHARDS) == 0
        calls["count"] += 1
        body = f"{_HEADER}\n{_ROW}\n" if first_of_cycle else f"{_HEADER}\n"
        return body.encode()

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    monkeypatch.setattr(http, "request_json", _forbid_request_json)
    return calls


def test_lookup_cache_hit_does_not_redownload(counting_register):
    lookup_mod.lookup(name="trout")
    after_first = counting_register["count"]
    assert after_first == len(lookup_mod.CHADWICK_SHARDS)

    # Second lookup is served from the in-memory cache without network IO.
    lookup_mod.lookup(name="trout")
    assert counting_register["count"] == after_first


def test_lookup_loads_disk_cache_without_redownload(counting_register):
    # Simulates a fresh process: in-memory cache is cold but the on-disk cache
    # persists, so _load reads from disk without network IO.
    lookup_mod.lookup(name="trout")
    after_first = counting_register["count"]

    lookup_mod._ROWS = None
    matches = lookup_mod.lookup(name="trout")
    assert len(matches) == 1
    assert counting_register["count"] == after_first


def test_refresh_redownloads(counting_register):
    lookup_mod.lookup(name="trout")
    after_first = counting_register["count"]

    path = lookup_mod.refresh()
    assert path == lookup_mod.CACHE_FILE
    assert counting_register["count"] == after_first * 2
    # refresh clears the in-memory cache so the next lookup reloads from disk.
    assert lookup_mod._ROWS is None


def test_load_force_refresh_redownloads(counting_register):
    lookup_mod._load()
    after_first = counting_register["count"]

    lookup_mod._load(force_refresh=True)
    assert counting_register["count"] == after_first * 2


def test_lookup_force_refresh_redownloads(counting_register):
    lookup_mod.lookup(name="trout")
    after_first = counting_register["count"]

    matches = lookup_mod.lookup(name="trout", force_refresh=True)
    assert len(matches) == 1
    assert counting_register["count"] == after_first * 2


def test_fetch_all_shards_skips_empty_shards(monkeypatch):
    bodies = iter([b"", f"{_HEADER}\n{_ROW}\n".encode()])
    monkeypatch.setattr(lookup_mod, "CHADWICK_SHARDS", "ab")
    monkeypatch.setattr(lookup_mod.time, "sleep", lambda *_: None)

    def fake_request_bytes(url, **kw):
        return next(bodies)

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)

    assert lookup_mod._fetch_all_shards() == f"{_HEADER}\n{_ROW}\n"


#####################################################################
# MLB Stats API xref fallback
#####################################################################


@pytest.fixture
def mock_xref(monkeypatch):
    """Patches http.request_json with the canned xrefIds payload, counting calls.

    Applied after mock_register in test signatures so it overrides the
    fixture's forbidden request_json.
    """
    calls = []

    def fake_request_json(url, params=None, **kw):
        calls.append((url, params))
        return _XREF_PAYLOAD

    monkeypatch.setattr(http, "request_json", fake_request_json)
    return calls


def test_xref_ids_shape(mock_xref):
    ids = lookup_mod.xref_ids(999999)
    assert ids == {
        "fangraphs": "31234",
        "lahman": "newbie01",
        "retrosheet": "newbn001",
    }
    assert mock_xref == [
        ("https://statsapi.mlb.com/api/v1/people/999999", {"hydrate": "xrefId"})
    ]


def test_xref_ids_empty_when_api_has_none(monkeypatch):
    monkeypatch.setattr(http, "request_json", lambda *a, **kw: {"people": []})
    assert lookup_mod.xref_ids("999999") == {}

    monkeypatch.setattr(
        http, "request_json", lambda *a, **kw: {"people": [{"id": 999999}]}
    )
    assert lookup_mod.xref_ids("999999") == {}


def test_xref_ids_non_dict_payload_returns_empty(monkeypatch):
    # request_json is typed to return Any; a non-dict payload (an error page
    # decoded as a JSON list, say) yields {} rather than an AttributeError.
    monkeypatch.setattr(http, "request_json", lambda *a, **kw: ["unexpected"])
    assert lookup_mod.xref_ids("999999") == {}


def test_fallback_fires_when_register_row_missing(mock_register, mock_xref):
    assert lookup_mod.mlbam_to_fangraphs("999999") == "31234"
    assert lookup_mod.mlbam_to_bbref("999999") == "newbie01"
    assert len(mock_xref) == 2  # one xrefId call per converter


def test_fallback_fires_when_register_value_blank(
    monkeypatch, mock_register, mock_xref
):
    monkeypatch.setattr(
        lookup_mod,
        "_ROWS",
        [_register_row(key_mlbam="999999", key_fangraphs="", key_bbref="")],
    )
    assert lookup_mod.mlbam_to_fangraphs("999999") == "31234"
    assert lookup_mod.mlbam_to_bbref("999999") == "newbie01"
    assert len(mock_xref) == 2


def test_no_fallback_when_register_has_value(mock_register):
    # The fixture's request_json raises on any call, so passing proves the
    # register hit short-circuits the fallback.
    assert lookup_mod.mlbam_to_fangraphs("545361") == "15640"
    assert lookup_mod.mlbam_to_bbref("545361") == "troutmi01"


def test_live_fallback_false_is_offline(mock_register):
    assert lookup_mod.mlbam_to_fangraphs("999999", live_fallback=False) is None
    assert lookup_mod.mlbam_to_bbref("999999", live_fallback=False) is None


def test_fallback_payload_missing_wanted_type(monkeypatch, mock_register):
    payload = {
        "people": [{"xrefIds": [{"xrefId": "newbn001", "xrefType": "retrosheet"}]}]
    }
    monkeypatch.setattr(http, "request_json", lambda *a, **kw: payload)
    assert lookup_mod.mlbam_to_fangraphs("999999") is None
    assert lookup_mod.mlbam_to_bbref("999999") is None


#####################################################################
# Cache staleness warning
#####################################################################


def test_stale_cache_warns(mock_register):
    lookup_mod.lookup(name="trout")  # populates the on-disk cache

    old = time.time() - (lookup_mod.STALE_AFTER_DAYS + 5) * 86400
    os.utime(mock_register, (old, old))

    lookup_mod._ROWS = None  # cold in-memory cache -> disk load path
    with pytest.warns(StaleCacheWarning, match="refresh"):
        lookup_mod.lookup(name="trout")

    # Warm in-memory cache: no disk load, so no repeat warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error", StaleCacheWarning)
        lookup_mod.lookup(name="trout")


def test_fresh_cache_does_not_warn(mock_register):
    lookup_mod.lookup(name="trout")

    lookup_mod._ROWS = None
    with warnings.catch_warnings():
        warnings.simplefilter("error", StaleCacheWarning)
        matches = lookup_mod.lookup(name="trout")
    assert len(matches) == 1


@pytest.mark.live
def test_lookup_live():
    matches = lookup_mod.lookup(name="Shohei Ohtani", force_refresh=True)
    assert any(m["name_last"] == "Ohtani" for m in matches)
