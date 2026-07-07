"""FanGraphs player endpoints — career stats and game logs.

Both endpoints return raw JSON exactly as FanGraphs produced it.

The stats payload's ``data`` rows mix several record kinds, discriminated by
the ``type`` field:

    0          MLB regular season
    900        playoff / split rows
    1000       league-average comparison rows
    negative   projection systems (ZiPS, Steamer, ATC, THE BAT, ...)

and by ``AbbLevel`` (``"MLB"``, ``"AAA"``, ..., ``"PROJ"``). One stat group per
row — batting rows never mix in pitching columns.
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import FangraphsError
from fungo.fangraphs.api import fg_json

#####################################################################
# Fetchers
#####################################################################


def get_player_stats(
    player_id: int | str,
    position: str = "",
) -> dict[str, Any]:
    """Fetch a player's full stats payload (career tables + metadata).

    Args:
        player_id: FanGraphs player id (e.g. ``15640`` for Aaron Judge) —
            resolvable from MLBAM via :func:`fungo.lookup.mlbam_to_fangraphs`.
        position: Position hint (``"OF"``, ``"P"``, ...); ``""`` usually works.

    Returns:
        Raw JSON with ``playerInfo``, ``teamInfo``, and ``data`` (season rows —
        see the module docstring for the ``type`` discriminator).

    Raises:
        FangraphsError: On a Cloudflare 403 or unexpected payload shape.
    """
    payload = fg_json(
        "/api/players/stats",
        {"playerid": player_id, "position": position},
    )
    if not isinstance(payload, dict):
        raise FangraphsError(
            f"Unexpected player stats payload: {type(payload).__name__}"
        )
    return payload


def get_game_log(
    player_id: int | str,
    season: int | None = None,
    *,
    position: str = "",
    log_type: int = 0,
) -> dict[str, Any]:
    """Fetch a player's game log.

    Args:
        player_id: FanGraphs player id (MiLB ids look like ``"sa917940"``).
        season: Season year. Omit for the MiLB variant (``log_type=-1``).
        position: ``"P"`` for pitchers, ``""`` for batters.
        log_type: ``0`` = MLB game log; ``-1`` = minor-league game log.

    Returns:
        Raw JSON. MLB logs live under the ``"mlb"`` key; the first row is a
        season-summary row, and ``Date`` fields arrive as HTML anchors.

    Raises:
        FangraphsError: On a Cloudflare 403 or unexpected payload shape.
    """
    params: dict[str, Any] = {
        "playerid": player_id,
        "position": position,
        "type": log_type,
    }
    if season is not None:
        params["season"] = season

    payload = fg_json("/api/players/game-log", params)
    if not isinstance(payload, dict):
        raise FangraphsError(f"Unexpected game log payload: {type(payload).__name__}")
    return payload
