"""Baseball-Reference minor-league register.

Register player ids are 12 characters — ``{last:6}{seq:3}{first:3}``, hyphen-
padded (``baez--001ben``) — and are exactly the Chadwick register's
``key_bbref_minors`` values, which fungo's lookup already carries:
``fungo.lookup.lookup(mlbam=...)`` -> ``key_bbref_minors``. **Never synthesize
these ids from names** — the sequence number's base is inconsistent (000 for
some players, 001 for others) and the first-name segment can come from the
legal rather than the used name; always resolve through the register.
"""

from __future__ import annotations

from typing import Any

from fungo.bbref.session import bbref_html
from fungo.bbref.tables import extract_all_tables

#####################################################################
# Fetchers
#####################################################################


def get_register_player(register_id: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch a player's minor-league register page.

    Args:
        register_id: 12-character register id (Chadwick ``key_bbref_minors``),
            e.g. ``"baez--001ben"``.

    Returns:
        Mapping of table id -> rows: ``standard_batting``,
        ``standard_pitching``, ``standard_fielding``, ``standard_roster``
        (season-by-season with ``level`` and ``affiliation`` columns). All
        values are strings.
    """
    return extract_all_tables(bbref_html("/register/player.fcgi", {"id": register_id}))
