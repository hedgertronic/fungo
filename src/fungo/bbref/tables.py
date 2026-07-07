"""Baseball-Reference HTML table extraction.

B-R defers rendering of many stat tables by shipping them inside HTML comments
(``<div id="all_X"> ... <!-- <table id="X">... --> ...``); on-page JavaScript
uncomments them on scroll. Since the 2024 "upgraded stats tables" rollout the
split is dynamic: primary tables arrive live, secondary ones commented, and
which is which shifts per page type. The robust strategy used here: strip the
comment markers from the whole document, then parse once — every table
resolves regardless of state.

Cells are addressed by their ``data-stat`` attribute (B-R's stable column
identifier) rather than display headers. Following fungo's CSV convention,
every value is a string (``""`` for empty cells); callers cast themselves.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from fungo.exceptions import BBRefError

#####################################################################
# Parsing helpers
#####################################################################


def _soup(html: str) -> BeautifulSoup:
    """Parse a B-R page with comment markers stripped, so deferred tables
    resolve as live DOM.

    Args:
        html: Raw page HTML.

    Returns:
        The parsed document.
    """
    return BeautifulSoup(html.replace("<!--", "").replace("-->", ""), "html.parser")


def _rows_from_table(table: Any) -> list[dict[str, Any]]:
    """Convert a ``<table>`` element into row dicts keyed by ``data-stat``.

    Skips B-R's repeated in-body header rows (``class="thead"``) and spacer
    rows. Cells without a ``data-stat`` attribute are ignored.

    Args:
        table: A bs4 ``<table>`` Tag.

    Returns:
        One dict per data row; all values are strings.
    """
    rows: list[dict[str, Any]] = []
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        classes = tr.get("class") or []
        if "thead" in classes or "spacer" in classes:
            continue
        row: dict[str, Any] = {}
        for cell in tr.find_all(["th", "td"]):
            stat = cell.get("data-stat")
            if stat:
                row[stat] = cell.get_text(strip=True)
        if row and any(v for v in row.values()):
            rows.append(row)
    return rows


#####################################################################
# Table extraction
#####################################################################


def extract_table(html: str, table_id: str) -> list[dict[str, Any]]:
    """Extract one table from a B-R page by its ``id``, live or commented.

    Args:
        html: Raw page HTML (as fetched — comments handled internally).
        table_id: The table's ``id`` attribute (e.g.
            ``"players_standard_batting"``).

    Returns:
        Row dicts keyed by ``data-stat``; all values are strings.

    Raises:
        BBRefError: If no table with that id exists on the page.
    """
    table = _soup(html).find("table", id=table_id)
    if table is None:
        available = ", ".join(list_tables(html)[:15])
        raise BBRefError(
            f"No table {table_id!r} on page. Available tables: {available}"
        )
    return _rows_from_table(table)


def extract_all_tables(html: str) -> dict[str, list[dict[str, Any]]]:
    """Extract every id-bearing table from a B-R page, live or commented.

    One fetched page often carries a dozen-plus tables; extracting them all at
    once is the polite pattern — one request, everything the page holds.

    B-R reuses table ids on some pages (the season standings page carries
    ``standings_E`` twice: AL first, NL second, in document order). Duplicates
    get a positional suffix (``standings_E``, ``standings_E_2``) rather than
    silently overwriting each other.

    Args:
        html: Raw page HTML.

    Returns:
        Mapping of table id -> row dicts. Tables without an ``id`` are skipped.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for t in _soup(html).find_all("table", id=True):
        key = str(t["id"])
        if key in out:
            n = 2
            while f"{key}_{n}" in out:
                n += 1
            key = f"{key}_{n}"
        out[key] = _rows_from_table(t)
    return out


def list_tables(html: str) -> list[str]:
    """List the ids of every table on a B-R page, live or commented.

    Args:
        html: Raw page HTML.

    Returns:
        Table ids in document order.
    """
    return [str(t["id"]) for t in _soup(html).find_all("table", id=True)]
