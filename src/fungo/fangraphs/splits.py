"""FanGraphs splits leaderboards -- the POST-only splits API.

Distinct from the handedness splits on the main leaderboard
(:func:`fungo.fangraphs.leaders.get_splits`, which uses ``month=13/14`` and a
narrow column set): this endpoint powers the site's Splits Leaderboards page
and composes arbitrary split filters (vs hand, home, RISP, day/night, ...)
with date ranges and stat groups.

The full split-code table lives in this module. ``SPLIT_CODE_TABLE``
maps 292 integer codes to human-readable labels (recovered from the
splits-leaderboards page inline JS, 2026-07-06). ``PITCH_SPLIT_CODE_TABLE``
maps 47 pitch-split codes (pitch type, count, zone). Named shortcuts for the
most common codes are in ``SPLIT_CODES`` and ``PITCH_SPLIT_CODES``; raw
integers are still accepted and multiple codes in one request combine.

Home/away are position-dependent: FanGraphs uses code 7/8 for batter home/away
and 9/10 for pitcher home/away. Pass ``"home"`` or ``"away"`` by name and
``get_split_leaders`` resolves to the right code automatically.
"""

from __future__ import annotations

from typing import Any

from fungo.exceptions import FangraphsError, ValidationError
from fungo.fangraphs.api import fg_json_post

#####################################################################
# Named shortcuts
#####################################################################

# Position-aware shortcuts. A dict value maps position arg "B"/"P" to the
# FanGraphs code because home/away codes differ by batter/pitcher view.
SPLIT_CODES: dict[str, int | dict[str, int]] = {
    # handedness
    "vs_lhp": 1,
    "vs_rhp": 2,
    "as_lhh": 3,
    "as_rhh": 4,
    "vs_lhh": 5,
    "vs_rhh": 6,
    "as_rhp": 96,
    "as_lhp": 97,
    # location -- FanGraphs uses different codes per position
    # (batter home=7, pitcher home=9)
    "home": {"B": 7, "P": 9},
    "away": {"B": 8, "P": 10},
    # batted ball
    "grounders": 11,
    "flyballs": 12,
    "line_drives": 13,
    "soft": 16,
    "medium": 17,
    "hard": 18,
    "pull": 78,
    "center": 79,
    "oppo": 80,
    # times through order (pitchers)
    "tto_1": 28,
    "tto_2": 29,
    "tto_3": 30,
    # base-out states
    "bases_empty": 57,
    "runners_on": 58,
    "risp": 59,
    "bases_loaded": 60,
    # leverage
    "high_leverage": 72,
    "medium_leverage": 73,
    "low_leverage": 74,
    # calendar
    "march_april": 84,
    "may": 85,
    "june": 86,
    "july": 87,
    "august": 88,
    "sept_oct": 89,
    "day": 90,
    "night": 91,
    "first_half": 92,
    "second_half": 93,
}

# Named shortcuts for strSplitArrPitch.
# NOTE: FanGraphs' own page JS ships wrong SQLValues for ids 5/7/8
# (changeup/curveball/slow-curve), so those three may be broken server-side --
# verify results before trusting them.
PITCH_SPLIT_CODES: dict[str, int] = {
    # pitch types
    "fourseam": 1,
    "cutter": 2,
    "splitter": 3,
    "sinker": 4,
    "changeup": 5,
    "slider": 6,
    "curveball": 7,
    "slow_curve": 8,
    "knuckleball": 9,
    "screwball": 10,
    # exact counts
    "count_0_0": 100,
    "count_0_1": 101,
    "count_0_2": 102,
    "count_1_0": 103,
    "count_1_1": 104,
    "count_1_2": 105,
    "count_2_0": 106,
    "count_2_1": 107,
    "count_2_2": 108,
    "count_3_0": 109,
    "count_3_1": 110,
    "count_3_2": 111,
}

SPLIT_STAT_GROUPS = {
    "standard": "1",
    "advanced": "2",
    "batted_ball": "3",
}

#####################################################################
# Full code tables (generated from splits-leaderboards inline JS)
#####################################################################

# Source: splits-leaderboards page inline JS, fetched 2026-07-06.
# Group ranges:
#   handedness 1-6/96-97, home-away 7-10, batted ball 11-18/75-80/98,
#   batting order 19-27, TTO 28-31, position 32-43/94-95,
#   inning 44-53, base-outs 54-60, through-count 61-71,
#   leverage 72-74, shift 81-83, calendar 84-93,
#   opponent 99-162, player team 163-226, park 227-268,
#   weather 269-279, roof 280-285, wind 286-292.
SPLIT_CODE_TABLE: dict[int, str] = {
    1: "vs LHP",
    2: "vs RHP",
    3: "as LHH",
    4: "as RHH",
    5: "vs LHH",
    6: "vs RHH",
    7: "Home (batters)",
    8: "Away (batters)",
    9: "Home (pitchers)",
    10: "Away (pitchers)",
    11: "Groundballs",
    12: "Flyballs",
    13: "Line Drives",
    14: "Balls Not in Play",
    15: "Balls in Play",
    16: "Soft",
    17: "Medium",
    18: "Hard",
    19: "Batting 1st",
    20: "Batting 2nd",
    21: "Batting 3rd",
    22: "Batting 4th",
    23: "Batting 5th",
    24: "Batting 6th",
    25: "Batting 7th",
    26: "Batting 8th",
    27: "Batting 9th",
    28: "1st Time Through Order",
    29: "2nd Time Through Order",
    30: "3rd Time Through Order",
    31: "4th Time Through Order",
    32: "as P",
    33: "as C",
    34: "as 1B",
    35: "as 2B",
    36: "as 3B",
    37: "as SS",
    38: "as LF",
    39: "as CF",
    40: "as RF",
    41: "as DH",
    42: "as SP",
    43: "as RP",
    44: "1st Inning",
    45: "2nd Inning",
    46: "3rd Inning",
    47: "4th Inning",
    48: "5th Inning",
    49: "6th Inning",
    50: "7th Inning",
    51: "8th Inning",
    52: "9th Inning",
    53: "Extra Innings",
    54: "No Outs",
    55: "1 Out",
    56: "2 Outs",
    57: "Bases Empty",
    58: "Runners On",
    59: "Runners in Scoring",
    60: "Bases Loaded",
    61: "Through 0-1",
    62: "Through 0-2",
    63: "Through 1-0",
    64: "Through 1-1",
    65: "Through 1-2",
    66: "Through 2-1",
    67: "Through 2-0",
    68: "Through 3-0",
    69: "Through 3-1",
    70: "Through 2-2",
    71: "Through 3-2",
    72: "High Leverage",
    73: "Medium Leverage",
    74: "Low Leverage",
    75: "Right Field",
    76: "Left Field",
    77: "Center Field",
    78: "Pull",
    79: "Center",
    80: "Oppo",
    81: "No Shift",
    82: "Shift - Traditional",
    83: "Shift - Non Traditional",
    84: "March/April",
    85: "May",
    86: "June",
    87: "July",
    88: "August",
    89: "Sept/Oct",
    90: "Day",
    91: "Night",
    92: "1st half",
    93: "2nd half",
    94: "as PH",
    95: "as PR",
    96: "as RHP",
    97: "as LHP",
    98: "Bunts",
    99: "vs. BAL (pitchers)",
    100: "vs. BOS (pitchers)",
    101: "vs. CHW (pitchers)",
    102: "vs. CLE (pitchers)",
    103: "vs. DET (pitchers)",
    104: "vs. HOU (pitchers)",
    105: "vs. KC (pitchers)",
    106: "vs. LAA (pitchers)",
    107: "vs. MIN (pitchers)",
    108: "vs. NYY (pitchers)",
    109: "vs. ATH (pitchers)",
    110: "vs. SEA (pitchers)",
    111: "vs. TB (pitchers)",
    112: "vs. TEX (pitchers)",
    113: "vs. TOR (pitchers)",
    114: "vs. AL (pitchers)",
    115: "vs. ARZ (pitchers)",
    116: "vs. ATL (pitchers)",
    117: "vs. CHC (pitchers)",
    118: "vs. CIN (pitchers)",
    119: "vs. COL (pitchers)",
    120: "vs. LAD (pitchers)",
    121: "vs. MIA (pitchers)",
    122: "vs. MIL (pitchers)",
    123: "vs. NYM (pitchers)",
    124: "vs. PHI (pitchers)",
    125: "vs. PIT (pitchers)",
    126: "vs. STL (pitchers)",
    127: "vs. SD (pitchers)",
    128: "vs. SF (pitchers)",
    129: "vs. WAS (pitchers)",
    130: "vs. NL (pitchers)",
    131: "vs. BAL (batters)",
    132: "vs. BOS (batters)",
    133: "vs. CHW (batters)",
    134: "vs. CLE (batters)",
    135: "vs. DET (batters)",
    136: "vs. HOU (batters)",
    137: "vs. KC (batters)",
    138: "vs. LAA (batters)",
    139: "vs. MIN (batters)",
    140: "vs. NYY (batters)",
    141: "vs. ATH (batters)",
    142: "vs. SEA (batters)",
    143: "vs. TB (batters)",
    144: "vs. TEX (batters)",
    145: "vs. TOR (batters)",
    146: "vs. AL (batters)",
    147: "vs. ARZ (batters)",
    148: "vs. ATL (batters)",
    149: "vs. CHC (batters)",
    150: "vs. CIN (batters)",
    151: "vs. COL (batters)",
    152: "vs. LAD (batters)",
    153: "vs. MIA (batters)",
    154: "vs. MIL (batters)",
    155: "vs. NYM (batters)",
    156: "vs. PHI (batters)",
    157: "vs. PIT (batters)",
    158: "vs. STL (batters)",
    159: "vs. SD (batters)",
    160: "vs. SF (batters)",
    161: "vs. WAS (batters)",
    162: "vs. NL (batters)",
    163: "team BAL (pitchers)",
    164: "team BOS (pitchers)",
    165: "team CHW (pitchers)",
    166: "team CLE (pitchers)",
    167: "team DET (pitchers)",
    168: "team HOU (pitchers)",
    169: "team KC (pitchers)",
    170: "team LAA (pitchers)",
    171: "team MIN (pitchers)",
    172: "team NYY (pitchers)",
    173: "team ATH (pitchers)",
    174: "team SEA (pitchers)",
    175: "team TB (pitchers)",
    176: "team TEX (pitchers)",
    177: "team TOR (pitchers)",
    178: "team AL (pitchers)",
    179: "team ARZ (pitchers)",
    180: "team ATL (pitchers)",
    181: "team CHC (pitchers)",
    182: "team CIN (pitchers)",
    183: "team COL (pitchers)",
    184: "team LAD (pitchers)",
    185: "team MIA (pitchers)",
    186: "team MIL (pitchers)",
    187: "team NYM (pitchers)",
    188: "team PHI (pitchers)",
    189: "team PIT (pitchers)",
    190: "team STL (pitchers)",
    191: "team SD (pitchers)",
    192: "team SF (pitchers)",
    193: "team WAS (pitchers)",
    194: "team NL (pitchers)",
    195: "team BAL (batters)",
    196: "team BOS (batters)",
    197: "team CHW (batters)",
    198: "team CLE (batters)",
    199: "team DET (batters)",
    200: "team HOU (batters)",
    201: "team KC (batters)",
    202: "team LAA (batters)",
    203: "team MIN (batters)",
    204: "team NYY (batters)",
    205: "team ATH (batters)",
    206: "team SEA (batters)",
    207: "team TB (batters)",
    208: "team TEX (batters)",
    209: "team TOR (batters)",
    210: "team AL (batters)",
    211: "team ARZ (batters)",
    212: "team ATL (batters)",
    213: "team CHC (batters)",
    214: "team CIN (batters)",
    215: "team COL (batters)",
    216: "team LAD (batters)",
    217: "team MIA (batters)",
    218: "team MIL (batters)",
    219: "team NYM (batters)",
    220: "team PHI (batters)",
    221: "team PIT (batters)",
    222: "team STL (batters)",
    223: "team SD (batters)",
    224: "team SF (batters)",
    225: "team WAS (batters)",
    226: "team NL (batters)",
    227: "Angel Stadium of Anaheim",
    228: "Oracle Park",
    229: "Busch Stadium II",
    230: "Busch Stadium III",
    231: "Camden Yards",
    232: "Chase Field",
    233: "Cingery Field",
    234: "Citi Field",
    235: "Citizen's Bank Park",
    236: "Comerica Park",
    237: "Coors Field",
    238: "Dodger Stadium",
    239: "Fenway Park",
    240: "Global Life Field",
    241: "Great American Ballpark",
    242: "Guaranteed Rate Field",
    243: "Kauffmann Stadium",
    244: "T-Mobile Park",
    245: "LoanDepot Park",
    246: "Metrodome",
    247: "Miller Park",
    248: "Minute Maid Park",
    249: "Nationals Park",
    250: "RingCentral Coliseum",
    251: "Olympic Stadium",
    252: "Petco Park",
    253: "Progressive Field",
    254: "PNC Park",
    255: "Qualcomm Stadium",
    256: "Ballpark in Arlington",
    257: "RFK Stadium",
    258: "Rogers Centre",
    259: "Shea Stadium",
    260: "Sun Life Stadium",
    261: "Truist Park",
    262: "Target Field",
    263: "Tropicana Field",
    264: "Turner Field",
    265: "Veterans Stadium",
    266: "Wrigley Field",
    267: "Yankees Stadium I",
    268: "Yankees Stadium II",
    269: "Clear",
    270: "Clouds",
    271: "Drizzle",
    272: "Dust",
    273: "Fog",
    274: "Haze",
    275: "Mist",
    276: "Rain",
    277: "Smoke",
    278: "Snow",
    279: "Thunderstorm",
    280: "Outdoor Stadium",
    281: "Fixed Dome",
    282: "Retractable Roof",
    283: "Roof Open/Outdoor",
    284: "Roof Closed",
    285: "Fixed Dome",
    286: "Blowing Out (LF, CF, RF)",
    287: "Blowing LF",
    288: "Blowing CF",
    289: "Blowing RF",
    290: "Blowing 3B to 1B",
    291: "Blowing 1B to 3B",
    292: "Blowing In",
}

# Source: strSplitArrPitch inline JS, fetched 2026-07-06.
# Pitch types 1-10, counts 100-111, location zones 200-224.
PITCH_SPLIT_CODE_TABLE: dict[int, str] = {
    1: "FA - Fourseam",
    2: "FC - Cutter",
    3: "FS - Splitter",
    4: "SI - Sinker",
    5: "CH - Changeup",
    6: "SL - Slider",
    7: "CU - Curveball",
    8: "CS - Slow Curve",
    9: "KN - Knuckleball",
    10: "SB - Screwball",
    100: "0-0",
    101: "0-1",
    102: "0-2",
    103: "1-0",
    104: "1-1",
    105: "1-2",
    106: "2-0",
    107: "2-1",
    108: "2-2",
    109: "3-0",
    110: "3-1",
    111: "3-2",
    200: "zone (0,0)",
    201: "zone (0,1)",
    202: "zone (0,2)",
    203: "zone (0,3)",
    204: "zone (0,4)",
    205: "zone (1,0)",
    206: "zone (1,1)",
    207: "zone (1,2)",
    208: "zone (1,3)",
    209: "zone (1,4)",
    210: "zone (2,0)",
    211: "zone (2,1)",
    212: "zone (2,2)",
    213: "zone (2,3)",
    214: "zone (2,4)",
    215: "zone (3,0)",
    216: "zone (3,1)",
    217: "zone (3,2)",
    218: "zone (3,3)",
    219: "zone (3,4)",
    220: "zone (4,0)",
    221: "zone (4,1)",
    222: "zone (4,2)",
    223: "zone (4,3)",
    224: "zone (4,4)",
}

#####################################################################
# Fetcher
#####################################################################


def get_split_leaders(
    position: str,
    season: int | None = None,
    splits: int | str | list[int | str] | None = None,
    *,
    stat_group: str = "advanced",
    stat_type: str = "player",
    start_date: str | None = None,
    end_date: str | None = None,
    player_id: int | str = "all",
    filters: list[dict[str, Any]] | None = None,
    pitch_splits: int | str | list[int | str] | None = None,
    extra_body: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch a splits leaderboard.

    Args:
        position: ``"B"`` for batters, ``"P"`` for pitchers.
        season: Season year -- expands to a March-November date range. Pass
            explicit ``start_date``/``end_date`` instead for custom windows.
        splits: Split selections -- names from :data:`SPLIT_CODES` and/or raw
            integer codes; a single code/name or a list. Multiple splits
            combine. ``None`` = no split filter (overall). Home/away resolve
            to the right code for the given ``position`` (batter home=7,
            pitcher home=9).
        stat_group: ``"standard"``, ``"advanced"``, or ``"batted_ball"``.
        stat_type: ``"player"`` or ``"team"``.
        start_date: ``YYYY-MM-DD`` range start (overrides ``season``).
        end_date: ``YYYY-MM-DD`` range end (overrides ``season``).
        player_id: A single FanGraphs player id to filter to, or ``"all"``.
        filters: Qualifier filters in the API's object form, e.g.
            ``[{"stat": "PA", "comp": "gt", "low": "100", "high": -99,
            "auto": False, "pending": True, "label": "PA >= 100",
            "value": 0}]``.
        pitch_splits: Pitch-split selections -- names from
            :data:`PITCH_SPLIT_CODES` and/or raw integer codes; a single
            code/name or a list. Feeds ``strSplitArrPitch``. ``None`` = no
            pitch-split filter.
        extra_body: Passthrough fields merged over the built request body.

    Returns:
        Leaderboard rows (typed numeric values). Multi-team players collapse
        to a ``"2 Tms"``-style ``TeamNameAbb``.

    Raises:
        ValidationError: On a bad position/stat group/split name/pitch-split
            name, or when neither a season nor a date range is given.
        FangraphsError: On a Cloudflare 403 or unexpected payload shape.
    """
    if position not in ("B", "P"):
        raise ValidationError(position, "position", ["B", "P"])
    if stat_group not in SPLIT_STAT_GROUPS:
        raise ValidationError(stat_group, "stat group", list(SPLIT_STAT_GROUPS))
    if stat_type not in ("player", "team"):
        raise ValidationError(stat_type, "stat type", ["player", "team"])

    if start_date is None or end_date is None:
        if season is None:
            raise ValidationError(None, "season (or explicit start_date/end_date)")
        start_date = start_date or f"{season}-03-01"
        end_date = end_date or f"{season}-11-30"

    if isinstance(splits, int | str):
        splits = [splits]
    if isinstance(pitch_splits, int | str):
        pitch_splits = [pitch_splits]

    codes: list[int] = []
    for s in splits or []:
        if isinstance(s, str):
            if s not in SPLIT_CODES:
                raise ValidationError(s, "split", list(SPLIT_CODES))
            val = SPLIT_CODES[s]
            if isinstance(val, dict):
                codes.append(val[position])
            else:
                codes.append(val)
        else:
            codes.append(s)

    pitch_codes: list[int] = []
    for p in pitch_splits or []:
        if isinstance(p, str):
            if p not in PITCH_SPLIT_CODES:
                raise ValidationError(p, "pitch split", list(PITCH_SPLIT_CODES))
            pitch_codes.append(PITCH_SPLIT_CODES[p])
        else:
            pitch_codes.append(p)

    body: dict[str, Any] = {
        "strPlayerId": str(player_id),
        "strSplitArr": codes,
        "strSplitArrPitch": pitch_codes,
        "strGroup": "season",
        "strPosition": position,
        "strType": SPLIT_STAT_GROUPS[stat_group],
        "strStartDate": start_date,
        "strEndDate": end_date,
        "strSplitTeams": False,
        "dctFilters": filters or [],
        "strStatType": stat_type,
        "strAutoPt": "false",
        "arrPlayerId": [],
    }
    if extra_body:
        body.update(extra_body)

    payload = fg_json_post("/api/leaders/splits/splits-leaders", body)
    if not isinstance(payload, dict) or "data" not in payload:
        raise FangraphsError(
            f"Unexpected splits payload shape: {type(payload).__name__}"
        )
    data = payload["data"]
    if not isinstance(data, list):
        raise FangraphsError(f"Expected a list under 'data', got {type(data).__name__}")
    return data
