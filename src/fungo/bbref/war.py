"""Baseball-Reference WAR daily files — the one B-R endpoint that is data-first.

``/data/war_daily_bat.txt`` and ``/data/war_daily_pitch.txt`` are plain CSV
flat files carrying bWAR and its full component breakdown for every player
season in B-R history. No HTML, no comments, no parsing tricks — but they are
multi-megabyte downloads covering all of history, so fetch once and keep the
result; they still route through the shared rate limiter.

Values follow fungo's CSV convention: every value is a string.
"""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_bytes
from fungo.exceptions import ValidationError
from fungo.http import parse_csv

#####################################################################
# Fetchers
#####################################################################

WAR_KINDS = ["bat", "pitch"]


def get_war_daily(kind: str) -> list[dict[str, Any]]:
    """Fetch B-R's daily-updated WAR file for batters or pitchers.

    Args:
        kind: ``"bat"`` or ``"pitch"``.

    Returns:
        One row per player-season (all of B-R history) with bWAR and its
        components (``WAR``, ``runs_bat``, ``runs_defense``, ``runs_position``,
        ``WAA``, salary, ...). All values are strings.

    Raises:
        ValidationError: On an unknown ``kind``.
    """
    if kind not in WAR_KINDS:
        raise ValidationError(kind, "WAR file kind", WAR_KINDS)
    return parse_csv(bbref_bytes(f"/data/war_daily_{kind}.txt"))


def get_war_daily_batting() -> list[dict[str, Any]]:
    """Fetch the batters' WAR daily file. See :func:`get_war_daily`."""
    return get_war_daily("bat")


def get_war_daily_pitching() -> list[dict[str, Any]]:
    """Fetch the pitchers' WAR daily file. See :func:`get_war_daily`."""
    return get_war_daily("pitch")
