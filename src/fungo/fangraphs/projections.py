"""FanGraphs projections — ZiPS, Steamer, ATC, THE BAT, OOPSY, Depth Charts.

One GET returns every projected player as a bare JSON list with typed values,
including the ``playerid`` (FanGraphs) / ``xMLBAMID`` (MLBAM) crosswalk and
fantasy columns (ADP, FPTS). Steamer rows additionally carry uncertainty
quantiles (``q10``-``q90``) and standard errors.

Rest-of-season slugs follow ``r<system>`` with two quirks: Steamer is
``steamerr`` (suffix), and ATC/OOPSY carry a ``dc`` suffix (``ratcdc``,
``roopsydc``). All eight RoS slugs are live-verified (2026-07, mid-season).
Steamer RoS covers minor-leaguers (~4,600 rows); the other systems project
only roster players (~620 rows).
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import FangraphsError, ValidationError
from fungo.fangraphs.api import fg_json

#####################################################################
# Constants
#####################################################################

# Pre-season / full-season systems (steamer + zips verified live 2026-07).
PROJECTION_SYSTEMS = [
    "steamer",
    "zips",
    "zipsdc",
    "fangraphsdc",  # Depth Charts
    "atc",
    "thebat",
    "thebatx",
    "oopsy",
]

# Rest-of-season variants (all eight verified live 2026-07).
ROS_PROJECTION_SYSTEMS = [
    "steamerr",
    "rzips",
    "rzipsdc",
    "rfangraphsdc",
    "ratcdc",
    "roopsydc",
    "rthebat",
    "rthebatx",
]


#####################################################################
# Fetcher
#####################################################################


def get_projections(
    system: str = "steamer",
    stats: str = "bat",
    *,
    pos: str = "all",
    team: int | str = 0,
    lg: str = "all",
    players: int | str = 0,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch player projections for a system.

    Args:
        system: Projection system slug — see :data:`PROJECTION_SYSTEMS` and
            :data:`ROS_PROJECTION_SYSTEMS`.
        stats: ``"bat"`` or ``"pit"``.
        pos: Position filter (``"all"``, ``"c"``, ...).
        team: Team id filter (``0`` = all).
        lg: League filter (``"all"``, ``"al"``, ``"nl"``).
        players: Player filter (``0`` = all).
        extra_params: Passthrough params merged over everything built here.

    Returns:
        One dict per projected player (typed values; ``xMLBAMID`` may be null
        for recent call-ups).

    Raises:
        ValidationError: On an unknown system or stats group.
        FangraphsError: On a Cloudflare 403 or unexpected payload shape.
    """
    valid = PROJECTION_SYSTEMS + ROS_PROJECTION_SYSTEMS
    if system not in valid:
        raise ValidationError(system, "projection system", valid)
    if stats not in ("bat", "pit"):
        raise ValidationError(stats, "stats group", ["bat", "pit"])

    params: dict[str, Any] = {
        "type": system,
        "stats": stats,
        "pos": pos,
        "team": team,
        "players": players,
        "lg": lg,
    }
    if extra_params:
        params.update(extra_params)

    payload = fg_json("/api/projections", params)
    if not isinstance(payload, list):
        raise FangraphsError(
            f"Unexpected projections payload: {type(payload).__name__}"
        )
    return payload
