"""Baseball Savant leaderboard registry, fetcher, and typed wrappers.

Returns raw ``list[dict]`` for CSV leaderboards; HTML-backed leaderboards
(park factors, hot stove, rolling windows) return parsed JSON
via :func:`_fetch_html_json`.

Every registry entry is a dict with these fields:

    category           "batting" | "pitching" | "fielding" | "catching" |
                       "running" | "other"
    display_name       human name
    type_param         list[str] | None of valid values for the ``type`` param
    required_params    list[str]
    optional_params    list[str]
    min_param          str | None — the leaderboard's min-threshold param name
    year_start         int | None
    year_format        "int" | "special" | "camelCase_season" | "season_array"
    player_id_behavior "supported" | "ignored" | "breaks" | "unknown"
    key_columns        list[str]
    notes              str | None

For non-CSV leaderboards (HTML-embedded JSON or browser-only):

    csv_available      False
    access_via         "_fetch_html_json:<var_name>" | "browser_only"

``year_format`` is load-bearing — it controls how :func:`fetch_leaderboard`
emits the season into the query string:

    int                ``year=<YYYY>``
    special            ``year=<composite string>``   (e.g. "2024_spin-based")
    camelCase_season   ``seasonStart=<YYYY>`` + ``seasonEnd=<YYYY>``
                       (single year -> both equal; ranges supported)
    season_array       ``season[]=<YYYY>``           (array param, repeatable)

The three bat-tracking boards IGNORE the standard ``year=`` param: passing it
silently returns the current season. Their registry entries use
``camelCase_season`` (``bat-tracking``, ``bat-tracking/swing-path-attack-angle``)
and ``season_array`` (``bat-tracking/swing-timing-miss-distance``).
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from fungo import http
from fungo.exceptions import SavantError, ValidationError
from fungo.statcast.search import BASE_URL, _fetch_csv

#####################################################################
# URL path overrides
#####################################################################

# Leaderboards with non-standard URL paths (not under /leaderboard/<slug>).
LEADERBOARD_PATHS: dict[str, str] = {
    "directional-oaa": "/directional_outs_above_average",
    # Primary running-splits path. /leaderboard/running-splits returns 404.
    "running-splits": "/running_splits",
    "running-splits-alt": "/running_splits",  # alternate slug alias
    "sprint-speed-alt": "/sprint_speed_leaderboard",
    "catch-probability-alt": "/catch_probability_leaderboard",
    "expected-stats-alt": "/expected_statistics",
    # Lives under /visuals/ — still serves CSV with csv=true
    "batting-stance": "/visuals/batting-stance",
}


#####################################################################
# Registry
#####################################################################

LEADERBOARDS: dict[str, dict[str, Any]] = {
    # ---------------- BATTING ----------------
    "exit-velocity-barrels": {
        "category": "batting",
        "display_name": "Exit Velocity & Barrels",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_bbe"],
        "min_param": "min_bbe",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "ignored",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "attempts",
            "avg_hit_speed",
            "max_hit_speed",
            "barrels",
            "brl_percent",
        ],
        "notes": None,
    },
    "expected_statistics": {
        "category": "batting",
        "display_name": "Expected Statistics (xBA/xSLG/xwOBA/xERA)",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pa", "min_pitches"],
        "min_param": "min_pa",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "ignored",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "pa",
            "bip",
            "ba",
            "est_ba",
            "slg",
            "est_slg",
            "woba",
            "est_woba",
        ],
        "notes": None,
    },
    "bat-tracking": {
        "category": "batting",
        "display_name": "Bat Tracking",
        "type_param": ["batter", "batting-team", "pitcher", "pitching-team", "league"],
        # NOT "year". Uses camelCase season params (see year_format).
        "required_params": ["seasonStart", "seasonEnd"],
        "optional_params": ["type", "minSwings", "gameType"],
        "min_param": "minSwings",
        "year_start": 2023,
        "year_format": "camelCase_season",
        "player_id_behavior": "ignored",
        "key_columns": [
            "id",
            "name",
            "swings_competitive",
            "contact",
            "avg_bat_speed",
            "hard_swing_rate",
            "squared_up_per_swing",
            "blast_per_swing",
            "swing_length",
            "swords",
            "batter_run_value",
        ],
        "notes": (
            "Hawk-Eye bat tracking, 2023+. IGNORES year=; use seasonStart/seasonEnd "
            "(camelCase). min param is minSwings (q,1,5,10,25,50,100,200). player_id "
            "ignored. type accepts batter/batting-team/pitcher/pitching-team/league "
            "(team views return ~30 rows, league one). A multi-year (seasonStart != "
            "seasonEnd) range returns ONE aggregated row per player across the span "
            "(no year column). The raw `whiffs` column is blank in every view; use "
            "`whiff_per_swing` (populated in all views). Returns id/name, not "
            "player_id."
        ),
    },
    "bat-tracking/swing-path-attack-angle": {
        "category": "batting",
        "display_name": "Swing Path / Attack Angle",
        "type_param": ["batter", "batting-team", "pitcher", "pitching-team", "league"],
        "required_params": ["seasonStart", "seasonEnd"],
        "optional_params": ["type", "minSwings", "gameType"],
        "min_param": "minSwings",
        "year_start": 2023,
        "year_format": "camelCase_season",
        "player_id_behavior": "ignored",
        "key_columns": [
            "id",
            "name",
            "side",
            "avg_bat_speed",
            "swing_tilt",
            "attack_angle",
            "attack_direction",
            "ideal_attack_angle_rate",
            "avg_intercept_y_vs_plate",
            "competitive_swings",
        ],
        "notes": (
            "Swing path metrics, 2023+. Same camelCase season params as bat-tracking. "
            "attack_angle/attack_direction/swing_tilt in degrees; "
            "ideal_attack_angle_rate is a 0-1 share. player_id ignored."
        ),
    },
    "bat-tracking/swing-timing-miss-distance": {
        "category": "batting",
        "display_name": "Swing Timing / Miss Distance",
        "type_param": ["batter", "batting-team", "pitcher", "pitching-team", "league"],
        # Array param: season[] (multi-year capable). NOT year=, NOT seasonStart.
        "required_params": ["season[]"],
        "optional_params": [
            "type",
            "min",
            "minSplit",
            "splitYear",
            "gameType[]",
            "showColumn",
        ],
        "min_param": "min",  # plain "min" (q or integer) — NOT minSwings
        "year_start": 2023,
        "year_format": "season_array",
        "player_id_behavior": "ignored",
        "key_columns": [
            "id",
            "name",
            "year",
            "team_name",
            "miss_distance",
            "whiff_rate",
            "n_swings",
            "perfect_percent",
            "flawed_percent",
            "early_percent",
            "on_time_percent",
            "late_percent",
            "over_percent",
            "under_percent",
        ],
        "notes": (
            "Swing timing + miss distance, 2023+. miss_distance is in INCHES (avg "
            "distance a whiff misses the ball). Uses season[] array param + min (not "
            "minSwings) and is a true multi-select: season[]=[2023,2024] returns one "
            "row per player PER year (has a `year` column). Timing axes: "
            "early/on_time/late (y), over/under (z), tied_up/flawed (x). player_id "
            "ignored."
        ),
    },
    "batted-ball": {
        "category": "batting",
        "display_name": "Batted Ball Profile",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_bbe"],
        "min_param": "min_bbe",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "ba",
            "slg",
            "xba",
            "xslg",
            "xwoba",
            "la_avg",
            "barrel_batted_rate",
        ],
        "notes": None,
    },
    "percentile-rankings": {
        "category": "batting",
        "display_name": "Percentile Rankings",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "player_id"],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "supported",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "year",
            "xba",
            "xslg",
            "xwoba",
            "exit_velocity_avg",
        ],
        "notes": "player_id supported server-side. Filters out null player 999999.",
    },
    "pitch-arsenal-stats": {
        "category": "batting",
        "display_name": "Pitch Arsenal Stats",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "pitch_type", "min_pa", "min_pitches"],
        "min_param": "min_pa",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "ignored",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "pitch_type",
            "pitches",
            "pa",
            "ba",
            "slg",
            "woba",
            "whiff_percent",
            "run_value",
            "run_value_per100",
        ],
        "notes": None,
    },
    "home-runs": {
        "category": "batting",
        "display_name": "Home Runs",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type"],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "total_home_runs",
            "avg_hr_distance",
            "avg_launch_speed",
            "avg_launch_angle",
        ],
        "notes": None,
    },
    "statcast-year-to-year": {
        "category": "batting",
        "display_name": "Year-Over-Year Changes",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pa", "min_pitches", "year_pair"],
        "min_param": "min_pa",
        "year_start": 2016,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": ["last_name", "first_name", "player_id"],
        "notes": (
            "Accepts either year=YYYY (delta vs previous year) or "
            'year_pair="YYYY-YYYY".'
        ),
    },
    "pitch-tempo": {
        "category": "batting",
        "display_name": "Pitch Tempo",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pa", "min_pitches"],
        "min_param": "min_pa",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "avg_time_between_pitches",
        ],
        "notes": "Most meaningful from pitch clock era (2023+).",
    },
    # ---------------- PITCHING ----------------
    "active-spin": {
        "category": "pitching",
        "display_name": "Active Spin",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2017,
        "year_format": "special",
        "player_id_behavior": "breaks",
        "key_columns": [
            "pitcher",
            "pitcher_id",
            "pitch_type",
            "n_pitches",
            "active_spin",
            "active_spin_pct",
            "spin_rate",
            "velocity",
        ],
        "notes": (
            "year must be 'YYYY_spin-based' or 'YYYY_observed'. Use "
            "active_spin_year() helper. player_id BREAKS endpoint."
        ),
    },
    "pitch-movement": {
        "category": "pitching",
        "display_name": "Pitch Movement",
        "type_param": None,
        "required_params": ["year", "pitch_type"],
        "optional_params": ["pitcher_throws", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "breaks",
        "key_columns": [
            "last_name",
            "first_name",
            "pitcher_id",
            "pitch_type",
            "pitches",
            "pitcher_hand",
            "avg_speed",
            "avg_spin",
            "avg_break_x",
            "avg_break_z",
        ],
        "notes": "pitch_type is required. player_id BREAKS — filter client-side.",
    },
    "pitch-arsenals": {
        "category": "pitching",
        "display_name": "Pitch Arsenals (Mix Breakdown)",
        "type_param": ["pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "n_ff",
            "n_si",
            "n_sl",
            "ff_pct",
            "si_pct",
            "sl_pct",
        ],
        "notes": None,
    },
    "spin-direction-pitches": {
        "category": "pitching",
        "display_name": "Spin Direction",
        "type_param": ["pitcher"],
        "required_params": ["year", "pitch_type"],
        "optional_params": ["type", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2020,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "pitch_type",
            "pitches",
            "spin_rate",
            "spin_direction",
            "active_spin_pct",
        ],
        "notes": "Hawk-Eye required (2020+).",
    },
    "pitcher-arm-angles": {
        "category": "pitching",
        "display_name": "Arm Angles",
        "type_param": ["pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2020,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "pitches",
            "arm_angle",
            "pitcher_hand",
            "team",
        ],
        "notes": "Hawk-Eye required (2020+).",
    },
    "pitcher-running-game": {
        "category": "pitching",
        "display_name": "Pitcher Running Game",
        "type_param": ["pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_attempts"],
        "min_param": "min_attempts",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "sb_attempts",
            "sb_pct",
            "stolen_bases",
            "caught_stealing",
            "pickoffs",
        ],
        "notes": None,
    },
    # ---------------- FIELDING ----------------
    "outs_above_average": {
        "category": "fielding",
        "display_name": "Outs Above Average",
        "type_param": ["fielder"],
        "required_params": ["year"],
        "optional_params": ["type", "position", "min_attempts"],
        "min_param": "min_attempts",
        "year_start": 2016,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "position",
            "attempts",
            "outs_above_average",
        ],
        "notes": None,
    },
    "fielding-run-value": {
        "category": "fielding",
        "display_name": "Fielding Run Value",
        "type_param": ["fielder"],
        "required_params": ["year"],
        "optional_params": ["type", "position", "min_inn"],
        "min_param": "min_inn",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "position",
            "inn",
            "run_value",
            "run_value_per_inn",
        ],
        "notes": None,
    },
    "catch-probability-alt": {
        "category": "fielding",
        "display_name": "Catch Probability",
        "type_param": ["fielder"],
        "required_params": ["year"],
        "optional_params": ["type", "min_attempts", "star_min", "star_max"],
        "min_param": "min_attempts",
        "year_start": 2016,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "attempts",
            "success_rate_raw",
            "outs_above_average",
        ],
        "notes": "Uses non-standard path /catch_probability_leaderboard.",
    },
    "directional-oaa": {
        "category": "fielding",
        "display_name": "Directional OAA",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["position", "min_attempts"],
        "min_param": "min_attempts",
        "year_start": 2016,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "position",
            "oaa_in",
            "oaa_out",
            "oaa_left",
            "oaa_right",
            "oaa_total",
        ],
        "notes": "Uses non-standard path /directional_outs_above_average.",
    },
    "outfield_jump": {
        "category": "fielding",
        "display_name": "Outfield Jump",
        "type_param": ["fielder"],
        "required_params": ["year"],
        "optional_params": ["type", "min_opportunities"],
        "min_param": "min_opportunities",
        "year_start": 2020,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "opportunities",
            "jump_distance",
            "reaction_distance",
        ],
        "notes": "Hawk-Eye required (2020+).",
    },
    "arm-strength": {
        "category": "fielding",
        "display_name": "Arm Strength",
        "type_param": ["fielder"],
        "required_params": ["year"],
        "optional_params": ["type", "position", "min_throws"],
        "min_param": "min_throws",
        "year_start": 2020,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "position",
            "throws",
            "max_arm_strength",
            "avg_arm_strength",
        ],
        "notes": "Hawk-Eye required (2020+).",
    },
    "baserunning": {
        "category": "fielding",
        "display_name": "Extra Bases / Arm Value",
        "type_param": ["Fld", "Run"],
        "required_params": ["year"],
        "optional_params": ["type", "position", "min_opportunities"],
        "min_param": "min_opportunities",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "attempts",
            "arm_value",
            "kills",
            "assists",
        ],
        "notes": "type='Fld' for arm value; default is extra-bases runner view.",
    },
    # ---------------- CATCHING ----------------
    "catcher-framing": {
        "category": "catching",
        "display_name": "Catcher Framing",
        "type_param": ["catcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "n",
            "extra_strikes",
            "framing_runs",
            "strike_rate",
        ],
        "notes": None,
    },
    "poptime": {
        "category": "catching",
        "display_name": "Pop Time",
        "type_param": ["catcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_attempts", "exchange_min", "exchange_max"],
        "min_param": "min_attempts",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "pop_2b",
            "pop_3b",
            "exchange_2b",
            "arm_2b",
        ],
        "notes": None,
    },
    "catcher-blocking": {
        "category": "catching",
        "display_name": "Catcher Blocking",
        "type_param": ["catcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_blocks"],
        "min_param": "min_blocks",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "n",
            "blocks_above_average",
            "run_value",
        ],
        "notes": None,
    },
    "catcher-throwing": {
        "category": "catching",
        "display_name": "Catcher Throwing",
        "type_param": ["catcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_attempts"],
        "min_param": "min_attempts",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "sb_attempts",
            "cs",
            "cs_pct",
            "pop_time",
            "arm_speed",
        ],
        "notes": None,
    },
    "catcher-stance": {
        "category": "catching",
        "display_name": "Catcher Receiving Stance",
        "type_param": ["catcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pitches"],
        "min_param": "min_pitches",
        "year_start": 2020,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": ["id", "name", "year", "pitches"],
        "notes": (
            "Hawk-Eye required (2020+). NOTE: returns different column names than "
            "other catcher endpoints (id, name, year, pitches)."
        ),
    },
    # ---------------- RUNNING ----------------
    "sprint_speed": {
        "category": "running",
        "display_name": "Sprint Speed",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_opportunities"],
        "min_param": "min_opportunities",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "ignored",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "sprint_speed",
            "hp_to_1b",
            "opportunities",
        ],
        "notes": None,
    },
    "running-splits": {
        "category": "running",
        "display_name": "90-Foot Running Splits",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_opportunities"],
        "min_param": "min_opportunities",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "n_tracked",
            "sprint_speed",
            "hp1b",
        ],
        "notes": (
            "Uses non-standard path /running_splits. (The "
            "/leaderboard/running-splits URL does not exist.)"
        ),
    },
    "baserunning-run-value": {
        "category": "running",
        "display_name": "Baserunning Run Value",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_opportunities"],
        "min_param": "min_opportunities",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "opportunities",
            "run_value",
            "outs",
            "extra_bases",
        ],
        "notes": None,
    },
    "basestealing-run-value": {
        "category": "running",
        "display_name": "Basestealing Run Value",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_attempts"],
        "min_param": "min_attempts",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "attempts",
            "sb",
            "cs",
            "run_value",
        ],
        "notes": None,
    },
    # ---------------- OTHER ----------------
    "custom": {
        "category": "other",
        "display_name": "Custom Leaderboard",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["type", "min_pa", "min_pitches", "custom_col"],
        "min_param": "min_pa",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [],
        "notes": "Pass custom_col as comma-separated Statcast column names.",
    },
    "game-scores": {
        "category": "other",
        "display_name": "Enhanced Game Scores",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": ["min_gs"],
        "min_param": "min_gs",
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "gs",
            "avg_game_score",
            "max_game_score",
        ],
        "notes": None,
    },
    "abs-challenges": {
        "category": "other",
        "display_name": "ABS Challenges",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": [],
        "min_param": None,
        "year_start": 2025,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "challenges",
            "wins",
            "losses",
            "win_pct",
        ],
        "notes": "Endpoint exists but returns empty data for 2023-2025 as of writing.",
    },
    "pitch-timer-infractions": {
        "category": "other",
        "display_name": "Pitch Timer Infractions",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": [],
        "min_param": None,
        "year_start": 2023,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "last_name",
            "first_name",
            "player_id",
            "team",
            "infractions",
            "inf_per_game",
        ],
        "notes": (
            "Do NOT pass type=pitcher — endpoint returns 0 rows with type filter. "
            "Slug 'timer-infractions' does NOT exist."
        ),
    },
    "swing-take": {
        "category": "other",
        "display_name": "Swing/Take Run Value",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": [],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "supported",
        "key_columns": ["last_name", "first_name", "player_id"],
        "notes": (
            "Plain year=YYYY works. Documented group/type/sub_type filters return "
            "0 rows — avoid them."
        ),
    },
    "statcast-park-factors": {
        "category": "other",
        "display_name": "Statcast Park Factors",
        "type_param": ["year", "batter", "pitcher", "venue"],
        "required_params": ["year"],
        "optional_params": ["type", "bat_side", "condition", "stat"],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [
            "venue_name",
            "venue_id",
            "team",
            "year",
            "park_factor",
            "hr_factor",
            "r_factor",
        ],
        "notes": "HTML-scraped (no CSV). Use get_park_factors() wrapper.",
        "csv_available": False,
        "access_via": "_fetch_html_json:data",
    },
    "rolling": {
        "category": "other",
        "display_name": "Rolling Windows",
        "type_param": None,
        "required_params": ["year"],
        "optional_params": [],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [],
        "notes": (
            "HTML-embedded JSON as `var rolling = {...}`. Use get_rolling_windows() "
            "wrapper. Returns a dict — inspect structure before extracting."
        ),
        "csv_available": False,
        "access_via": "_fetch_html_json:rolling",
    },
    "hot-stove": {
        "category": "other",
        "display_name": "Hot Stove",
        "type_param": ["batter", "pitcher"],
        "required_params": ["year"],
        "optional_params": ["side"],
        "min_param": None,
        "year_start": 2015,
        "year_format": "int",
        "player_id_behavior": "unknown",
        "key_columns": [],
        "notes": "HTML-embedded JSON. Use get_hot_stove() wrapper.",
        "csv_available": False,
        "access_via": "_fetch_html_json:HOT_STOVE_BATTER_DATA",
    },
}


#####################################################################
# Registry introspection
#####################################################################


def list_leaderboards(category: str | None = None) -> list[str]:
    """Return leaderboard slugs, optionally filtered by category.

    Args:
        category: ``None`` (all) or one of ``"batting"``, ``"pitching"``,
            ``"fielding"``, ``"catching"``, ``"running"``, ``"other"``.

    Returns:
        Sorted ``list[str]`` of slugs.
    """
    if category is None:
        return sorted(LEADERBOARDS)
    return sorted(
        slug for slug, meta in LEADERBOARDS.items() if meta.get("category") == category
    )


def describe_leaderboard(slug: str) -> dict[str, Any]:
    """Return the registry entry for ``slug``.

    Args:
        slug: A leaderboard slug.

    Returns:
        The registry entry dict.

    Raises:
        ValidationError: If ``slug`` is unknown (with a did-you-mean suggestion).
    """
    if slug not in LEADERBOARDS:
        raise ValidationError(slug, "leaderboard", valid_values=list(LEADERBOARDS))
    return LEADERBOARDS[slug]


#####################################################################
# Year-format param emission
#####################################################################


def _emit_year(
    query: dict[str, Any], slug: str, year: int | str | tuple[int, int] | list[int]
) -> None:
    """Emit the season into ``query`` using the slug's ``year_format``.

    The bat-tracking boards ignore ``year=`` and silently return the current
    season unless their camelCase / array params are emitted. The two
    camelCase boards take a contiguous RANGE; the array board takes a true
    multi-select.

    - ``int`` / ``special`` -> ``year=<str(year)>`` (``special`` expects a
      pre-composed string; build it with :func:`active_spin_year`).
    - ``camelCase_season`` -> ``seasonStart=str(min(year))`` +
      ``seasonEnd=str(max(year))`` for a tuple/list range, else both = the
      single year.
    - ``season_array`` -> ``season[]`` as a LIST value; transport's
      ``urlencode(..., doseq=True)`` repeats it (``season[]=2023&season[]=2024``).
      A scalar year is emitted as a one-element list.

    Unknown slugs default to ``int``.

    Raises:
        ValidationError: If a multi-year tuple/list is passed to an ``int`` /
            ``special`` board (only the bat-tracking boards support multi-year).
    """
    year_format = LEADERBOARDS.get(slug, {}).get("year_format", "int")
    if year_format == "camelCase_season":
        if isinstance(year, (tuple, list)):
            if not year:
                raise ValidationError(
                    year, "year", ["a non-empty list or tuple of seasons"]
                )
            query["seasonStart"] = str(min(year))
            query["seasonEnd"] = str(max(year))
        else:
            query["seasonStart"] = str(year)
            query["seasonEnd"] = str(year)
    elif year_format == "season_array":
        years = year if isinstance(year, (tuple, list)) else [year]
        query["season[]"] = [str(y) for y in years]
    else:  # "int" or "special" (pre-composed string)
        # Only the bat-tracking boards (handled above) accept a multi-year
        # sequence. The int/special boards take a single season; str([2023, 2024])
        # would silently send a mangled year= and return wrong/empty data, so fail
        # loud (a str passes through — active-spin's composite year still works).
        if isinstance(year, (tuple, list)):
            raise ValidationError(
                year, f"single-year value for the {slug!r} leaderboard"
            )
        query["year"] = str(year)


#####################################################################
# Core leaderboard fetch
#####################################################################


def fetch_leaderboard(
    name: str,
    year: int | str | tuple[int, int] | list[int] | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Fetch a Baseball Savant leaderboard as ``list[dict]``.

    Resolves the URL path (registry overrides in :data:`LEADERBOARD_PATHS`),
    emits the season per the slug's ``year_format`` (see :func:`_emit_year`), and
    handles ``player_id`` per the slug's ``player_id_behavior``:

    - ``supported`` — pass ``player_id`` in the URL (server-side filter).
    - ``ignored`` — pass ``player_id`` (harmless) and filter client-side.
    - ``breaks`` — omit ``player_id`` (would force an HTML response) and filter
      client-side.

    The client-side filter matches on the first of ``player_id`` / ``id`` present
    in a row, so it works on the bat-tracking and catcher-stance boards (which
    return ``id`` rather than ``player_id``).

    Args:
        name: Leaderboard slug (e.g. ``"active-spin"``, ``"bat-tracking"``).
        year: Season. For ``year_format="special"`` slugs, a composite string
            (e.g. ``"2024_spin-based"``).
        player_id: MLBAM player ID. Optional.
        **params: Endpoint-specific params (``type``, ``min_*``, ``position``...).

    Returns:
        ``list[dict]`` — one row per leaderboard entry.

    Raises:
        SavantError: If a response is HTML rather than CSV.
        RequestError: On transport failure.
    """
    path = LEADERBOARD_PATHS.get(name, f"/leaderboard/{name}")
    url = f"{BASE_URL}{path}"

    query: dict[str, Any] = dict(params)
    if year is not None:
        _emit_year(query, name, year)
    query["csv"] = "true"

    pid_behavior = LEADERBOARDS.get(name, {}).get("player_id_behavior", "ignored")
    needs_client_filter = False

    if player_id is not None:
        if pid_behavior == "breaks":
            needs_client_filter = True
        else:
            query["player_id"] = str(player_id)
            if pid_behavior == "ignored":
                needs_client_filter = True

    rows = _fetch_csv(url, params=query)

    if player_id is not None and needs_client_filter:
        pid_str = str(player_id)
        rows = [r for r in rows if _row_player_id(r) == pid_str]

    return rows


def _row_player_id(row: dict[str, Any]) -> str:
    """Return a row's player id, checking ``player_id`` then ``id``."""
    for key in ("player_id", "id"):
        if key in row:
            return str(row[key])
    return ""


def get_leaderboard(
    slug: str,
    year: int | str | tuple[int, int] | list[int] | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Registry-aware wrapper around :func:`fetch_leaderboard`.

    Args:
        slug: A leaderboard slug.
        year: Season (composite string for ``year_format="special"``; a tuple/list
            range for ``camelCase_season``; a list for ``season_array``).
        **params: Endpoint-specific params.

    Returns:
        ``list[dict[str, Any]]`` of rows.

    Raises:
        ValidationError: If ``slug`` is unknown (with a did-you-mean suggestion).
        ValueError: If ``slug`` has no CSV endpoint, or is ``year_format="special"``
            and ``year`` is an ``int`` (use :func:`active_spin_year`).
    """
    if slug not in LEADERBOARDS:
        raise ValidationError(slug, "leaderboard", valid_values=list(LEADERBOARDS))

    meta = LEADERBOARDS[slug]

    if meta.get("csv_available") is False:
        raise ValidationError(
            slug,
            "leaderboard",
            [
                f"a CSV-available slug (access_via={meta.get('access_via')} — "
                "use the typed wrapper instead: get_park_factors, "
                "get_rolling_windows, get_hot_stove)"
            ],
        )

    if meta.get("year_format") == "special" and isinstance(year, int):
        raise ValidationError(
            year,
            f"year for {slug!r}",
            [
                "a composite year string (e.g., '2024_spin-based')"
                " — use active_spin_year(year, method)"
            ],
        )

    return fetch_leaderboard(slug, year=year, **params)


#####################################################################
# Helpers
#####################################################################


def active_spin_year(year: int, method: str = "spin-based") -> str:
    """Build the composite ``year`` value the active-spin leaderboard requires.

    Args:
        year: Season (e.g. ``2024``).
        method: ``"spin-based"`` or ``"observed"``.

    Returns:
        A string like ``"2024_spin-based"``.

    Raises:
        ValidationError: If ``method`` is not ``"spin-based"`` or ``"observed"``.
    """
    if method not in ("spin-based", "observed"):
        raise ValidationError(method, "method", valid_values=["spin-based", "observed"])
    return f"{year}_{method}"


def _cast_numeric(
    rows: list[dict[str, Any]], cols: list[str] | None = None
) -> list[dict[str, Any]]:
    """Return a NEW ``list[dict]`` with numeric columns coerced to ``float``.

    Empty strings become ``None``; non-numeric strings are left as ``str``.
    ``cols=None`` auto-detects from the first row's keys.

    Args:
        rows: ``list[dict]`` to coerce.
        cols: Columns to coerce, or ``None`` to use every key in the first row.

    Returns:
        A ``list[dict]`` with coerced values.
    """
    if not rows:
        return []

    if cols is None:
        cols = list(rows[0])

    out: list[dict[str, Any]] = []
    for r in rows:
        nr = dict(r)
        for c in cols:
            if c not in nr:
                continue
            v = nr[c]
            if v == "" or v is None:
                nr[c] = None
            else:
                with contextlib.suppress(TypeError, ValueError):
                    nr[c] = float(v)
        out.append(nr)
    return out


#####################################################################
# Percentile rankings
#####################################################################


def get_percentile_rankings(
    player_type: str = "batter",
    year: int | None = None,
    player_id: int | str | None = None,
) -> list[dict[str, Any]]:
    """Get MLB percentile rankings (0-100) from Baseball Savant.

    With ``player_id`` set, returns that player's career year-by-year percentiles
    (server-side filter). Otherwise returns all players for ``year``. The null
    placeholder player (``player_id == "999999"``) is dropped.

    Args:
        player_type: ``"batter"`` or ``"pitcher"``.
        year: Season. Optional when ``player_id`` is set.
        player_id: MLBAM player ID. Optional.

    Returns:
        ``list[dict]`` of percentile rows.
    """
    rows = fetch_leaderboard(
        "percentile-rankings", year=year, player_id=player_id, type=player_type
    )
    return [r for r in rows if r.get("player_id", "") != "999999"]


#####################################################################
# Typed CSV leaderboard wrappers
#####################################################################


def get_exit_velocity_barrels(
    year: int,
    type: str = "batter",
    min_bbe: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Exit Velocity & Barrels leaderboard."""
    if min_bbe is not None:
        params["min_bbe"] = min_bbe
    return fetch_leaderboard(
        "exit-velocity-barrels", year=year, player_id=player_id, type=type, **params
    )


def get_expected_statistics(
    year: int,
    type: str = "batter",
    min_pa: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Expected stats (xBA/xSLG/xwOBA/xERA)."""
    if min_pa is not None:
        params["min_pa"] = min_pa
    return fetch_leaderboard(
        "expected_statistics", year=year, player_id=player_id, type=type, **params
    )


def get_bat_tracking(
    season: int | tuple[int, int],
    type: str = "batter",
    min_swings: int | str | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Bat Tracking leaderboard (Hawk-Eye 2023+).

    Uses camelCase season params (``seasonStart``/``seasonEnd``, emitted via the
    registry's ``year_format``) and ``minSwings`` (``q`` or an integer). Passing
    ``year=`` would silently return the current season.

    Args:
        season: A single year, or a ``(start, end)`` tuple for a contiguous range
            (emitted as ``seasonStart=min`` / ``seasonEnd=max``).
        type: View — ``"batter"``, ``"pitcher"``, ``"league"``, etc.
        min_swings: ``minSwings`` threshold (``"q"`` or an integer).
        player_id: MLBAM player ID (ignored server-side; filtered client-side).
        **params: Endpoint-specific params.

    Returns:
        ``list[dict[str, Any]]`` of rows.
    """
    if min_swings is not None:
        params["minSwings"] = min_swings
    return fetch_leaderboard(
        "bat-tracking", year=season, player_id=player_id, type=type, **params
    )


def get_swing_path_attack_angle(
    season: int | tuple[int, int],
    type: str = "batter",
    min_swings: int | str | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Swing Path / Attack Angle leaderboard.

    Same camelCase season scheme + ``minSwings`` as :func:`get_bat_tracking`.

    Args:
        season: A single year, or a ``(start, end)`` tuple for a contiguous range.
        type: View — ``"batter"``, ``"pitcher"``, ``"league"``, etc.
        min_swings: ``minSwings`` threshold (``"q"`` or an integer).
        player_id: MLBAM player ID (ignored server-side; filtered client-side).
        **params: Endpoint-specific params.

    Returns:
        ``list[dict[str, Any]]`` of rows.
    """
    if min_swings is not None:
        params["minSwings"] = min_swings
    return fetch_leaderboard(
        "bat-tracking/swing-path-attack-angle",
        year=season,
        player_id=player_id,
        type=type,
        **params,
    )


def get_swing_timing_miss_distance(
    season: int | list[int],
    type: str = "batter",
    min: int | str = "q",
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Swing Timing / Miss Distance leaderboard (2023+).

    Uses the ``season[]`` array param (emitted via the registry's ``year_format``)
    and the plain ``min`` threshold (``q`` or an integer) — NOT ``minSwings``.
    ``miss_distance`` is in inches. ``player_id`` is ignored server-side and
    filtered client-side.

    Args:
        season: A single year, or a ``list`` of years for a true multi-select
            (emitted as repeated ``season[]`` params).
        type: View — ``"batter"``, ``"pitcher"``, ``"league"``, etc.
        min: Plain ``min`` threshold (``"q"`` or an integer).
        player_id: MLBAM player ID (ignored server-side; filtered client-side).
        **params: Endpoint-specific params.

    Returns:
        ``list[dict[str, Any]]`` of rows.
    """
    params["min"] = min
    return fetch_leaderboard(
        "bat-tracking/swing-timing-miss-distance",
        year=season,
        player_id=player_id,
        type=type,
        **params,
    )


def get_batted_ball(
    year: int,
    type: str = "batter",
    min_bbe: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Batted Ball Profile leaderboard."""
    if min_bbe is not None:
        params["min_bbe"] = min_bbe
    return fetch_leaderboard(
        "batted-ball", year=year, player_id=player_id, type=type, **params
    )


def get_pitch_arsenal_stats(
    year: int,
    type: str = "pitcher",
    min_pa: int | None = None,
    pitch_type: str | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitch Arsenal Stats (per-pitch-type batter/pitcher results)."""
    if min_pa is not None:
        params["min_pa"] = min_pa
    if pitch_type is not None:
        params["pitch_type"] = pitch_type
    return fetch_leaderboard(
        "pitch-arsenal-stats", year=year, player_id=player_id, type=type, **params
    )


def get_home_runs(
    year: int,
    type: str = "batter",
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Home Runs leaderboard."""
    return fetch_leaderboard(
        "home-runs", year=year, player_id=player_id, type=type, **params
    )


def get_year_to_year(
    year: int | None = None,
    year_pair: str | None = None,
    type: str = "batter",
    min_pa: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Year-over-year changes leaderboard."""
    if year_pair is not None:
        params["year_pair"] = year_pair
    if min_pa is not None:
        params["min_pa"] = min_pa
    return fetch_leaderboard(
        "statcast-year-to-year", year=year, player_id=player_id, type=type, **params
    )


def get_pitch_tempo(
    year: int,
    type: str = "pitcher",
    min_pa: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitch Tempo leaderboard (most meaningful 2023+)."""
    if min_pa is not None:
        params["min_pa"] = min_pa
    return fetch_leaderboard(
        "pitch-tempo", year=year, player_id=player_id, type=type, **params
    )


def get_active_spin(
    year: int | str,
    method: str = "spin-based",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Active Spin leaderboard.

    ``year`` may be an int (auto-composed with ``method``) or a pre-built string.
    ``player_id`` BREAKS this endpoint — filtered client-side.
    """
    year_str = active_spin_year(year, method) if isinstance(year, int) else year
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "active-spin", year=year_str, player_id=player_id, **params
    )


def get_pitch_movement(
    year: int,
    pitch_type: str,
    pitcher_throws: str | None = None,
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitch Movement leaderboard. ``pitch_type`` is REQUIRED."""
    params["pitch_type"] = pitch_type
    if pitcher_throws is not None:
        params["pitcher_throws"] = pitcher_throws
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard("pitch-movement", year=year, player_id=player_id, **params)


def get_pitch_arsenals(
    year: int,
    type: str = "pitcher",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitch Arsenals — per-pitcher pitch mix breakdown."""
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "pitch-arsenals", year=year, player_id=player_id, type=type, **params
    )


def get_spin_direction(
    year: int,
    pitch_type: str,
    type: str = "pitcher",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Spin Direction leaderboard (Hawk-Eye 2020+). ``pitch_type`` required."""
    params["pitch_type"] = pitch_type
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "spin-direction-pitches", year=year, player_id=player_id, type=type, **params
    )


def get_arm_angles(
    year: int,
    type: str = "pitcher",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitcher Arm Angles (2020+)."""
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "pitcher-arm-angles", year=year, player_id=player_id, type=type, **params
    )


def get_pitcher_running_game(
    year: int,
    type: str = "pitcher",
    min_attempts: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Pitcher Running Game leaderboard."""
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    return fetch_leaderboard(
        "pitcher-running-game", year=year, player_id=player_id, type=type, **params
    )


def get_outs_above_average(
    year: int,
    type: str = "fielder",
    position: str | None = None,
    min_attempts: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Outs Above Average fielding leaderboard."""
    if position is not None:
        params["position"] = position
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    return fetch_leaderboard(
        "outs_above_average", year=year, player_id=player_id, type=type, **params
    )


def get_fielding_run_value(
    year: int,
    type: str = "fielder",
    position: str | None = None,
    min_inn: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Fielding Run Value leaderboard."""
    if position is not None:
        params["position"] = position
    if min_inn is not None:
        params["min_inn"] = min_inn
    return fetch_leaderboard(
        "fielding-run-value", year=year, player_id=player_id, type=type, **params
    )


def get_catch_probability(
    year: int,
    type: str = "fielder",
    min_attempts: int | None = None,
    star_min: int | None = None,
    star_max: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catch Probability leaderboard (uses non-standard path)."""
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    if star_min is not None:
        params["star_min"] = star_min
    if star_max is not None:
        params["star_max"] = star_max
    return fetch_leaderboard(
        "catch-probability-alt", year=year, player_id=player_id, type=type, **params
    )


def get_directional_oaa(
    year: int,
    position: str | None = None,
    min_attempts: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Directional OAA."""
    if position is not None:
        params["position"] = position
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    return fetch_leaderboard(
        "directional-oaa", year=year, player_id=player_id, **params
    )


def get_outfield_jump(
    year: int,
    type: str = "fielder",
    min_opportunities: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Outfield Jump (2020+)."""
    if min_opportunities is not None:
        params["min_opportunities"] = min_opportunities
    return fetch_leaderboard(
        "outfield_jump", year=year, player_id=player_id, type=type, **params
    )


def get_arm_strength(
    year: int,
    type: str = "fielder",
    position: str | None = None,
    min_throws: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Arm Strength leaderboard (2020+)."""
    if position is not None:
        params["position"] = position
    if min_throws is not None:
        params["min_throws"] = min_throws
    return fetch_leaderboard(
        "arm-strength", year=year, player_id=player_id, type=type, **params
    )


def get_baserunning(
    year: int,
    type: str | None = None,
    position: str | None = None,
    min_opportunities: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Extra Bases / Arm Value ('baserunning'). ``type='Fld'`` for arm value."""
    if type is not None:
        params["type"] = type
    if position is not None:
        params["position"] = position
    if min_opportunities is not None:
        params["min_opportunities"] = min_opportunities
    return fetch_leaderboard("baserunning", year=year, player_id=player_id, **params)


def get_catcher_framing(
    year: int,
    type: str = "catcher",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catcher Framing leaderboard."""
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "catcher-framing", year=year, player_id=player_id, type=type, **params
    )


def get_poptime(
    year: int,
    type: str = "catcher",
    min_attempts: int | None = None,
    exchange_min: float | None = None,
    exchange_max: float | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catcher Pop Time leaderboard."""
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    if exchange_min is not None:
        params["exchange_min"] = exchange_min
    if exchange_max is not None:
        params["exchange_max"] = exchange_max
    return fetch_leaderboard(
        "poptime", year=year, player_id=player_id, type=type, **params
    )


def get_catcher_blocking(
    year: int,
    type: str = "catcher",
    min_blocks: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catcher Blocking leaderboard."""
    if min_blocks is not None:
        params["min_blocks"] = min_blocks
    return fetch_leaderboard(
        "catcher-blocking", year=year, player_id=player_id, type=type, **params
    )


def get_catcher_throwing(
    year: int,
    type: str = "catcher",
    min_attempts: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catcher Throwing leaderboard."""
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    return fetch_leaderboard(
        "catcher-throwing", year=year, player_id=player_id, type=type, **params
    )


def get_catcher_stance(
    year: int,
    type: str = "catcher",
    min_pitches: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Catcher Receiving Stance (2020+). Returns id/name/year/pitches columns."""
    if min_pitches is not None:
        params["min_pitches"] = min_pitches
    return fetch_leaderboard(
        "catcher-stance", year=year, player_id=player_id, type=type, **params
    )


def get_sprint_speed(
    year: int,
    min_opportunities: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Sprint Speed leaderboard."""
    if min_opportunities is not None:
        params["min_opportunities"] = min_opportunities
    return fetch_leaderboard("sprint_speed", year=year, player_id=player_id, **params)


def get_running_splits(
    year: int,
    min_opportunities: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """90-Foot Running Splits. Uses /running_splits path."""
    if min_opportunities is not None:
        params["min_opportunities"] = min_opportunities
    return fetch_leaderboard("running-splits", year=year, player_id=player_id, **params)


def get_baserunning_run_value(
    year: int,
    min_opportunities: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Baserunning Run Value."""
    if min_opportunities is not None:
        params["min_opportunities"] = min_opportunities
    return fetch_leaderboard(
        "baserunning-run-value", year=year, player_id=player_id, **params
    )


def get_basestealing_run_value(
    year: int,
    min_attempts: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Basestealing Run Value."""
    if min_attempts is not None:
        params["min_attempts"] = min_attempts
    return fetch_leaderboard(
        "basestealing-run-value", year=year, player_id=player_id, **params
    )


def get_custom_leaderboard(
    year: int,
    type: str = "batter",
    custom_col: str | None = None,
    min_pa: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Custom leaderboard. Pass ``custom_col`` as comma-separated Statcast columns."""
    if custom_col is not None:
        params["custom_col"] = custom_col
    if min_pa is not None:
        params["min_pa"] = min_pa
    return fetch_leaderboard(
        "custom", year=year, player_id=player_id, type=type, **params
    )


def get_game_scores(
    year: int,
    min_gs: int | None = None,
    player_id: int | str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    """Enhanced Game Scores leaderboard."""
    if min_gs is not None:
        params["min_gs"] = min_gs
    return fetch_leaderboard("game-scores", year=year, player_id=player_id, **params)


def get_abs_challenges(
    year: int, player_id: int | str | None = None, **params: Any
) -> list[dict[str, Any]]:
    """ABS Challenges leaderboard. NOTE: returns empty for 2023-2025 as of writing."""
    return fetch_leaderboard("abs-challenges", year=year, player_id=player_id, **params)


def get_timer_infractions(
    year: int, player_id: int | str | None = None, **params: Any
) -> list[dict[str, Any]]:
    """Pitch Timer Infractions leaderboard.

    Do NOT pass a ``type`` param — the endpoint returns 0 rows when type is set.
    """
    params.pop("type", None)
    return fetch_leaderboard(
        "pitch-timer-infractions", year=year, player_id=player_id, **params
    )


def get_swing_take(
    year: int, player_id: int | str | None = None, **params: Any
) -> list[dict[str, Any]]:
    """Swing/Take Run Value leaderboard.

    Plain ``year=YYYY`` works. Avoid group/type/sub_type — they return 0 rows.
    """
    return fetch_leaderboard("swing-take", year=year, player_id=player_id, **params)


#####################################################################
# HTML-embedded JSON extraction
#####################################################################


def _brace_match(text: str, start_idx: int, open_char: str, close_char: str) -> str:
    """Return ``text`` from ``start_idx`` through the matching close bracket.

    Tracks string literals and escapes so brackets inside strings don't confuse
    the depth counter. ``start_idx`` must point at the opening bracket.
    """
    depth = 0
    i = start_idx
    in_str: str | None = None
    esc = False
    while i < len(text):
        c = text[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif in_str:
            if c == in_str:
                in_str = None
        elif c in ("'", '"'):
            in_str = c
        elif c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]
        i += 1
    raise SavantError(
        f"Unterminated {open_char}...{close_char} block at offset {start_idx}"
    )


def _fetch_html_json(
    url: str, var_name: str = "data", params: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any] | list[Any]:
    """Fetch an HTML page and extract an inline JSON blob assigned to a JS var.

    Savant's interactive leaderboards (park factors, hot stove, rolling windows)
    embed their table data as ``var <name> = [...]`` / ``const <name> = {...}``
    inside a ``<script>`` tag. This finds the declaration, brace-matches the
    expression, and parses it as JSON.

    Args:
        url: Full URL to fetch.
        var_name: JS variable name to extract.
        params: Optional query params.
        **kw: Forwarded to :func:`fungo.http.request_bytes`.

    Returns:
        The parsed JSON value (``dict`` or ``list``).

    Raises:
        SavantError: If the variable isn't found or the blob isn't valid JSON.
    """
    import json
    from typing import cast

    raw = http.request_bytes(url, params=params, **kw)
    html = raw.decode("utf-8", errors="replace")

    pattern = rf"(?:var|const|let)\s+{re.escape(var_name)}\s*=\s*([\[{{])"
    m = re.search(pattern, html)
    if not m:
        raise SavantError(f"Variable `{var_name}` not found in HTML at {url}")
    open_char = m.group(1)
    close_char = "]" if open_char == "[" else "}"
    blob = _brace_match(html, m.end() - 1, open_char, close_char)
    try:
        return cast("dict[str, Any] | list[Any]", json.loads(blob))
    except json.JSONDecodeError as e:
        raise SavantError(f"Failed to parse JSON for `{var_name}` at {url}: {e}") from e


#####################################################################
# HTML-backed leaderboard wrappers
#####################################################################


def get_park_factors(
    year: int,
    stat: str = "index_wOBA",
    bat_side: str = "R",
    type: str = "year",
    condition: str = "All",
) -> dict[str, Any] | list[Any]:
    """Statcast park factors (HTML-embedded JSON scrape).

    Args:
        year: Season.
        stat: e.g. ``"index_wOBA"``, ``"index_runs"``, ``"index_hardhit"``.
        bat_side: ``"R"`` or ``"L"``.
        type: ``"year"``, ``"batter"``, ``"pitcher"``, or ``"venue"``.
        condition: ``"All"``, ``"Day"``, or ``"Night"``.

    Returns:
        ``list[dict]`` — one row per venue.
    """
    url = f"{BASE_URL}/leaderboard/statcast-park-factors"
    return _fetch_html_json(
        url,
        var_name="data",
        params={
            "year": str(year),
            "type": type,
            "bat_side": bat_side,
            "condition": condition,
            "stat": stat,
        },
    )


def get_hot_stove(year: int, side: str = "batter") -> dict[str, Any] | list[Any]:
    """Hot Stove leaderboard (HTML-embedded JSON scrape).

    Args:
        year: Season.
        side: ``"batter"`` or ``"pitcher"``.

    Returns:
        ``list[dict]``.
    """
    url = f"{BASE_URL}/leaderboard/hot-stove"
    var_name = "HOT_STOVE_BATTER_DATA" if side == "batter" else "HOT_STOVE_PITCHER_DATA"
    return _fetch_html_json(url, var_name=var_name, params={"year": str(year)})


def get_rolling_windows(year: int, **params: Any) -> dict[str, Any] | list[Any]:
    """Rolling Windows leaderboard (HTML-embedded ``var rolling = {...}``).

    Returns a dict — inspect its structure before extracting.
    """
    url = f"{BASE_URL}/leaderboard/rolling"
    query = {"year": str(year)}
    query.update({k: str(v) for k, v in params.items() if v is not None})
    return _fetch_html_json(url, var_name="rolling", params=query)
