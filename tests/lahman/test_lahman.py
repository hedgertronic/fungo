"""Tests for the Lahman module.

Offline throughout: fungo.http.request_bytes is mocked with fake SABR HTML,
fake Box folder pages, and a small CSV, and the cache is redirected to a tmp
dir so the real ~/.cache/fungo/lahman is never touched. Live tests live in
test_live.py behind @pytest.mark.live.
"""

from __future__ import annotations

import pytest

from fungo import http
from fungo.exceptions import LahmanError, ValidationError
from fungo.lahman import api
from fungo.lahman import tables as tables_mod

SHARED_NAME = "y1prhc795jk8zvmelfd3jq7tl389y6cd"

SABR_HTML = f"""
<html><body>
<ul>
<li><a href="https://sabr.box.com/s/sqlsqlsqlsql" target="_blank"
rel="noopener">SQL version</a></li>
<li><a href="https://sabr.box.com/s/accessaccess" target="_blank"
rel="noopener">Microsoft Access version</a></li>
<li><a href="https://sabr.box.com/s/{SHARED_NAME}" target="_blank"
rel="noopener">Comma-delimited version</a></li>
</ul>
</body></html>
"""

# Box embeds the folder listing as JSON with "typedID":"f_{id}" preceding
# "name" in each file object; "pageCount" drives pagination.
BOX_PAGE_1 = (
    '{"pageNumber":1,"pageCount":2,"items":['
    '{"typedID":"f_111","type":"file","extension":"csv","name":"Parks.csv"},'
    '{"typedID":"f_222","type":"file","extension":"csv","name":"People.csv"},'
    '{"typedID":"f_333","type":"file","extension":"txt","name":"readme2025.txt"},'
    '{"typedID":"f_444","type":"file","extension":"csv","name":"Teams.csv"}'
    "]}"
)
BOX_PAGE_2 = (
    '{"pageNumber":2,"pageCount":2,"items":['
    '{"typedID":"f_555","type":"file","extension":"csv","name":"AllstarFull.csv"}'
    "]}"
)

PARKS_CSV = (
    b"\xef\xbb\xbfID,parkkey,parkname,city\n"
    b"256,ALB01,Riverside Park,Rensselaer\n"
    b"257,ALT01,Columbia Park,Altoona\n"
)


def _dispatch(url: str, params: dict | None) -> bytes:
    """Serve the fake SABR page, Box folder pages, and CSV download."""
    params = params or {}
    if url == api.SABR_URL:
        return SABR_HTML.encode()
    if url == f"{api.BOX_BASE_URL}/s/{SHARED_NAME}":
        return (BOX_PAGE_2 if params.get("page") == 2 else BOX_PAGE_1).encode()
    if url == f"{api.BOX_BASE_URL}/index.php":
        assert params["rm"] == "box_download_shared_file"
        assert params["shared_name"] == SHARED_NAME
        return PARKS_CSV
    raise AssertionError(f"Unexpected URL in offline test: {url}")


@pytest.fixture
def mock_lahman(monkeypatch, tmp_path):
    """Redirect the cache to tmp and count mocked request_bytes calls."""
    monkeypatch.setattr(tables_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(tables_mod, "_INDEX", None)

    calls = {"count": 0}

    def fake_request_bytes(url, params=None, **kw):
        calls["count"] += 1
        return _dispatch(url, params)

    monkeypatch.setattr(http, "request_bytes", fake_request_bytes)
    return calls


#####################################################################
# Discovery
#####################################################################


def test_discover_shared_name_picks_csv_link(mock_lahman):
    assert api.discover_shared_name() == SHARED_NAME


def test_fetch_table_index_walks_pages_and_skips_non_csv(mock_lahman):
    files = api.fetch_table_index(SHARED_NAME)
    assert files == {
        "Parks": "f_111",
        "People": "f_222",
        "Teams": "f_444",
        "AllstarFull": "f_555",
    }
    # Two folder pages fetched (pageCount=2), readme2025.txt excluded.
    assert mock_lahman["count"] == 2


def test_list_tables(mock_lahman):
    assert tables_mod.list_tables() == ["AllstarFull", "Parks", "People", "Teams"]


#####################################################################
# get_table
#####################################################################


def test_get_table_happy_path(mock_lahman):
    rows = tables_mod.get_table("Parks")
    assert len(rows) == 2
    assert rows[0] == {
        "ID": "256",
        "parkkey": "ALB01",
        "parkname": "Riverside Park",
        "city": "Rensselaer",
    }
    # All values are strings (fungo CSV convention).
    assert all(isinstance(v, str) for row in rows for v in row.values())


def test_get_table_case_tolerant(mock_lahman):
    assert tables_mod.get_table("parks") == tables_mod.get_table("Parks")
    assert tables_mod.get_table("PARKS.csv") == tables_mod.get_table("Parks")


def test_get_table_unknown_raises_validation_error(mock_lahman):
    with pytest.raises(ValidationError) as excinfo:
        tables_mod.get_table("Parkz")
    assert excinfo.value.valid_values == ["AllstarFull", "Parks", "People", "Teams"]
    assert "Parks" in str(excinfo.value)  # "did you mean?" suggestion


def test_convenience_wrappers_resolve_their_tables(mock_lahman):
    # Teams is in the fake index; the wrapper resolves and downloads it.
    assert tables_mod.get_teams() == tables_mod.get_table("Teams")
    # People resolves too (same fake CSV body serves every download).
    assert tables_mod.get_people()


#####################################################################
# Caching
#####################################################################


def test_second_get_table_makes_zero_requests(mock_lahman):
    tables_mod.get_table("Parks")
    after_first = mock_lahman["count"]
    # SABR page + 2 folder pages + 1 download.
    assert after_first == 4

    tables_mod.get_table("Parks")
    assert mock_lahman["count"] == after_first


def test_disk_cache_survives_cold_memory(mock_lahman):
    # Simulates a fresh process: the in-memory index is cold but the on-disk
    # index and CSV persist, so nothing touches the network.
    tables_mod.get_table("Parks")
    after_first = mock_lahman["count"]

    tables_mod._INDEX = None
    rows = tables_mod.get_table("Parks")
    assert len(rows) == 2
    assert mock_lahman["count"] == after_first


def test_corrupt_index_file_triggers_rediscovery(mock_lahman):
    tables_mod.list_tables()
    after_first = mock_lahman["count"]

    tables_mod._INDEX = None
    tables_mod._index_file().write_text("not json", encoding="utf-8")
    assert tables_mod.list_tables() == ["AllstarFull", "Parks", "People", "Teams"]
    assert mock_lahman["count"] == after_first * 2


def test_refresh_clears_and_rediscovers(mock_lahman):
    tables_mod.get_table("Parks")
    after_first = mock_lahman["count"]
    csv_cache = tables_mod.CACHE_DIR / "Parks.csv"
    assert csv_cache.exists()

    path = tables_mod.refresh()
    assert path == tables_mod._index_file()
    assert path.exists()
    assert not csv_cache.exists()  # cached tables are dropped
    # refresh re-runs discovery: SABR page + 2 folder pages.
    assert mock_lahman["count"] == after_first + 3

    # The next get_table re-downloads the table (one more request).
    tables_mod.get_table("Parks")
    assert mock_lahman["count"] == after_first + 4


def test_clear_cache_forces_full_refetch(mock_lahman):
    tables_mod.get_table("Parks")
    after_first = mock_lahman["count"]

    tables_mod.clear_cache()
    assert tables_mod._INDEX is None
    assert not any(tables_mod.CACHE_DIR.iterdir())

    tables_mod.get_table("Parks")
    assert mock_lahman["count"] == after_first * 2


def test_get_table_force_refresh_redownloads(mock_lahman):
    tables_mod.get_table("Parks")
    after_first = mock_lahman["count"]

    tables_mod.get_table("Parks", force_refresh=True)
    assert mock_lahman["count"] == after_first * 2


#####################################################################
# LahmanError conditions
#####################################################################


def _patch_transport(monkeypatch, fake):
    monkeypatch.setattr(http, "request_bytes", fake)


def test_sabr_page_without_box_links_raises(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params=None, **kw: b"<html>new</html>")
    with pytest.raises(LahmanError, match="No Box shared links"):
        api.discover_shared_name()


def test_sabr_page_without_csv_label_raises(monkeypatch):
    body = (
        b'<a href="https://sabr.box.com/s/abc123">SQL version</a>'
        b'<a href="https://sabr.box.com/s/def456">Microsoft Access version</a>'
    )
    _patch_transport(monkeypatch, lambda url, params=None, **kw: body)
    with pytest.raises(LahmanError, match="comma-delimited"):
        api.discover_shared_name()


def test_unparsable_folder_page_raises(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params=None, **kw: b"<html>login</html>")
    with pytest.raises(LahmanError, match="No file entries parsed"):
        api.fetch_table_index(SHARED_NAME)


def test_folder_without_csv_files_raises(monkeypatch):
    body = b'{"pageCount":1,"items":[{"typedID":"f_1","name":"readme2025.txt"}]}'
    _patch_transport(monkeypatch, lambda url, params=None, **kw: body)
    with pytest.raises(LahmanError, match=r"no \.csv files"):
        api.fetch_table_index(SHARED_NAME)


def test_html_download_raises(monkeypatch):
    _patch_transport(
        monkeypatch,
        lambda url, params=None, **kw: b"<!DOCTYPE html><html>error</html>",
    )
    with pytest.raises(LahmanError, match="returned HTML, not CSV") as excinfo:
        api.download_table(SHARED_NAME, "f_111", "Parks")
    # Download failures point at refresh() first — a stale cached index after
    # an annual release is the most likely cause.
    assert "fungo.lahman.refresh()" in str(excinfo.value)


def test_empty_download_raises(monkeypatch):
    _patch_transport(monkeypatch, lambda url, params=None, **kw: b"  \n")
    with pytest.raises(LahmanError, match="Empty response") as excinfo:
        api.download_table(SHARED_NAME, "f_111", "Parks")
    assert "fungo.lahman.refresh()" in str(excinfo.value)


def test_folder_page_without_page_count_treated_as_single_page(monkeypatch):
    body = b'{"items":[{"typedID":"f_9","name":"Parks.csv"}]}'
    calls = {"count": 0}

    def fake(url, params=None, **kw):
        calls["count"] += 1
        return body

    _patch_transport(monkeypatch, fake)
    assert api.fetch_table_index(SHARED_NAME) == {"Parks": "f_9"}
    assert calls["count"] == 1
