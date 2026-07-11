"""Chadwick Bureau player ID cross-reference lookup.

Maps MLBAM <-> FanGraphs <-> Baseball-Reference <-> Retrosheet IDs. Source:
https://github.com/chadwickbureau/register (split into 16 shards by the last hex
char of ``key_person``).

The ~6 MB register is fetched on demand via :func:`fungo.http.request_bytes`
and cached under the stdlib user cache dir
(``$XDG_CACHE_HOME``/``~/.cache`` -> ``fungo/chadwick_people.csv``). Call
:func:`refresh` or pass ``force_refresh=True`` to update it.

The register's rookie lag is column-specific (``key_fangraphs`` stays blank
for ~a season after debut), so the ``mlbam_to_*`` converters fall back to the
MLB Stats API's xrefIds (:func:`xref_ids`) when the register has no value.
"""

from __future__ import annotations

import csv
import os
import time
import warnings
from pathlib import Path
from typing import Any

from fungo import http
from fungo.exceptions import StaleCacheWarning

CHADWICK_SHARD_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people-{}.csv"
CHADWICK_SHARDS = "0123456789abcdef"

STATSAPI_PERSON_URL = "https://statsapi.mlb.com/api/v1/people/{}"

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser() / "fungo"
CACHE_FILE = CACHE_DIR / "chadwick_people.csv"

# The register updates monthly in-season; a cache older than one update cycle
# (plus slack) is worth flagging.
STALE_AFTER_DAYS = 35

# In-memory cache — populated on first lookup.
_ROWS: list[dict[str, Any]] | None = None


#####################################################################
# Download / cache
#####################################################################


def _fetch_all_shards() -> str:
    """Download all 16 Chadwick shards and concatenate them into one CSV blob.

    Returns:
        The combined CSV text (single header row followed by all data rows).
    """
    header: str | None = None
    out_lines: list[str] = []
    for shard in CHADWICK_SHARDS:
        url = CHADWICK_SHARD_URL.format(shard)
        text = http.request_bytes(url, timeout=60).decode("utf-8")
        lines = text.splitlines()
        if not lines:
            continue
        if header is None:
            header = lines[0]
            out_lines.append(header)
        out_lines.extend(lines[1:])
        time.sleep(0.2)  # be polite to GitHub
    return "\n".join(out_lines) + "\n"


def refresh() -> Path:
    """Re-download the Chadwick register, overwriting the on-disk cache.

    Returns:
        Path to the written cache file.
    """
    global _ROWS
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    text = _fetch_all_shards()
    CACHE_FILE.write_text(text, encoding="utf-8")
    _ROWS = None
    return CACHE_FILE


def _load(force_refresh: bool = False) -> list[dict[str, Any]]:
    """Load the register into memory, downloading/refreshing the cache if needed.

    When the on-disk cache is older than ``STALE_AFTER_DAYS`` days, a
    :class:`~fungo.exceptions.StaleCacheWarning` recommends
    :func:`fungo.lookup.refresh` — the register updates monthly in-season.
    The warning fires only when the disk cache is read into the cold
    in-memory cache (at most once per process); it never auto-refreshes,
    because a surprise ~6 MB download inside a lookup call is worse than a
    warning.

    Args:
        force_refresh: Re-download before loading.

    Returns:
        The full list of register rows.
    """
    global _ROWS
    if _ROWS is not None and not force_refresh:
        return _ROWS
    if force_refresh or not CACHE_FILE.exists():
        refresh()
    elif time.time() - CACHE_FILE.stat().st_mtime > STALE_AFTER_DAYS * 86400:
        warnings.warn(
            f"The cached Chadwick register at {CACHE_FILE} is more than "
            f"{STALE_AFTER_DAYS} days old; the register updates monthly "
            "in-season. Call fungo.lookup.refresh() to re-download it.",
            StaleCacheWarning,
            stacklevel=3,
        )
    with open(CACHE_FILE, encoding="utf-8") as f:
        _ROWS = list(csv.DictReader(f))
    return _ROWS


#####################################################################
# Lookup
#####################################################################


def lookup(
    name: str | None = None,
    mlbam: int | str | None = None,
    fangraphs: int | str | None = None,
    bbref: str | None = None,
    bbref_minors: str | None = None,
    retro: str | None = None,
    *,
    mlb_only: bool = True,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Look up players by any identifier or by name substring.

    Args:
        name: Full / first / last name substring (case-insensitive).
        mlbam: MLBAM (Savant) player ID.
        fangraphs: FanGraphs player ID.
        bbref: Baseball-Reference major-league ID (e.g. ``"troutmi01"``).
        bbref_minors: Baseball-Reference minor-league ID.
        retro: Retrosheet player ID.
        mlb_only: If True, restrict to players with any MLB seasons.
        force_refresh: Re-download the register before looking up.

    Returns:
        Matching rows. Keys include ``key_mlbam``, ``key_fangraphs``,
        ``key_bbref``, ``key_bbref_minors``, ``key_retro``, ``name_first``,
        ``name_last``, ``name_given``, ``mlb_played_first``, ``mlb_played_last``.
    """
    rows = _load(force_refresh=force_refresh)
    name_lc = name.lower() if name else None

    out = []
    for r in rows:
        if mlbam is not None and r.get("key_mlbam") != str(mlbam):
            continue
        if fangraphs is not None and r.get("key_fangraphs") != str(fangraphs):
            continue
        if bbref is not None and r.get("key_bbref") != str(bbref):
            continue
        if bbref_minors is not None and r.get("key_bbref_minors") != str(bbref_minors):
            continue
        if retro is not None and r.get("key_retro") != str(retro):
            continue
        if name_lc is not None:
            fn = (r.get("name_first") or "").lower()
            ln = (r.get("name_last") or "").lower()
            full = f"{fn} {ln}".strip()
            if name_lc not in fn and name_lc not in ln and name_lc not in full:
                continue
        if mlb_only and not (r.get("mlb_played_first") or r.get("mlb_played_last")):
            continue
        out.append(r)
    return out


#####################################################################
# MLB Stats API xref IDs
#####################################################################


def xref_ids(mlbam: int | str) -> dict[str, str]:
    """Fetch cross-reference IDs for a player from the MLB Stats API.

    Queries ``statsapi.mlb.com/api/v1/people/{mlbam}?hydrate=xrefId`` and
    returns the ``xrefIds`` list as an ``xrefType -> xrefId`` mapping. Types
    include ``fangraphs``, ``retrosheet``, and ``lahman`` (the ``lahman``
    value is the Baseball-Reference ID for modern players). The MLB Stats API
    carries FanGraphs IDs within days of a player's debut, far ahead of the
    Chadwick register's ~season-long ``key_fangraphs`` lag — this is the
    live-fallback source behind :func:`mlbam_to_fangraphs` and
    :func:`mlbam_to_bbref`.

    Args:
        mlbam: MLBAM (Savant) player ID.

    Returns:
        Mapping of ``xrefType`` to ``xrefId``; empty when the API has none.

    Raises:
        RequestError: On transport failure.
    """
    data = http.request_json(
        STATSAPI_PERSON_URL.format(mlbam), params={"hydrate": "xrefId"}
    )
    if not isinstance(data, dict):
        return {}
    people = data.get("people") or []
    if not people:
        return {}
    xrefs = people[0].get("xrefIds") or []
    return {
        str(x["xrefType"]): str(x["xrefId"])
        for x in xrefs
        if x.get("xrefType") and x.get("xrefId")
    }


#####################################################################
# ID converters
#####################################################################


def mlbam_to_fangraphs(mlbam: int | str, *, live_fallback: bool = True) -> str | None:
    """Convert an MLBAM ID to a FanGraphs ID, or ``None`` if not found.

    The Chadwick register is consulted first. Its ``key_fangraphs`` column
    lags roughly a full season for current-season debutants, while the MLB
    Stats API's xrefIds carry the FanGraphs ID within days of debut — so when
    the register row is missing or its FanGraphs key is blank, a single
    :func:`xref_ids` call fills the gap (the ``fangraphs`` xref type).

    Args:
        mlbam: MLBAM (Savant) player ID.
        live_fallback: When True, fall back to the MLB Stats API xrefIds if
            the register has no value. False keeps the lookup fully offline.

    Returns:
        The FanGraphs ID, or ``None`` if neither source has one.

    Raises:
        RequestError: If the live fallback call fails.
    """
    matches = lookup(mlbam=mlbam, mlb_only=False)
    value = matches[0].get("key_fangraphs") if matches else None
    if value:
        return str(value)
    if live_fallback:
        return xref_ids(mlbam).get("fangraphs")
    return None


def mlbam_to_bbref(mlbam: int | str, *, live_fallback: bool = True) -> str | None:
    """Convert an MLBAM ID to a Baseball-Reference ID, or ``None`` if not found.

    The Chadwick register is consulted first. Its ``key_bbref`` column lands
    within about one monthly update of a player's debut, but rows for the
    newest debutants can still be missing or blank — so when they are, a
    single :func:`xref_ids` call fills the gap (the ``lahman`` xref type,
    which is the Baseball-Reference ID for modern players).

    Args:
        mlbam: MLBAM (Savant) player ID.
        live_fallback: When True, fall back to the MLB Stats API xrefIds if
            the register has no value. False keeps the lookup fully offline.

    Returns:
        The Baseball-Reference ID, or ``None`` if neither source has one.

    Raises:
        RequestError: If the live fallback call fails.
    """
    matches = lookup(mlbam=mlbam, mlb_only=False)
    value = matches[0].get("key_bbref") if matches else None
    if value:
        return str(value)
    if live_fallback:
        return xref_ids(mlbam).get("lahman")
    return None


def fangraphs_to_mlbam(fangraphs: int | str) -> str | None:
    """Convert a FanGraphs ID to an MLBAM ID, or ``None`` if not found."""
    matches = lookup(fangraphs=fangraphs, mlb_only=False)
    if not matches:
        return None
    return matches[0].get("key_mlbam") or None


def bbref_to_mlbam(bbref: str) -> str | None:
    """Convert a Baseball-Reference ID to an MLBAM ID, or ``None`` if not found."""
    matches = lookup(bbref=bbref, mlb_only=False)
    if not matches:
        return None
    return matches[0].get("key_mlbam") or None
