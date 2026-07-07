"""Baseball Savant (Statcast) pitch-level search.

Returns raw ``list[dict]`` (one dict per pitch); all CSV values are strings —
callers cast themselves. Built on :mod:`fungo.http` for transport, retry, and
CSV parsing; this module adds the Savant-specific HTML-vs-CSV detection (Savant
serves an HTML error page, not a 4xx, when params are unacceptable).

Gotchas folded in from the Statcast skill references:

- **30,000-row hard cap.** :func:`search_pitches` auto-chunks ranges longer
  than 5 days into 1-day requests, fanned through :func:`fungo.http.map_concurrent`.
  Even single high-volume days can approach the cap — add filters.
- **Pipe-separated params must NOT be URL-encoded.** ``http.request_bytes`` uses
  ``safe="|"``. Join multi-value filters with ``"|"`` (e.g. ``"FF|SL|CH|"``).
- **MiLB search:** pass ``level="milb"`` to hit ``/statcast-search-minors/csv``.
  MLBAM IDs are shared across MLB/MiLB. Coverage: AAA 2023+, PCL+Charlotte 2022,
  Single-A FSL 2021+; no Double-A / High-A.
- **All CSV values are strings.** Empty cells are ``""``. Pre-2015 rows are Pitch
  F/X, not Statcast (spin/EV/LA unreliable or missing).

Pitch-by-pitch bat-tracking / miss-distance columns present in the
``type=details`` search output (verified live 2026-07; absent from older docs):

    bat_speed                                   bat head speed, mph
    swing_length                                swing path length, feet
    miss_distance                               whiff miss distance, inches
                                                (per-pitch; ~6.19 on a whiff)
    attack_angle                                vertical bat angle at intercept, degrees
    attack_direction                            horizontal bat direction at intercept,
                                                degrees (negative = toward pull side)
    swing_path_tilt                             swing-plane tilt, degrees
    intercept_ball_minus_batter_pos_x_inches    ball-vs-batter X offset, inches
    intercept_ball_minus_batter_pos_y_inches    ball-vs-batter Y offset, inches

Related Hawk-Eye columns also present: ``arm_angle`` (deg),
``api_break_z_with_gravity`` / ``api_break_x_arm`` / ``api_break_x_batter_in``
(inches), ``hyper_speed`` (mph).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fungo import constants, http
from fungo.constants import resolve_team  # re-exported for convenience
from fungo.exceptions import SavantError, ValidationError
from fungo.statcast.physics import axis_to_clock

#####################################################################
# Constants
#####################################################################

BASE_URL = "https://baseballsavant.mlb.com"
SEARCH_PATH_MLB = "/statcast_search/csv"
SEARCH_PATH_MILB = "/statcast-search-minors/csv"
MAX_ROWS_PER_QUERY = 30_000
DEFAULT_CHUNK_DAYS = 1
DEFAULT_DELAY = 1.0  # seconds between chunked requests
_VALID_LEVELS = {"mlb", "milb"}
_VALID_PLAYER_TYPES = {"pitcher", "batter"}
_VALID_SIDES = {"any", "home", "away"}

__all__ = [
    "aggregate_pitcher_arsenal",
    "get_pitcher_arsenal",
    "resolve_team",
    "search_game",
    "search_matchup",
    "search_pitches",
    "search_team",
    "statcast_search",
]


#####################################################################
# Core: _fetch_csv (HTML detection lives here)
#####################################################################


def _fetch_csv(
    url: str, params: dict[str, Any] | None = None, **kw: Any
) -> list[dict[str, Any]]:
    """Fetch a CSV endpoint from Baseball Savant and return ``list[dict]``.

    Wraps :func:`fungo.http.request_bytes` + :func:`fungo.http.parse_csv`,
    adding Savant-specific HTML detection: Savant returns an HTML page (HTTP 200)
    rather than a 4xx when given parameters it cannot serve as CSV. That HTML is
    detected here and surfaced as a :class:`~fungo.exceptions.SavantError`.

    Args:
        url: Full URL (query string optional).
        params: Query parameters to append. ``None`` values are dropped by
            transport.
        **kw: Forwarded to :func:`fungo.http.request_bytes` (``retries``,
            ``timeout``, ``headers``).

    Returns:
        ``list[dict]`` — one dict per CSV row; ``[]`` if there are no data rows.

    Raises:
        SavantError: If the response body is HTML rather than CSV.
        RequestError: On transport failure (raised by ``request_bytes``).
    """
    raw = http.request_bytes(url, params=params, **kw)

    text = raw.decode("utf-8-sig", errors="replace")
    if text.lstrip()[:200].lower().startswith(("<!doctype", "<html")):
        raise SavantError(
            f"Received HTML instead of CSV from {url}. "
            "The endpoint may not support the given parameters."
        )

    return http.parse_csv(text)


#####################################################################
# Search base params
#####################################################################


def _search_base_params(player_type: str = "pitcher") -> dict[str, str]:
    return {
        "all": "true",
        "type": "details",
        "player_type": player_type,
        "group_by": "name",
        "sort_col": "pitches",
        "sort_order": "desc",
        "min_pitches": "0",
        "min_results": "0",
        "min_abs": "0",
    }


#####################################################################
# Statcast search
#####################################################################


def search_pitches(
    start_date: str,
    end_date: str,
    player_type: str = "pitcher",
    player_id: int | str | None = None,
    level: str = "mlb",
    *,
    max_workers: int = 4,
    delay: float = DEFAULT_DELAY,
    progress: bool = False,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Fetch pitch-level Statcast data from Baseball Savant.

    Ranges spanning more than 5 days are auto-chunked into 1-day requests (the
    30k-row cap defense) and fanned through :func:`fungo.http.map_concurrent`
    with a bounded thread pool, a politeness ``delay`` between submissions, and
    opt-in progress. Per-day results are flattened in date order.

    Args:
        start_date: ``"YYYY-MM-DD"`` start (inclusive).
        end_date: ``"YYYY-MM-DD"`` end (inclusive).
        player_type: ``"pitcher"`` or ``"batter"``.
        player_id: MLBAM player ID. Emitted as ``pitchers_lookup[]`` /
            ``batters_lookup[]`` per ``player_type``. Optional.
        level: ``"mlb"`` (default) or ``"milb"``.
        max_workers: Max concurrent fetches when chunking.
        delay: Seconds between chunk submissions.
        progress: If True, show a progress bar when ``rich`` is installed.
        **filters: Additional raw Savant search params (``team``, ``hfPT``,
            ``hfTeam``, etc.), passed through verbatim.

    Returns:
        ``list[dict]`` — one dict per pitch.

    Raises:
        SavantError: If ``start_date`` is after ``end_date``, or a response is
            HTML rather than CSV.
    """
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(start_date, "start_date", ["YYYY-MM-DD format"]) from None
    try:
        dt_end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(end_date, "end_date", ["YYYY-MM-DD format"]) from None

    if dt_start > dt_end:
        raise SavantError(f"start_date {start_date} is after end_date {end_date}")

    if player_type not in _VALID_PLAYER_TYPES:
        raise ValidationError(player_type, "player_type", sorted(_VALID_PLAYER_TYPES))

    if level not in _VALID_LEVELS:
        raise ValidationError(level, "level", sorted(_VALID_LEVELS))
    path = SEARCH_PATH_MILB if level == "milb" else SEARCH_PATH_MLB
    base = f"{BASE_URL}{path}"

    base_params = _search_base_params(player_type)

    if player_id is not None:
        key = "pitchers_lookup[]" if player_type == "pitcher" else "batters_lookup[]"
        base_params[key] = str(player_id)

    base_params.update(filters)

    day_span = (dt_end - dt_start).days
    if day_span <= 5:
        single = dict(base_params)
        single["game_date_gt"] = start_date
        single["game_date_lt"] = end_date
        return _fetch_csv(base, params=single)

    days: list[str] = []
    current = dt_start
    while current <= dt_end:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    def fetch_day(day: str) -> list[dict[str, Any]]:
        day_params = dict(base_params)
        day_params["game_date_gt"] = day
        day_params["game_date_lt"] = day
        return _fetch_csv(base, params=day_params)

    per_day = http.map_concurrent(
        fetch_day,
        days,
        max_workers=max_workers,
        delay=delay,
        progress=progress,
        label="statcast_search",
    )
    return [row for day_rows in per_day for row in day_rows]


def statcast_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Alias for :func:`search_pitches`.

    Retained for callers familiar with the pre-1.0 API and pybaseball-style
    naming. New code should prefer ``search_pitches`` inside the
    ``fungo.statcast`` namespace.
    """
    return search_pitches(*args, **kwargs)


#####################################################################
# Convenience query wrappers
#####################################################################


def search_game(
    game_pk: int | str, level: str = "mlb", **filters: Any
) -> list[dict[str, Any]]:
    """Fetch every pitch from a single game by ``game_pk``.

    Args:
        game_pk: MLB game_pk.
        level: ``"mlb"`` or ``"milb"``.
        **filters: Additional raw Savant search params.

    Returns:
        ``list[dict]`` — one pitch per row.
    """
    if level not in _VALID_LEVELS:
        raise ValidationError(level, "level", sorted(_VALID_LEVELS))
    path = SEARCH_PATH_MILB if level == "milb" else SEARCH_PATH_MLB
    params = _search_base_params()
    params["game_pk"] = str(game_pk)
    params.update(filters)
    return _fetch_csv(f"{BASE_URL}{path}", params=params)


def search_matchup(
    pitcher_id: int | str,
    batter_id: int | str,
    start_date: str,
    end_date: str,
    level: str = "mlb",
    *,
    delay: float = DEFAULT_DELAY,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Fetch every pitch between one pitcher and one batter over a date range.

    Args:
        pitcher_id: MLBAM pitcher ID.
        batter_id: MLBAM batter ID.
        start_date: ``"YYYY-MM-DD"`` (inclusive).
        end_date: ``"YYYY-MM-DD"`` (inclusive).
        level: ``"mlb"`` or ``"milb"``.
        delay: Seconds between chunk submissions.
        **filters: Additional raw Savant search params.

    Returns:
        ``list[dict]`` — one pitch per row.
    """
    matchup_filters = dict(filters)
    matchup_filters["pitchers_lookup[]"] = str(pitcher_id)
    matchup_filters["batters_lookup[]"] = str(batter_id)
    return search_pitches(
        start_date,
        end_date,
        player_type="pitcher",
        player_id=None,
        level=level,
        delay=delay,
        **matchup_filters,
    )


def search_team(
    team: str,
    start_date: str,
    end_date: str,
    side: str = "any",
    level: str = "mlb",
    *,
    delay: float = DEFAULT_DELAY,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Fetch every pitch involving a team over a date range.

    The ``team`` argument is resolved via :func:`fungo.constants.resolve_team`,
    so a code (``"LAD"``), full name, city, or alias (``"Dodgers"``) all work.

    Args:
        team: Team code / name / city / alias.
        start_date: ``"YYYY-MM-DD"`` (inclusive).
        end_date: ``"YYYY-MM-DD"`` (inclusive).
        side: ``"any"`` (team on either side), ``"home"``, or ``"away"``.
        level: ``"mlb"`` or ``"milb"``.
        delay: Seconds between chunk submissions.
        **filters: Additional raw Savant search params.

    Returns:
        ``list[dict]`` — one pitch per row.

    Raises:
        ValidationError: If ``team`` resolves to no known club.
    """
    if side not in _VALID_SIDES:
        raise ValidationError(side, "side", sorted(_VALID_SIDES))
    code = constants.resolve_team(team)
    team_filters = dict(filters)
    if side == "home":
        team_filters["home_team"] = code
    elif side == "away":
        team_filters["away_team"] = code
    else:
        team_filters["hfTeam"] = f"{code}|"
    return search_pitches(
        start_date,
        end_date,
        player_type="pitcher",
        player_id=None,
        level=level,
        delay=delay,
        **team_filters,
    )


#####################################################################
# Aggregation
#####################################################################

_ARSENAL_METRICS: tuple[str, ...] = (
    "release_speed",
    "release_spin_rate",
    "effective_speed",
    "release_extension",
    "release_pos_x",
    "release_pos_z",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "launch_speed",
    "launch_angle",
    "spin_axis",
)


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def aggregate_pitcher_arsenal(
    rows: list[dict[str, Any]],
    group_by: tuple[str, ...] = ("pitcher", "pitch_type"),
    metrics: tuple[str, ...] = _ARSENAL_METRICS,
) -> list[dict[str, Any]]:
    """Aggregate pitch-level rows into per-group summaries.

    Returns one dict per group (default ``(pitcher, pitch_type)``) with the group
    keys, ``player_name`` / ``p_throws`` carried from the first member if present,
    ``n_pitches``, ``usage_pct`` (share of that pitcher's total pitches when
    grouping on ``pitcher``), ``avg_<metric>`` means (``None`` if all missing),
    and ``avg_tilt`` (clock string from ``avg_spin_axis`` via
    :func:`~fungo.statcast.physics.axis_to_clock`) when spin axis is present.

    Args:
        rows: ``list[dict]`` from :func:`search_pitches`.
        group_by: Column names to group on.
        metrics: Metric columns to average.

    Returns:
        ``list[dict]`` — one summary per group.
    """
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = tuple(r.get(k, "") for k in group_by)
        groups[key].append(r)

    per_pitcher: dict[str, int] = defaultdict(int)
    pitcher_idx = group_by.index("pitcher") if "pitcher" in group_by else None
    if pitcher_idx is not None:
        for key, grp in groups.items():
            per_pitcher[key[pitcher_idx]] += len(grp)

    out: list[dict[str, Any]] = []
    for key, grp in groups.items():
        row: dict[str, Any] = {group_by[i]: key[i] for i in range(len(group_by))}
        first = grp[0]
        for carry in ("player_name", "p_throws"):
            if carry in first and carry not in row:
                row[carry] = first.get(carry, "")
        row["n_pitches"] = len(grp)
        if pitcher_idx is not None:
            total = per_pitcher[key[pitcher_idx]]
            row["usage_pct"] = 100.0 * len(grp) / total if total else 0.0

        for m in metrics:
            vals = [_coerce_float(r.get(m)) for r in grp]
            row[f"avg_{m}"] = _mean(vals)

        axis = row.get("avg_spin_axis")
        if axis is not None:
            row["avg_tilt"] = axis_to_clock(axis)

        out.append(row)
    return out


#####################################################################
# High-level composition
#####################################################################


def get_pitcher_arsenal(
    pitcher_id: int | str,
    start_date: str,
    end_date: str,
    level: str = "mlb",
    **filters: Any,
) -> list[dict[str, Any]]:
    """Fetch a pitcher's pitch-level data and aggregate into an arsenal summary.

    Convenience wrapper: :func:`search_pitches` + :func:`aggregate_pitcher_arsenal`.

    Args:
        pitcher_id: MLBAM pitcher ID.
        start_date: ``"YYYY-MM-DD"`` (inclusive).
        end_date: ``"YYYY-MM-DD"`` (inclusive).
        level: ``"mlb"`` or ``"milb"``.
        **filters: Additional raw Savant search params.

    Returns:
        ``list[dict]`` — one summary per (pitcher, pitch_type) group.
    """
    rows = search_pitches(
        start_date,
        end_date,
        player_type="pitcher",
        player_id=pitcher_id,
        level=level,
        **filters,
    )
    return aggregate_pitcher_arsenal(rows)
