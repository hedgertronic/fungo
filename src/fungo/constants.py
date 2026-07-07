"""Baseball Savant / Statcast constants and name-aware resolvers.

Module-level mappings for pitch types, plate-appearance and pitch results,
batted-ball types, quality-of-contact buckets, base states, game types, and
fielding positions, ported from the Statcast skill reference tables. Teams are
enriched with full name / city / alias metadata, and three resolvers turn loose
client input into canonical codes, raising :class:`ValidationError` (with a
"did you mean?" suggestion) on a miss.
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import ValidationError

#####################################################################
# Pitch / outcome enums
#####################################################################

PITCH_TYPES: dict[str, str] = {
    "FF": "4-Seam Fastball",
    "SI": "Sinker",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
    "CU": "Curveball",
    "KC": "Knuckle Curve",
    "CH": "Changeup",
    "FS": "Split-Finger",
    "FO": "Forkball",
    "KN": "Knuckleball",
    "EP": "Eephus",
}

PA_RESULTS: dict[str, str] = {
    "single": "Single",
    "double": "Double",
    "triple": "Triple",
    "home_run": "Home Run",
    "walk": "Walk",
    "hit_by_pitch": "Hit by Pitch",
    "strikeout": "Strikeout",
    "strikeout_double_play": "Strikeout + DP",
    "field_out": "Field Out",
    "double_play": "Double Play",
    "triple_play": "Triple Play",
    "force_out": "Force Out",
    "grounded_into_double_play": "GIDP",
    "fielders_choice": "Fielder's Choice",
    "fielders_choice_out": "FC Out",
    "sac_fly": "Sacrifice Fly",
    "sac_bunt": "Sacrifice Bunt",
    "sac_fly_double_play": "Sac Fly DP",
}

# Pitch-level results (the `description` column)
PITCH_RESULTS: dict[str, str] = {
    "S": "Swinging Strike",
    "C": "Called Strike",
    "B": "Ball",
    "X": "Ball in Play",
    "F": "Foul",
    "T": "Foul Tip",
    "L": "Foul Bunt",
    "I": "Intent Ball",
    "O": "Foul Tip (bunted)",
    "W": "Swinging Strike (blocked)",
    "M": "Missed Bunt",
    "P": "Pitchout",
    "Q": "Swinging Pitchout",
    "R": "Foul Pitchout",
}

BATTED_BALL_TYPES: dict[str, str] = {
    "ground_ball": "Ground Ball",
    "line_drive": "Line Drive",
    "fly_ball": "Fly Ball",
    "popup": "Popup",
}

# Savant 6-tier batted ball quality of contact buckets
QOC_CODES: dict[int, str] = {
    1: "Weak",
    2: "Topped",
    3: "Under",
    4: "Flare/Burner",
    5: "Solid Contact",
    6: "Barrel",
}

# 0 = bases empty, 1 = runner on 1st, 2 = 2nd, 3 = 3rd,
# 4 = 1st+2nd, 5 = 1st+3rd, 6 = 2nd+3rd, 7 = bases loaded
RUNNERS_ON: dict[int, str] = {
    0: "Empty",
    1: "1st",
    2: "2nd",
    3: "3rd",
    4: "1st & 2nd",
    5: "1st & 3rd",
    6: "2nd & 3rd",
    7: "Loaded",
}

GAME_TYPES: dict[str, str] = {
    "R": "Regular Season",
    "F": "Wild Card",
    "D": "Division Series",
    "L": "League Championship Series",
    "W": "World Series",
    "S": "Spring Training",
}

POSITIONS: dict[str, str] = {
    "1": "P",
    "2": "C",
    "3": "1B",
    "4": "2B",
    "5": "3B",
    "6": "SS",
    "7": "LF",
    "8": "CF",
    "9": "RF",
}


#####################################################################
# Teams
#####################################################################

# code -> {"name", "city", "aliases"}. Codes match Savant's hfTeam / home_team /
# away_team values.
TEAMS: dict[str, dict[str, Any]] = {
    "ARI": {
        "name": "Arizona Diamondbacks",
        "city": "Arizona",
        "aliases": ["Diamondbacks", "D-backs", "DBacks", "AZ"],
    },
    "ATL": {"name": "Atlanta Braves", "city": "Atlanta", "aliases": ["Braves"]},
    "BAL": {
        "name": "Baltimore Orioles",
        "city": "Baltimore",
        "aliases": ["Orioles", "O's"],
    },
    "BOS": {"name": "Boston Red Sox", "city": "Boston", "aliases": ["Red Sox", "Sox"]},
    "CHC": {"name": "Chicago Cubs", "city": "Chicago", "aliases": ["Cubs", "Cubbies"]},
    "CWS": {
        "name": "Chicago White Sox",
        "city": "Chicago",
        "aliases": ["White Sox", "ChiSox", "CHW"],
    },
    "CIN": {"name": "Cincinnati Reds", "city": "Cincinnati", "aliases": ["Reds"]},
    "CLE": {
        "name": "Cleveland Guardians",
        "city": "Cleveland",
        "aliases": ["Guardians", "Indians"],
    },
    "COL": {"name": "Colorado Rockies", "city": "Colorado", "aliases": ["Rockies"]},
    "DET": {"name": "Detroit Tigers", "city": "Detroit", "aliases": ["Tigers"]},
    "HOU": {"name": "Houston Astros", "city": "Houston", "aliases": ["Astros"]},
    "KC": {
        "name": "Kansas City Royals",
        "city": "Kansas City",
        "aliases": ["Royals", "KCR"],
    },
    "LAA": {
        "name": "Los Angeles Angels",
        "city": "Los Angeles",
        "aliases": ["Angels", "LA Angels", "Anaheim"],
    },
    "LAD": {
        "name": "Los Angeles Dodgers",
        "city": "Los Angeles",
        "aliases": ["Dodgers", "LA Dodgers"],
    },
    "MIA": {"name": "Miami Marlins", "city": "Miami", "aliases": ["Marlins", "FLA"]},
    "MIL": {
        "name": "Milwaukee Brewers",
        "city": "Milwaukee",
        "aliases": ["Brewers", "Brew Crew"],
    },
    "MIN": {"name": "Minnesota Twins", "city": "Minnesota", "aliases": ["Twins"]},
    "NYM": {"name": "New York Mets", "city": "New York", "aliases": ["Mets"]},
    "NYY": {
        "name": "New York Yankees",
        "city": "New York",
        "aliases": ["Yankees", "Yanks"],
    },
    "OAK": {
        "name": "Oakland Athletics",
        "city": "Oakland",
        "aliases": ["Athletics", "A's", "As", "ATH"],
    },
    "PHI": {
        "name": "Philadelphia Phillies",
        "city": "Philadelphia",
        "aliases": ["Phillies", "Phils"],
    },
    "PIT": {
        "name": "Pittsburgh Pirates",
        "city": "Pittsburgh",
        "aliases": ["Pirates", "Bucs"],
    },
    "SD": {
        "name": "San Diego Padres",
        "city": "San Diego",
        "aliases": ["Padres", "SDP"],
    },
    "SEA": {
        "name": "Seattle Mariners",
        "city": "Seattle",
        "aliases": ["Mariners", "M's"],
    },
    "SF": {
        "name": "San Francisco Giants",
        "city": "San Francisco",
        "aliases": ["Giants", "SFG"],
    },
    "STL": {
        "name": "St. Louis Cardinals",
        "city": "St. Louis",
        "aliases": ["Cardinals", "Cards"],
    },
    "TB": {"name": "Tampa Bay Rays", "city": "Tampa Bay", "aliases": ["Rays", "TBR"]},
    "TEX": {"name": "Texas Rangers", "city": "Texas", "aliases": ["Rangers"]},
    "TOR": {
        "name": "Toronto Blue Jays",
        "city": "Toronto",
        "aliases": ["Blue Jays", "Jays"],
    },
    "WSH": {
        "name": "Washington Nationals",
        "city": "Washington",
        "aliases": ["Nationals", "Nats", "WSN", "WAS"],
    },
}

# The 30 codes used by Baseball Savant search-params docs.
TEAM_CODES: list[str] = list(TEAMS)


#####################################################################
# Pitch / hand aliases
#####################################################################

# Loose name -> canonical pitch code (lowercased keys). Codes resolve to
# themselves; full names and common nicknames map here too.
_PITCH_ALIASES: dict[str, str] = {
    "4-seam": "FF",
    "4 seam": "FF",
    "four-seam": "FF",
    "fourseam": "FF",
    "fastball": "FF",
    "heater": "FF",
    "two-seam": "SI",
    "2-seam": "SI",
    "sinker": "SI",
    "cutter": "FC",
    "cut fastball": "FC",
    "slider": "SL",
    "sweeper": "ST",
    "sweeping slider": "ST",
    "slurve": "SV",
    "curve": "CU",
    "curveball": "CU",
    "knuckle curve": "KC",
    "knuckle-curve": "KC",
    "change": "CH",
    "changeup": "CH",
    "splitter": "FS",
    "split-finger": "FS",
    "split finger": "FS",
    "forkball": "FO",
    "knuckleball": "KN",
    "knuckle": "KN",
    "eephus": "EP",
}

# Loose hand -> canonical "R" / "L" / "S".
_HAND_ALIASES: dict[str, str] = {
    "r": "R",
    "right": "R",
    "rhp": "R",
    "rhh": "R",
    "righty": "R",
    "righthanded": "R",
    "right-handed": "R",
    "l": "L",
    "left": "L",
    "lhp": "L",
    "lhh": "L",
    "lefty": "L",
    "lefthanded": "L",
    "left-handed": "L",
    "s": "S",
    "switch": "S",
    "both": "S",
    "switch-hitter": "S",
}


#####################################################################
# Resolvers
#####################################################################


def resolve_team(value: str) -> str:
    """Resolve a team code, full name, city, or alias to its canonical code.

    Matching is case-insensitive across the code, ``name``, ``city``, and each
    entry in ``aliases``.

    Args:
        value: A team code (``"LAD"``), full name (``"Los Angeles Dodgers"``),
            city (``"Los Angeles"`` — note multiple teams share cities), or
            alias (``"Dodgers"``).

    Returns:
        The canonical 2-3 letter team code.

    Raises:
        ValidationError: If ``value`` matches no team; includes a suggestion.
    """
    needle = value.strip().lower()

    for code, meta in TEAMS.items():
        if needle == code.lower():
            return code
        if needle == meta["name"].lower():
            return code
        if needle == meta["city"].lower():
            return code
        if any(needle == alias.lower() for alias in meta["aliases"]):
            return code

    candidates = list(TEAMS)
    candidates += [m["name"] for m in TEAMS.values()]
    candidates += [alias for m in TEAMS.values() for alias in m["aliases"]]
    raise ValidationError(value, "team", candidates)


def resolve_pitch_type(value: str) -> str:
    """Resolve a pitch code, full name, or nickname to its Statcast code.

    Args:
        value: A pitch code (``"FF"``), full name (``"4-Seam Fastball"``), or
            nickname (``"4-seam"``, ``"sweeper"``).

    Returns:
        The canonical Statcast pitch-type code.

    Raises:
        ValidationError: If ``value`` matches no pitch type; includes a
            suggestion.
    """
    needle = value.strip()
    upper = needle.upper()
    if upper in PITCH_TYPES:
        return upper

    lower = needle.lower()
    if lower in _PITCH_ALIASES:
        return _PITCH_ALIASES[lower]

    for code, name in PITCH_TYPES.items():
        if lower == name.lower():
            return code

    candidates = list(PITCH_TYPES) + list(PITCH_TYPES.values()) + list(_PITCH_ALIASES)
    raise ValidationError(value, "pitch type", candidates)


def resolve_hand(value: str) -> str:
    """Resolve a handedness value to canonical ``"R"`` / ``"L"`` / ``"S"``.

    Args:
        value: ``"R"``/``"L"``/``"S"`` or a word like ``"right"``, ``"left"``,
            ``"switch"``, ``"both"``.

    Returns:
        One of ``"R"``, ``"L"``, ``"S"``.

    Raises:
        ValidationError: If ``value`` matches no handedness; includes a
            suggestion.
    """
    needle = value.strip().lower()
    if needle in _HAND_ALIASES:
        return _HAND_ALIASES[needle]

    raise ValidationError(value, "handedness", list(_HAND_ALIASES))
