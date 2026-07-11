"""Positional field names for Retrosheet files that need them.

``GAME_LOG_FIELDS`` names the 161 positional columns of the headerless
``gl{year}.txt`` game-log files. Names and ordering follow Retrosheet's field
guide at https://www.retrosheet.org/gamelogs/glfields.txt (fields 1-161).

``SCHEDULE_FIELDS`` names the 13 columns of the ``{year}schedule.csv``
schedule files. The source file carries a header row, but its column names
collide (``League`` and ``Game`` each appear twice — once for the visitor,
once for the home team), so fungo drops that row and keys schedule rows by
these disambiguated names instead.
"""

from __future__ import annotations

#####################################################################
# Game logs (gl{year}.txt) — glfields.txt fields 1-161
#####################################################################

# Per-team statistics, one block per team (visiting = fields 22-49,
# home = fields 50-77): 17 offense, 5 pitching, 6 defense.
_TEAM_STATS: tuple[str, ...] = (
    # Offense (glfields.txt 22-38 / 50-66).
    "at_bats",
    "hits",
    "doubles",
    "triples",
    "homeruns",
    "rbi",
    "sacrifice_hits",
    "sacrifice_flies",
    "hit_by_pitch",
    "walks",
    "intentional_walks",
    "strikeouts",
    "stolen_bases",
    "caught_stealing",
    "grounded_into_double_plays",
    "catcher_interference",
    "left_on_base",
    # Pitching (glfields.txt 39-43 / 67-71).
    "pitchers_used",
    "individual_earned_runs",
    "team_earned_runs",
    "wild_pitches",
    "balks",
    # Defense (glfields.txt 44-49 / 72-77).
    "putouts",
    "assists",
    "errors",
    "passed_balls",
    "double_plays",
    "triple_plays",
)

# Umpire positions in file order (glfields.txt 78-89), id + name each.
_UMPIRE_POSITIONS: tuple[str, ...] = (
    "home_plate",
    "first_base",
    "second_base",
    "third_base",
    "left_field",
    "right_field",
)

GAME_LOG_FIELDS: tuple[str, ...] = (
    # glfields.txt 1-21.
    "date",
    "game_number",
    "day_of_week",
    "visiting_team",
    "visiting_league",
    "visiting_team_game_number",
    "home_team",
    "home_league",
    "home_team_game_number",
    "visiting_score",
    "home_score",
    "game_length_outs",
    "day_night",
    "completion_info",
    "forfeit_info",
    "protest_info",
    "park_id",
    "attendance",
    "game_length_minutes",
    "visiting_line_score",
    "home_line_score",
    # glfields.txt 22-49 / 50-77.
    *(f"visiting_{stat}" for stat in _TEAM_STATS),
    *(f"home_{stat}" for stat in _TEAM_STATS),
    # glfields.txt 78-89.
    *(
        f"{position}_umpire_{part}"
        for position in _UMPIRE_POSITIONS
        for part in ("id", "name")
    ),
    # glfields.txt 90-105.
    "visiting_manager_id",
    "visiting_manager_name",
    "home_manager_id",
    "home_manager_name",
    "winning_pitcher_id",
    "winning_pitcher_name",
    "losing_pitcher_id",
    "losing_pitcher_name",
    "saving_pitcher_id",
    "saving_pitcher_name",
    "game_winning_rbi_batter_id",
    "game_winning_rbi_batter_name",
    "visiting_starting_pitcher_id",
    "visiting_starting_pitcher_name",
    "home_starting_pitcher_id",
    "home_starting_pitcher_name",
    # glfields.txt 106-132 / 133-159: starters 1-9 in batting order,
    # (id, name, defensive position) each.
    *(
        f"visiting_starter_{slot}_{part}"
        for slot in range(1, 10)
        for part in ("id", "name", "position")
    ),
    *(
        f"home_starter_{slot}_{part}"
        for slot in range(1, 10)
        for part in ("id", "name", "position")
    ),
    # glfields.txt 160-161.
    "additional_info",
    "acquisition_info",
)


#####################################################################
# Schedules ({year}schedule.csv)
#####################################################################

# Source header: Date,Num,Day,Visitor,League,Game,Home,League,Game,
# Day/Night,Location,Postponed,Makeup. ``Location`` holds a Retrosheet
# park id (e.g. "SFO03"), hence ``park_id`` here; team/league/game-number
# names match the game-log field names.
SCHEDULE_FIELDS: tuple[str, ...] = (
    "date",
    "game_number",
    "day_of_week",
    "visiting_team",
    "visiting_league",
    "visiting_team_game_number",
    "home_team",
    "home_league",
    "home_team_game_number",
    "day_night",
    "park_id",
    "postponed",
    "makeup",
)
