"""FanGraphs leaderboards — the ``/api/leaders/.../data`` JSON API.

This is the modern replacement for the retired ``leaders-legacy.aspx`` page.
One endpoint serves batting, pitching, and fielding boards; the full pitching
board is ~540 columns per row and includes the Stuff+ family (``sp_stuff``,
``sp_location``, ``sp_pitching``, per-pitch ``sp_s_FF`` etc.) and the
PitchingBot family (``pb_stuff``, ``pb_command``, ``pb_overall``, per-pitch
grades, ``pb_xRV100``). None of it is membership-gated.

Param traps, straight from the source's own convention:

- ``season`` is the **end** year and ``season1`` the **start** — inverted from
  what the names suggest. The wrappers here take ``start_season``/``end_season``
  and emit the right pair.
- ``month`` is a split code, not just a calendar month: ``0`` = full season,
  ``13`` = vs LHP, ``14`` = vs RHP. Handedness splits return a much narrower
  column set (~90 columns, not ~540) — handle missing keys accordingly.
- ``ind=1`` returns one row per player per season; ``ind=0`` aggregates the
  span into one row per player. Aggregating very long spans (>10 years) has
  historically failed server-side — prefer ``ind=1`` and aggregate yourself.
- ``qual="y"`` = qualified players only; an integer = a PA/IP minimum;
  ``0`` = everyone.
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import FangraphsError, ValidationError
from fungo.fangraphs.api import fg_json

#####################################################################
# Constants
#####################################################################

STAT_GROUPS = ["bat", "pit", "fld"]

# Split codes for the `month` param beyond calendar months.
SPLIT_MONTHS = {
    "full": 0,
    "vs_lhp": 13,
    "vs_rhp": 14,
}


#####################################################################
# Fetchers
#####################################################################


def fetch_leaders(
    stats: str = "bat",
    start_season: int | None = None,
    end_season: int | None = None,
    *,
    league: str = "major",
    pos: str = "all",
    lg: str = "all",
    qual: str | int = "y",
    ind: int = 0,
    month: int = 0,
    team: str | int = 0,
    hand: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
    players: str = "",
    postseason: str = "",
    stat_type: int | str = 8,
    sort_stat: str = "WAR",
    sort_dir: str = "default",
    page_items: int = 500000,
    page_num: int = 1,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch a FanGraphs leaderboard and return the raw JSON payload.

    Args:
        stats: Stat group — ``"bat"``, ``"pit"``, or ``"fld"``.
        start_season: First season of the range (defaults to ``end_season``).
        end_season: Last season of the range (defaults to ``start_season``).
        league: ``"major"`` or ``"minor"`` — selects the API endpoint.
        pos: Position filter (``"all"``, ``"c"``, ``"1b"``, ``"of"``, ...).
        lg: League filter (``"all"``, ``"al"``, ``"nl"``).
        qual: ``"y"`` for qualified only, an integer PA/IP minimum, or ``0``
            for everyone.
        ind: ``1`` = one row per player per season; ``0`` = aggregate the span.
        month: Split code — ``0`` full season, ``13`` vs LHP, ``14`` vs RHP,
            or a calendar-month code.
        team: Team id (``0`` = all); append ``",ts"`` for team totals.
        hand: Batter/pitcher handedness filter (``"R"``, ``"L"``, or ``""``).
        start_date: Optional ``YYYY-MM-DD`` range start (used with date splits).
        end_date: Optional ``YYYY-MM-DD`` range end.
        players: Comma-joined FanGraphs player ids to filter to, or ``""``.
        postseason: Postseason code, or ``""`` for regular season.
        stat_type: Column-set id (``8`` = the Dashboard set).
        sort_stat: Column to sort by.
        sort_dir: ``"asc"``, ``"desc"``, or ``"default"``.
        page_items: Rows per page (default large enough for everything).
        page_num: 1-based page number.
        extra_params: Passthrough params merged over everything built here.

    Returns:
        The raw JSON payload: ``{"data": [...], "totalCount": ..., ...}``.

    Raises:
        ValidationError: On an unknown ``stats`` group or ``league``.
        FangraphsError: If the response is not the expected JSON object, or on
            a Cloudflare 403.
    """
    if stats not in STAT_GROUPS:
        raise ValidationError(stats, "stats group", STAT_GROUPS)
    if league not in ("major", "minor"):
        raise ValidationError(league, "league", ["major", "minor"])

    if start_season is None and end_season is None:
        raise ValidationError(None, "season (start_season and/or end_season)")
    start = start_season if start_season is not None else end_season
    end = end_season if end_season is not None else start_season

    params: dict[str, Any] = {
        "age": "",
        "pos": pos,
        "stats": stats,
        "lg": lg,
        "qual": qual,
        # FanGraphs' naming is inverted: season = END year, season1 = START.
        "season": end,
        "season1": start,
        "startdate": start_date or "",
        "enddate": end_date or "",
        "month": month,
        "hand": hand,
        "team": team,
        "pageitems": page_items,
        "pagenum": page_num,
        "ind": ind,
        "rost": 0,
        "players": players,
        "type": stat_type,
        "postseason": postseason,
        "sortdir": sort_dir,
        "sortstat": sort_stat,
    }
    if extra_params:
        params.update(extra_params)

    payload = fg_json(f"/api/leaders/{league}-league/data", params)
    if not isinstance(payload, dict) or "data" not in payload:
        raise FangraphsError(
            f"Unexpected leaders payload shape: {type(payload).__name__}"
        )
    return payload


def get_leaders(
    stats: str = "bat",
    start_season: int | None = None,
    end_season: int | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Fetch a leaderboard and return just its rows.

    Thin convenience over :func:`fetch_leaders` — drops the pagination wrapper
    and returns ``payload["data"]``. Values are native JSON numbers; rows carry
    both ``playerid`` (FanGraphs) and ``xMLBAMID`` (MLBAM) ids.

    Args:
        stats: Stat group — ``"bat"``, ``"pit"``, or ``"fld"``.
        start_season: First season of the range.
        end_season: Last season of the range.
        **kwargs: Forwarded to :func:`fetch_leaders`.

    Returns:
        One ``dict`` per player (or per player-season when ``ind=1``).
    """
    payload = fetch_leaders(stats, start_season, end_season, **kwargs)
    data = payload["data"]
    if not isinstance(data, list):
        raise FangraphsError(f"Expected a list under 'data', got {type(data).__name__}")
    return data


def get_splits(
    stats: str,
    season: int,
    split: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Fetch a handedness/full-season split board by name.

    Args:
        stats: Stat group — ``"bat"``, ``"pit"``, or ``"fld"``.
        season: Season year.
        split: ``"full"``, ``"vs_lhp"``, or ``"vs_rhp"``.
        **kwargs: Forwarded to :func:`fetch_leaders`.

    Returns:
        Leaderboard rows for the split. Handedness splits return a narrower
        column set than the full board.

    Raises:
        ValidationError: On an unknown split name.
    """
    if split not in SPLIT_MONTHS:
        raise ValidationError(split, "split", list(SPLIT_MONTHS))
    return get_leaders(stats, season, season, month=SPLIT_MONTHS[split], **kwargs)
