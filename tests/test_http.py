"""Tests for fungo.http: request_bytes, parse_csv, map_concurrent (offline)."""

from __future__ import annotations

import sys
import threading
import urllib.error
import urllib.request

import pytest

from fungo import http
from fungo.exceptions import RequestError
from fungo.http import map_concurrent, parse_csv, request_bytes

#####################################################################
# request_bytes — param encoding
#####################################################################


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return b"ok"


def test_request_bytes_doseq_repeats_list_params(monkeypatch):
    # A LIST param value must become repeated keys (season[]=2023&season[]=2024),
    # not a stringified list. This is what makes multi-year season[] work; without
    # doseq=True the URL would be season%5B%5D=%5B... and Savant returns garbage.
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    request_bytes("https://example.com/x", {"season[]": ["2023", "2024"]})
    assert "season%5B%5D=2023&season%5B%5D=2024" in captured["url"]


def test_request_bytes_keeps_pipes_unencoded(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    request_bytes("https://example.com/x", {"hfPT": "FF|SL|"})
    assert "hfPT=FF|SL|" in captured["url"]


def test_request_bytes_serializes_bools_lowercase(monkeypatch):
    # str(True) is "True"; query params want the canonical lowercase form.
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    request_bytes("https://example.com/x", {"active": True, "flag": False})
    assert "active=true" in captured["url"]
    assert "flag=false" in captured["url"]


def test_request_bytes_merges_custom_headers(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    request_bytes("https://example.com/x", headers={"Accept": "application/json"})
    assert captured["headers"]["User-agent"] == http.USER_AGENT
    assert captured["headers"]["Accept"] == "application/json"


#####################################################################
# request_bytes — retry / backoff
#####################################################################


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.com/x", code, f"status {code}", None, None
    )


def test_request_bytes_retries_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise _http_error(503)
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    body = request_bytes("https://example.com/x")
    assert body == b"ok"
    assert calls["n"] == 3  # two 503s retried, third succeeds


def test_request_bytes_4xx_raises_immediately_without_retry(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RequestError, match="HTTP 404"):
        request_bytes("https://example.com/x")
    assert calls["n"] == 1  # no retry on 4xx


def test_request_bytes_exhausts_retries_raises(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(503)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RequestError, match="Failed after 3 retries"):
        request_bytes("https://example.com/x")
    assert calls["n"] == 3  # default retries=3 attempts


def test_request_bytes_retries_network_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection refused")
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert request_bytes("https://example.com/x") == b"ok"
    assert calls["n"] == 2


def test_request_bytes_respects_custom_retries(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(500)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RequestError, match="Failed after 5 retries"):
        request_bytes("https://example.com/x", retries=5)
    assert calls["n"] == 5


#####################################################################
# parse_csv
#####################################################################


def test_parse_csv_basic():
    raw = "a,b,c\n1,2,3\n4,5,6\n"
    rows = parse_csv(raw)
    assert rows == [
        {"a": "1", "b": "2", "c": "3"},
        {"a": "4", "b": "5", "c": "6"},
    ]


def test_parse_csv_strips_bom_from_bytes():
    raw = "﻿name,team\nTrout,LAA\n".encode("utf-8-sig")
    rows = parse_csv(raw)
    assert next(iter(rows[0])) == "name"
    assert rows[0] == {"name": "Trout", "team": "LAA"}


def test_parse_csv_strips_bom_from_str_first_key():
    raw = "﻿name,team\nTrout,LAA\n"
    rows = parse_csv(raw)
    assert next(iter(rows[0])) == "name"


def test_parse_csv_empty_returns_empty_list():
    assert parse_csv("") == []
    assert parse_csv("   \n  ") == []
    assert parse_csv(b"") == []


def test_parse_csv_preserves_empty_string_values():
    raw = "a,b,c\n1,,3\n"
    rows = parse_csv(raw)
    assert rows[0]["b"] == ""


def test_parse_csv_handles_quoted_values_with_commas():
    raw = 'name,note\n"Doe, John","says ""hi"""\n'
    rows = parse_csv(raw)
    assert rows[0]["name"] == "Doe, John"
    assert rows[0]["note"] == 'says "hi"'


#####################################################################
# request_json
#####################################################################


def test_request_json_decodes_success(monkeypatch):
    captured: dict = {}

    def fake_request_bytes(url, params=None, **kw):
        captured["url"] = url
        captured["params"] = params
        captured["kw"] = kw
        return b'{"ok": true, "rows": [1, 2]}'

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    result = http.request_json(
        "https://example.com/json",
        params={"x": "1"},
        headers={"Accept": "application/json"},
    )
    assert result == {"ok": True, "rows": [1, 2]}
    assert captured == {
        "url": "https://example.com/json",
        "params": {"x": "1"},
        "kw": {"headers": {"Accept": "application/json"}},
    }


def test_request_json_invalid_json_raises_request_error(monkeypatch):
    monkeypatch.setattr(http, "request_bytes", lambda *a, **kw: b"not valid json {")
    with pytest.raises(RequestError, match="Invalid JSON response"):
        http.request_json("https://example.com/json")


#####################################################################
# map_concurrent
#####################################################################


def test_map_concurrent_preserves_input_order():
    items = list(range(20))
    result = map_concurrent(lambda x: x * x, items, max_workers=4)
    assert result == [x * x for x in items]


def test_map_concurrent_runs_every_item():
    seen: set[int] = set()
    lock = threading.Lock()

    def record(x: int) -> int:
        with lock:
            seen.add(x)
        return x

    items = list(range(50))
    result = map_concurrent(record, items, max_workers=8)
    assert seen == set(items)
    assert result == items


def test_map_concurrent_empty_input():
    assert map_concurrent(lambda x: x, []) == []


def test_map_concurrent_delay_sleeps_between_submissions(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(http.time, "sleep", sleeps.append)

    result = map_concurrent(lambda x: x, [1, 2, 3], max_workers=1, delay=0.25)

    assert result == [1, 2, 3]
    assert sleeps == [0.25, 0.25]


def test_map_concurrent_progress_false_is_silent(capsys):
    result = map_concurrent(lambda x: x + 1, [1, 2, 3], progress=False)
    assert result == [2, 3, 4]
    assert capsys.readouterr().out == ""


def test_map_concurrent_progress_true_noop_when_rich_absent(capsys, monkeypatch):
    # Force the rich-absent path deterministically: a None entry in sys.modules
    # makes `import rich.progress` raise ImportError. The progress branch must
    # then be a silent no-op — no raise, no stdout.
    monkeypatch.setitem(sys.modules, "rich.progress", None)
    result = map_concurrent(lambda x: x + 1, [1, 2, 3], progress=True)
    assert result == [2, 3, 4]
    assert capsys.readouterr().out == ""


def test_map_concurrent_progress_true_works_when_rich_present():
    # rich is a dev dependency; progress=True must still return correct,
    # in-order results when the real progress bar is exercised.
    result = map_concurrent(lambda x: x + 1, [1, 2, 3], progress=True)
    assert result == [2, 3, 4]


def test_map_concurrent_worker_exception_propagates():
    # A worker that raises must propagate through the BaseException handler,
    # which shuts down the executor and re-raises. Lines 226-228 of http.py.
    def boom(x: int) -> int:
        raise RuntimeError("worker failed")

    with pytest.raises(RuntimeError, match="worker failed"):
        map_concurrent(boom, [1, 2, 3], max_workers=2)
