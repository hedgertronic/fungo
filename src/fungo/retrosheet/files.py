"""Retrosheet dataset download, cache, and CSV parsing.

Retrosheet is a static file host: each dataset is a zip on
``www.retrosheet.org``, refreshed in roughly twice-yearly bulk releases, with
no rate limits. Every accessor therefore downloads its zip once, extracts all
members into the user cache dir (``fungo/retrosheet/<dataset>/``), and parses
from disk on subsequent calls. There is no in-memory cache — rows are
re-parsed from the cached file on each call.

Verified file shapes (2024/2026 releases):

- ``gl{year}.zip`` -> ``gl{year}.txt``: headerless positional CSV, 161 fields
  per record, keyed by :data:`~fungo.retrosheet.fields.GAME_LOG_FIELDS`.
- ``{year}plays.zip`` -> ``{year}plays.csv``: headered, 177 labeled columns.
- ``{year}SKED.zip`` -> ``{year}schedule.csv``: 13 columns with a header row
  whose names collide (``League``/``Game`` twice), so rows are keyed by
  :data:`~fungo.retrosheet.fields.SCHEDULE_FIELDS` instead.
- ``biofile.zip`` -> ``biofile.csv``, ``biofile0.csv``, ``coaches.csv``,
  ``relatives.csv``: all headered.
- ``{year}csvs.zip`` -> ``{year}{gameinfo,teamstats,batting,pitching,
  fielding,allplayers,plays}.csv``: all headered. One bundle download serves
  every per-season accessor; the bundled plays file duplicates the dedicated
  ``{year}plays.zip`` content.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from pathlib import Path
from typing import Any

from fungo import http
from fungo.exceptions import RequestError, ValidationError
from fungo.retrosheet.fields import GAME_LOG_FIELDS, SCHEDULE_FIELDS

BASE_URL = "https://www.retrosheet.org"

# URL template and first covered season per dataset (``None`` = not
# year-scoped). The schedule suffix is lowercase ".zip" — the uppercase
# variant 404s. The per-season CSV bundles cover the parsed play-by-play
# era, the same span as the plays files.
DATASETS: dict[str, tuple[str, int | None]] = {
    "game_logs": (f"{BASE_URL}/gamelogs/gl{{year}}.zip", 1871),
    "plays": (f"{BASE_URL}/downloads/plays/{{year}}plays.zip", 1903),
    "schedule": (f"{BASE_URL}/schedule/{{year}}SKED.zip", 1877),
    "biofile": (f"{BASE_URL}/biofile.zip", None),
    "season": (f"{BASE_URL}/downloads/{{year}}/{{year}}csvs.zip", 1903),
}

CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser()
    / "fungo"
    / "retrosheet"
)


#####################################################################
# Download / cache
#####################################################################


def _coerce_year(dataset: str, year: int | str | None) -> int:
    """Validate ``year`` for a year-scoped dataset and coerce it to ``int``.

    Accessors normalize through this before building member filenames, so the
    name embedded in the URL and the name looked up in the cache always agree
    (``int(" 2024")`` and ``int("2024")`` both yield ``2024``).

    Args:
        dataset: A year-scoped :data:`DATASETS` key.
        year: Season, as an ``int`` or a numeric string.

    Returns:
        The season as an ``int``.

    Raises:
        ValidationError: On a missing or non-numeric ``year``, or a ``year``
            before the dataset's coverage.
    """
    if year is None:
        raise ValidationError(year, f"year (required for the {dataset!r} dataset)")
    try:
        year = int(year)
    except ValueError:
        raise ValidationError(year, "year") from None
    first_year = DATASETS[dataset][1]
    if first_year is not None and year < first_year:
        raise ValidationError(
            year, f"{dataset} year (Retrosheet coverage begins in {first_year})"
        )
    return year


def _dataset_url(dataset: str, year: int | str | None) -> str:
    """Resolve the download URL for ``dataset``, validating ``year``.

    Args:
        dataset: A :data:`DATASETS` key.
        year: Season for year-scoped datasets; ignored for ``"biofile"``.

    Returns:
        The fully substituted download URL.

    Raises:
        ValidationError: On an unknown dataset, a missing or non-numeric
            ``year`` for a year-scoped dataset, or a ``year`` before the
            dataset's coverage.
    """
    if dataset not in DATASETS:
        raise ValidationError(dataset, "dataset", valid_values=sorted(DATASETS))
    template, first_year = DATASETS[dataset]
    if first_year is None:
        return template
    return template.format(year=_coerce_year(dataset, year))


def _extract_zip(url: str, dataset: str) -> list[Path]:
    """Download a dataset zip and extract every file member into the cache dir.

    Members are written under ``CACHE_DIR/<dataset>/`` by basename (member
    names in Retrosheet zips are flat; taking the basename also guards
    against path traversal). Directory entries are skipped.

    Args:
        url: The zip's download URL.
        dataset: Cache subdirectory name.

    Returns:
        Paths of the extracted files.

    Raises:
        RequestError: On transport failure or a non-zip response body.
    """
    raw = http.request_bytes(url, timeout=120)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise RequestError(f"Response from {url} is not a zip archive") from exc
    target = CACHE_DIR / dataset
    target.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with archive:
        for info in archive.infolist():
            name = Path(info.filename).name
            if info.is_dir() or not name:
                continue
            path = target / name
            path.write_bytes(archive.read(info))
            paths.append(path)
    return paths


def _member_bytes(
    dataset: str,
    year: int | str | None,
    member: str,
    *,
    force_refresh: bool = False,
) -> bytes:
    """Return one cached zip member, downloading the dataset zip if needed.

    Args:
        dataset: A :data:`DATASETS` key.
        year: Season for year-scoped datasets.
        member: Filename of the extracted member to read.
        force_refresh: Re-download the zip even if the member is cached.

    Returns:
        The member's raw bytes.

    Raises:
        ValidationError: On a bad dataset/year (validated before any I/O).
        RequestError: On download failure or if the zip lacks ``member``.
    """
    url = _dataset_url(dataset, year)
    path = CACHE_DIR / dataset / member
    if force_refresh or not path.exists():
        _extract_zip(url, dataset)
        if not path.exists():
            raise RequestError(f"{member!r} is not a member of {url}")
    return path.read_bytes()


def refresh(dataset: str, year: int | str | None = None) -> list[Path]:
    """Re-download one dataset zip, overwriting its cached members.

    Args:
        dataset: One of ``"game_logs"``, ``"plays"``, ``"schedule"``,
            ``"biofile"``, ``"season"``.
        year: Season for year-scoped datasets; ignored for ``"biofile"``.

    Returns:
        Paths of the extracted cache files.

    Raises:
        ValidationError: On a bad dataset name or year.
        RequestError: On download failure.
    """
    url = _dataset_url(dataset, year)
    return _extract_zip(url, dataset)


def clear_cache() -> int:
    """Delete every cached Retrosheet file and return the count deleted.

    Empty dataset subdirectories are left in place; the next accessor call
    re-downloads into them.

    Returns:
        Number of cache files deleted.
    """
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for path in sorted(CACHE_DIR.rglob("*")):
        if path.is_file():
            path.unlink()
            count += 1
    return count


#####################################################################
# Positional-CSV parsing (headerless / colliding-header files)
#####################################################################


def _read_records(raw: bytes) -> list[list[str]]:
    """Decode bytes as ``utf-8-sig`` and parse into non-empty CSV records."""
    text = raw.decode("utf-8-sig")
    return [record for record in csv.reader(io.StringIO(text)) if record]


def _zip_records(
    records: list[list[str]],
    fields: tuple[str, ...],
    source: str,
) -> list[dict[str, Any]]:
    """Key positional CSV records by ``fields``, one dict per record.

    Args:
        records: Parsed CSV records.
        fields: Positional field names; every record must match its length.
        source: Filename used in the error message on a width mismatch.

    Returns:
        One dict per record; every value is a string.

    Raises:
        RequestError: If a record's width differs from ``fields`` — the
            Retrosheet file format no longer matches the embedded constants.
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        if len(record) != len(fields):
            raise RequestError(
                f"{source} record has {len(record)} fields, expected "
                f"{len(fields)} — the Retrosheet file format may have changed"
            )
        rows.append(dict(zip(fields, record, strict=True)))
    return rows


#####################################################################
# Game logs / plays / schedules
#####################################################################


def get_game_logs(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch the Retrosheet game logs for one season (one row per game).

    The ``gl{year}.txt`` member is headerless positional CSV; rows are keyed
    by the 161 names in :data:`~fungo.retrosheet.fields.GAME_LOG_FIELDS`.

    Args:
        year: Season, 1871 or later.
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per game; every value is a string (``""`` for empty).

    Raises:
        ValidationError: If ``year`` predates game-log coverage.
        RequestError: On download failure or an unexpected file format.
    """
    year = _coerce_year("game_logs", year)
    raw = _member_bytes("game_logs", year, f"gl{year}.txt", force_refresh=force_refresh)
    return _zip_records(_read_records(raw), GAME_LOG_FIELDS, f"gl{year}.txt")


def get_plays(year: int | str, *, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch the parsed play-by-play file for one season (one row per event).

    The ``{year}plays.csv`` member is headered (177 labeled columns: batter,
    pitcher, count, pitch sequence, outcome flags, runner advancement,
    fielder credits, lineup state); rows are keyed by that header.

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per play event; every value is a string (``""`` for empty).

    Raises:
        ValidationError: If ``year`` predates play-by-play coverage.
        RequestError: On download failure.
    """
    year = _coerce_year("plays", year)
    raw = _member_bytes("plays", year, f"{year}plays.csv", force_refresh=force_refresh)
    return http.parse_csv(raw)


def get_schedule(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch the season schedule (one row per scheduled game).

    The ``{year}schedule.csv`` member carries a header row whose names
    collide (``League`` and ``Game`` each appear twice), so that row is
    dropped and rows are keyed by the 13 names in
    :data:`~fungo.retrosheet.fields.SCHEDULE_FIELDS`. Header detection is by
    the first cell: data rows start with a ``yyyymmdd`` date, so a headerless
    file also parses correctly.

    Args:
        year: Season, 1877 or later (the next season's schedule is published
            ahead of time).
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per scheduled game; every value is a string.

    Raises:
        ValidationError: If ``year`` predates schedule coverage.
        RequestError: On download failure or an unexpected file format.
    """
    year = _coerce_year("schedule", year)
    raw = _member_bytes(
        "schedule", year, f"{year}schedule.csv", force_refresh=force_refresh
    )
    records = _read_records(raw)
    if records and not records[0][0].isdigit():
        records = records[1:]
    return _zip_records(records, SCHEDULE_FIELDS, f"{year}schedule.csv")


#####################################################################
# Biographical files (biofile.zip)
#####################################################################


def get_biofile(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch the Retrosheet biofile (one row per person, all roles).

    Covers everyone with a Retrosheet ID — players, managers, coaches, and
    umpires — with names, birth/death data, debut/final-game dates per role,
    bats/throws, and height/weight. Keys are the source header's uppercase
    names (``PLAYERID``, ``LAST``, ``FIRST``, ``BIRTHDATE``, ...). The same
    zip download also serves :func:`get_coaches` and :func:`get_relatives`.

    Args:
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per person; every value is a string (``""`` for empty).

    Raises:
        RequestError: On download failure.
    """
    raw = _member_bytes("biofile", None, "biofile.csv", force_refresh=force_refresh)
    return http.parse_csv(raw)


def get_coaches(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch coaching assignments (one row per person-season-team-role).

    Backed by the ``coaches.csv`` member of ``biofile.zip`` (columns ``id``,
    ``year``, ``team``, ``role``, ``start``, ``end``); a cached biofile
    download is reused.

    Args:
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per coaching stint; every value is a string.

    Raises:
        RequestError: On download failure.
    """
    raw = _member_bytes("biofile", None, "coaches.csv", force_refresh=force_refresh)
    return http.parse_csv(raw)


def get_relatives(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch family relationships between Retrosheet people.

    Backed by the ``relatives.csv`` member of ``biofile.zip`` (columns
    ``id1``, ``relation``, ``id2``); a cached biofile download is reused.

    Args:
        force_refresh: Re-download the zip even if a cached copy exists.

    Returns:
        One dict per relationship; every value is a string.

    Raises:
        RequestError: On download failure.
    """
    raw = _member_bytes("biofile", None, "relatives.csv", force_refresh=force_refresh)
    return http.parse_csv(raw)


#####################################################################
# Per-season CSV bundle ({year}csvs.zip)
#####################################################################


def _season_table(
    year: int | str,
    table: str,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Fetch one headered table from the per-season CSV bundle.

    One ``{year}csvs.zip`` download extracts every bundle member, so the
    first accessor call for a season pays the download and the rest read
    from the cache.

    Args:
        year: Season, 1903 or later.
        table: Bundle table name (``gameinfo``, ``batting``, ...).
        force_refresh: Re-download the bundle even if cached.

    Returns:
        One dict per row; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    year = _coerce_year("season", year)
    raw = _member_bytes(
        "season", year, f"{year}{table}.csv", force_refresh=force_refresh
    )
    return http.parse_csv(raw)


def get_gameinfo(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch per-game metadata for one season (one row per game).

    Columns cover teams, park, date, start time, day/night, attendance,
    weather, umpire crew, winning/losing/save pitchers, and line-score runs.

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per game; every value is a string (``""`` for empty).

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "gameinfo", force_refresh=force_refresh)


def get_batting(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch per-game batting lines for one season (one row per player-game).

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per batting line; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "batting", force_refresh=force_refresh)


def get_pitching(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch per-game pitching lines for one season (one row per player-game).

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per pitching line; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "pitching", force_refresh=force_refresh)


def get_fielding(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch per-game fielding lines for one season (one row per player-game-position).

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per fielding line; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "fielding", force_refresh=force_refresh)


def get_teamstats(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch per-game team totals for one season (one row per team-game).

    Columns cover inning-by-inning runs, batting/pitching/fielding totals,
    the manager, and the starting lineup.

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per team-game; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "teamstats", force_refresh=force_refresh)


def get_allplayers(
    year: int | str, *, force_refresh: bool = False
) -> list[dict[str, Any]]:
    """Fetch the season player roster (one row per player-team).

    Columns cover bats/throws, games played by position, and first/last game
    dates for the season.

    Args:
        year: Season, 1903 or later.
        force_refresh: Re-download the season bundle even if cached.

    Returns:
        One dict per player-team stint; every value is a string.

    Raises:
        ValidationError: If ``year`` predates bundle coverage.
        RequestError: On download failure.
    """
    return _season_table(year, "allplayers", force_refresh=force_refresh)
