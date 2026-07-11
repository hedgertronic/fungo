# Fungo for Python <!-- omit in toc -->

Python tools for baseball data from [Statcast](https://baseballsavant.mlb.com), the [MLB Stats API](https://statsapi.mlb.com), [FanGraphs](https://www.fangraphs.com), [Baseball-Reference](https://www.baseball-reference.com), [Retrosheet](https://www.retrosheet.org), and the [Lahman Database](https://sabr.org/lahman-database/).

Fungo is a small data-access library for researchers, analysts, and developers who want raw baseball data without committing to a DataFrame stack. It carries exactly two runtime dependencies (`beautifulsoup4` and `curl_cffi`, both for Baseball-Reference); everything else is stdlib. CSV endpoints return `list[dict]` with string values, JSON endpoints return raw payloads exactly as the source produced them, and results drop straight into whatever DataFrame library you already use (`pl.DataFrame(rows)` / `pd.DataFrame(rows)`).

## Contents <!-- omit in toc -->

- [Installation](#installation)
- [Getting Started](#getting-started)
- [Statcast](#statcast)
  - [Pitch-Level Search](#pitch-level-search)
  - [Search Helpers](#search-helpers)
  - [Leaderboards](#leaderboards)
  - [Bat Tracking](#bat-tracking)
  - [HTML-Backed Leaderboards](#html-backed-leaderboards)
  - [Derived Spin Physics](#derived-spin-physics)
- [MLB Stats API](#mlb-stats-api)
  - [Low-Level API](#low-level-api)
  - [People](#people)
  - [Teams](#teams)
  - [Games And Schedule](#games-and-schedule)
  - [Stats](#stats)
  - [League And Baseball Metadata](#league-and-baseball-metadata)
  - [Miscellaneous Endpoints](#miscellaneous-endpoints)
- [FanGraphs](#fangraphs)
  - [Leaderboards](#leaderboards-1)
  - [Splits Leaderboards](#splits-leaderboards)
  - [Projections](#projections)
  - [Player Stats And Game Logs](#player-stats-and-game-logs)
  - [RosterResource](#rosterresource)
  - [Guts And Park Factors](#guts-and-park-factors)
  - [THE BOARD (Prospects)](#the-board-prospects)
  - [Access Notes](#access-notes)
- [Baseball-Reference](#baseball-reference)
  - [WAR Daily Files](#war-daily-files)
  - [Player Pages, Game Logs, And Splits](#player-pages-game-logs-and-splits)
  - [Standings, Draft, Box Scores, And The Minor-League Register](#standings-draft-box-scores-and-the-minor-league-register)
  - [Rate Limiting And Etiquette](#rate-limiting-and-etiquette)
  - [Response Caching](#response-caching)
- [Retrosheet](#retrosheet)
- [Lahman Database](#lahman-database)
- [Player ID Lookup](#player-id-lookup)
- [DataFrames](#dataframes)
- [Command Line](#command-line)

## Installation

Install the core package:

```bash
pip install fungo
```

Or with [`uv`](https://docs.astral.sh/uv/):

```bash
uv add fungo
```

Install optional extras when you need them:

```bash
uv add "fungo[progress]"    # rich progress bars on long pulls
```

For local development:

```bash
uv sync --all-extras --dev
uv run ruff check src tests
uv run pytest
```

## Getting Started

Fungo keeps each source under its own namespace:

```python
from fungo import mlb, statcast

pitches = statcast.search_pitches(
    start_date="2024-03-28",
    end_date="2024-04-03",
    player_type="pitcher",
    player_id=543037,
)

schedule = mlb.get_schedule(date="2024-07-16")
```

The library returns raw data by design:

- CSV endpoints (Statcast search/leaderboards, Baseball-Reference tables and WAR files, Retrosheet downloads, Lahman tables) return `list[dict]`; every value is a string, with `""` for empty cells.
- JSON endpoints (MLB Stats API, FanGraphs) return the raw payload exactly as the source produced it — FanGraphs values arrive as native JSON numbers.
- Wrap any tabular result in your DataFrame library of choice: `pl.DataFrame(rows)` or `pd.DataFrame(rows)`.

## Statcast

The `fungo.statcast` namespace wraps Baseball Savant search, leaderboard, and derived physics workflows.

### Pitch-Level Search

`search_pitches(...)` fetches pitch-level Baseball Savant CSV data. Ranges
longer than five days are split into one-day requests and fetched concurrently
to avoid Savant's row cap. `statcast_search(...)` is an alias.

```python
from fungo.statcast import search_pitches

# Every pitch Gerrit Cole (MLBAM 543037) threw in the first week of 2024.
pitches = search_pitches(
    start_date="2024-03-28",
    end_date="2024-04-03",
    player_type="pitcher",
    player_id=543037,
)

print(len(pitches), pitches[0]["pitch_type"], pitches[0]["release_speed"])
```

Important options:

- `player_type`: `"pitcher"` or `"batter"`.
- `player_id`: MLBAM player ID.
- `team`: team abbreviation/name, resolved through Fungo constants.
- `home_road`: home/away filter for team searches.
- `level`: `"mlb"` or `"milb"`.
- arbitrary Savant filters such as `hfPT`, `hfBBT`, `hfGT`, or `game_date_gt`.

Savant itself documents only the *output* columns; the complete input-param
vocabulary (every `hf*` filter with its accepted values, the `metric_N`
columns, serialization rules) is cataloged in
[docs/savant-search-params.md](docs/savant-search-params.md).

Multi-value filters use Baseball Savant's pipe convention:

```python
fastballs_sliders = search_pitches(
    start_date="2024-04-01",
    end_date="2024-04-30",
    player_id=543037,
    hfPT="FF|SL|",
)
```

### Search Helpers

Convenience helpers build common Statcast search filters:

- `search_game(game_pk, level="mlb", **filters)`: all pitches for one MLB or MiLB game.
- `search_matchup(pitcher_id=..., batter_id=..., start_date=..., end_date=...)`: pitcher/batter matchups.
- `search_team(team, start_date=..., end_date=..., home_road=None, level="mlb")`: team-filtered searches.
- `get_pitcher_arsenal(player_id, start_date, end_date, level="mlb")`: aggregated pitch arsenal rows.
- `aggregate_pitcher_arsenal(rows)`: aggregate already-fetched pitch rows.

```python
from fungo.statcast import get_pitcher_arsenal, search_game

game = search_game(game_pk=747220)
arsenal = get_pitcher_arsenal(543037, "2024-04-01", "2024-04-30")
```

### Leaderboards

Fungo includes a registry of Baseball Savant leaderboards with typed wrappers plus a generic fetcher.

Discovery:

- `list_leaderboards(category=None)`: list registered leaderboard slugs.
- `describe_leaderboard(slug)`: inspect category, params, year behavior, key columns, and notes.
- `get_leaderboard(slug, **params)`: generic, registry-checked fetcher.

Common typed wrappers include:

- Batting: `get_expected_statistics`, `get_exit_velocity_barrels`, `get_batted_ball`, `get_home_runs`, `get_percentile_rankings`, `get_custom_leaderboard`.
- Pitching: `get_pitch_arsenals`, `get_pitch_arsenal_stats`, `get_pitch_movement`, `get_spin_direction`, `get_active_spin`, `get_pitch_tempo`, `get_game_scores`.
- Fielding: `get_outs_above_average`, `get_directional_oaa`, `get_fielding_run_value`, `get_arm_strength`, `get_arm_angles`, `get_catch_probability`, `get_outfield_jump`.
- Catching: `get_catcher_framing`, `get_catcher_throwing`, `get_catcher_blocking`, `get_catcher_stance`, `get_poptime`.
- Running: `get_sprint_speed`, `get_running_splits`, `get_baserunning`, `get_baserunning_run_value`, `get_basestealing_run_value`, `get_pitcher_running_game`.
- Other: `get_year_to_year`, `get_abs_challenges`, `get_timer_infractions`, `get_swing_take`.

```python
from fungo.statcast import (
    get_expected_statistics,
    get_leaderboard,
    get_percentile_rankings,
    list_leaderboards,
)

xstats = get_expected_statistics(year=2024, type="batter", min_pa=300)
trout_pctl = get_percentile_rankings(player_type="batter", player_id=545361)
framing = get_leaderboard("catcher-framing", year=2024)

print(list_leaderboards(category="catching"))
```

### Bat Tracking

The Hawk-Eye bat-tracking boards take season parameters that differ from every other Baseball Savant board. The wrappers emit the correct form for each:

- `get_bat_tracking`
- `get_swing_path_attack_angle`
- `get_swing_timing_miss_distance`

```python
from fungo.statcast import get_bat_tracking, get_swing_timing_miss_distance

# seasonStart/seasonEnd range: one aggregated row per player over the span.
combined = get_bat_tracking(season=(2023, 2024), type="batter", min_swings=100)

# season[] array: one row per player per selected season.
per_year = get_swing_timing_miss_distance(season=[2023, 2024], type="batter")
```

### HTML-Backed Leaderboards

Some Baseball Savant pages do not expose CSV. Fungo parses their inline JSON:

- `get_park_factors`
- `get_hot_stove`
- `get_rolling_windows`

### Derived Spin Physics

`add_spin_columns(...)` adds Alan Nathan-style derived spin physics columns to Statcast pitch rows fetched by search.

```python
from fungo.statcast import add_spin_columns, axis_to_clock

enriched = add_spin_columns(pitches)
clock = axis_to_clock(225)
```

Derived columns include induced/Magnus movement estimates, transverse
acceleration, spin efficiency, inferred spin components, and clock-face tilt
where inputs are available.

## MLB Stats API

The `fungo.mlb` namespace is a pass-through wrapper for `statsapi.mlb.com`.
Every function returns raw JSON and accepts the most common endpoint parameters.
For unsupported or less common routes, use `mlb_api(path, params)`.

### Low-Level API

```python
from fungo import mlb

raw = mlb.mlb_api("/api/v1/teams", {"sportId": 1})
```

### People

Player/person endpoints:

- `get_people(person_ids, hydrate=None, fields=None)`
- `get_person(person_id, hydrate=None, fields=None)`
- `search_players(names=None, person_ids=None, active=None, current_team_id=None, sport_id=None)`
- `search_player_matches(name, sport_id=1)`
- `resolve_player_id(name, sport_id=1)`
- `get_player_changes(...)`
- `get_free_agents(season, order=None)`
- `get_player_stats_all_sports(person_id, season, groups=..., stat_types=..., sport_ids=...)`

```python
person = mlb.get_person(545361)
matches = mlb.search_player_matches("Mike Trout")
```

### Teams

Team directory, roster, team stats, and team-specific endpoints:

- `get_teams`, `get_team`, `get_team_history`
- `get_team_stats`, `get_team_leaders`
- `get_team_affiliates`, `get_roster`
- `get_team_specific_leaders`, `get_team_specific_stats`, `get_team_alumni`
- `resolve_team_id`

```python
teams = mlb.get_teams(sport_id=1)
roster = mlb.get_roster(team_id=108)
```

### Games And Schedule

Schedule, live game feed, per-game views, and postseason helpers:

- `get_schedule`
- `get_gamefeed`, `get_gamefeed_diffpatch`, `get_gamefeed_timestamps`
- `get_boxscore`, `get_linescore`, `get_playbyplay`, `get_game_content`
- `get_context_metrics`, `get_win_probability`
- `get_color_feed`, `get_color_diffpatch`, `get_color_timestamps`
- `get_game_changes`
- `get_postseason_schedule`, `get_postseason_series`, `get_tied_games`

```python
schedule = mlb.get_schedule(date="2024-07-16")
feed = mlb.get_gamefeed(game_pk=747220)
box = mlb.get_boxscore(game_pk=747220)
```

### Stats

League/player/team stats helpers:

- `build_stats_hydrate`
- `get_stats`
- `get_stat_leaders`
- `get_streaks`

```python
leaders = mlb.get_stat_leaders(leader_categories="homeRuns", season=2024)
stats = mlb.get_stats(stats="season", group="hitting", season=2024)
```

### League And Baseball Metadata

Discovery endpoints return valid parameter values and metadata used by the other wrappers. `get_hydrations(path)` asks an endpoint which `hydrate=` values it accepts — the Stats API self-documents via `hydrate=hydrations` — and the hydration syntax itself (nesting, brackets, the `stats(...)` form) is covered in [docs/mlb-hydrations.md](docs/mlb-hydrations.md):

```python
mlb.get_hydrations("/api/v1/people/545361")   # ['awards', 'currentTeam', ...]
```

The full discovery set:

- Stat/game metadata: `get_stat_types`, `get_stat_groups`, `get_game_types`, `get_game_status`, `get_baseball_stats`, `get_metrics`
- Field/game descriptors: `get_positions`, `get_situation_codes`, `get_pitch_types`, `get_hit_trajectories`, `get_event_types`, `get_schedule_event_types`
- Environment/job/platform descriptors: `get_wind_direction`, `get_sky`, `get_job_types`, `get_languages`, `get_platforms`
- Organization descriptors: `get_league_leader_types`, `get_sports_discovery`, `get_roster_types`, `get_standings_types`

```python
pitch_types = mlb.get_pitch_types()
positions = mlb.get_positions()
```

### Miscellaneous Endpoints

Other Stats API wrappers include:

- Draft/prospects/awards: `get_draft`, `get_draft_prospects`, `get_award_recipients`
- Transactions/standings/attendance: `get_transactions`, `get_standings`, `get_attendance`
- Venues/leagues/divisions/seasons/sports: `get_venues`, `get_venue`, `get_leagues`, `get_league`, `get_divisions`, `get_seasons`, `get_season`, `get_sports`, `get_sport`, `get_sport_players`
- Jobs/broadcasts/conferences: `get_umpires`, `get_official_scorers`, `get_datacasters`, `get_broadcasts`, `get_conferences`
- Specialty endpoints: `get_high_low`, `get_home_run_derby`, `get_derby_bracket`, `get_derby_pool`, `get_game_pace`, `get_uniforms_game`, `get_uniforms_team`

```python
transactions = mlb.get_transactions(start_date="2024-07-01", end_date="2024-07-31")
venues = mlb.get_venues()
```

## FanGraphs

The `fungo.fangraphs` namespace wraps FanGraphs' JSON API — leaderboards, player stats and game logs, RosterResource depth charts, Guts! constants, and THE BOARD. Values arrive as native JSON numbers, and rows carry both `playerid` (FanGraphs) and `xMLBAMID` (MLBAM), so results join directly to Statcast data.

### Leaderboards

One endpoint serves batting, pitching, and fielding boards (and the minor leagues via `league="minor"`). The full pitching board is ~540 columns per row, including the Stuff+ family (`sp_stuff`, `sp_location`, `sp_pitching`, per-pitch grades like `sp_s_FF`) and the PitchingBot family (`pb_stuff`, `pb_command`, `pb_overall`, `pb_xRV100`). None of it requires a membership.

```python
from fungo import fangraphs

# 2025 qualified batting leaders (Dashboard columns), sorted by WAR.
rows = fangraphs.get_leaders("bat", 2025)

# Pitching leaders with Stuff+ / PitchingBot columns.
pitchers = fangraphs.get_leaders("pit", 2025, qual=50)

# Multi-year span, one row per player per season.
span = fangraphs.get_leaders("bat", 2023, 2025, ind=1)

# Handedness splits (narrower column set).
vs_lhp = fangraphs.get_splits("bat", 2025, "vs_lhp")
```

Param traps handled for you: FanGraphs' `season` param is the *end* year and `season1` the *start* (the wrappers take `start_season`/`end_season`); `month=13/14` are the vs-LHP/vs-RHP split codes; `qual="y"` means qualified only.

### Splits Leaderboards

The full Splits Leaderboards page (a POST-only API, distinct from the `month=13/14` splits above) composes arbitrary split filters with date ranges, stat groups, and qualifier filters:

```python
rows = fangraphs.get_split_leaders(
    "B", 2025, ["vs_lhp"],
    filters=[{"stat": "PA", "comp": "gt", "low": "100", "high": -99,
              "auto": False, "pending": True, "label": "PA >= 100", "value": 0}],
)
```

Named splits include handedness (`vs_lhp`, `vs_rhp`, `vs_lhh`, `vs_rhh`), base states (`risp`, `bases_empty`, `runners_on`, `bases_loaded`), leverage (`high_leverage`, `medium_leverage`, `low_leverage`), calendar (`march_april` through `sept_oct`, `day`, `night`, `first_half`, `second_half`), batted-ball type (`grounders`, `flyballs`, `line_drives`, `pull`, `center`, `oppo`), and more -- see `SPLIT_CODES`. The full 292-code registry is in `SPLIT_CODE_TABLE` (code integer to human label). Home/away are position-dependent: `"home"` resolves to code 7 for batters and 9 for pitchers automatically. Raw integer codes work too, and multiple splits combine.

The `pitch_splits` keyword filters by pitch type or count (`"fourseam"`, `"slider"`, `"count_3_2"`, etc. -- see `PITCH_SPLIT_CODES`; full 47-code table in `PITCH_SPLIT_CODE_TABLE`):

### Projections

ZiPS, Steamer, ATC, THE BAT/X, OOPSY, and Depth Charts, as one call each — typed values, the FanGraphs/MLBAM id crosswalk, and (Steamer only) uncertainty quantiles:

```python
proj = fangraphs.get_projections("steamer", "bat")   # 4,000+ players
zips = fangraphs.get_projections("zips", "pit")
```

Rest-of-season variants use the `r`-prefixed slugs in `ROS_PROJECTION_SYSTEMS` (community-reported; Steamer's is irregularly `steamerr`).

### Player Stats And Game Logs

```python
info = fangraphs.get_player_stats(15640, "OF")   # Aaron Judge
logs = fangraphs.get_game_log(15640, 2025)       # game log; rows under "mlb"
```

The stats payload's `data` rows mix record kinds, discriminated by `type`: `0` = MLB regular season, `900` = playoff/split, `1000` = league average, negative values = projection systems (ZiPS, Steamer, ATC, THE BAT).

### RosterResource

RosterResource pages have no public API route; fungo extracts the JSON payload embedded in the server-rendered page. One call returns everything the depth chart shows:

```python
chart = fangraphs.get_depth_chart("rangers")
chart["dataRoster"]              # full roster with roles
chart["dataProbableStarters"]    # probable starters
chart["dataRecentTransactions"]  # transaction log
```

### Guts And Park Factors

The one HTML-backed corner of FanGraphs — small, stable tables whose values are all strings:

```python
constants = fangraphs.get_guts_constants()             # wOBA weights, cFIP, run env
pf = fangraphs.get_park_factors(2025)
pfh = fangraphs.get_park_factors_by_handedness(2025)
```

### THE BOARD (Prospects)

```python
board = fangraphs.get_prospect_board(2026)   # ~1,300 prospects: FV, risk, tool grades
```

### Access Notes

FanGraphs fronts its site with Cloudflare, which blocks generic HTTP clients; fungo rides the one known exemption (the FanGraphs mobile app's `okhttp` User-Agent). If FanGraphs withdraws that exemption, calls fail loudly with `FangraphsError` explaining the condition. FanGraphs states automated access is "not supported" — endpoints can change without notice. Be polite: fetch what you need, cache locally, and don't loop over the league.

## Baseball-Reference

The `fungo.bbref` namespace provides polite, on-demand, single-page fetchers. Sports Reference tolerates rate-limited automated access but prohibits bulk harvesting; every request routes through a process-wide rate limiter (~9 requests/minute, under both their stated 20/min ceiling and the community-tested 10/min practical limit), and a 403/429 raises `BBRefError` with jail guidance instead of retrying.

### WAR Daily Files

Plain CSV flat files with bWAR and its full component breakdown for every player season in history — the one B-R endpoint that needs no HTML parsing:

```python
from fungo import bbref

war = bbref.get_war_daily_batting()    # ~126k rows, all of MLB history
```

### Player Pages, Game Logs, And Splits

One page fetch extracts *every* table on the page at once — including the ones B-R defers inside HTML comments — so a single request yields standard/advanced/value batting, fielding, appearances, salaries, and postseason tables together:

```python
from fungo import bbref, lookup

bbref_id = lookup.mlbam_to_bbref(545361)      # "troutmi01"

tables = bbref.get_player(bbref_id)           # dict: table id -> rows
tables["players_standard_batting"]
tables["br-salaries"]

logs = bbref.get_game_log(bbref_id, 2024)     # gl.fcgi, all tables
splits = bbref.get_splits(bbref_id, 2024)     # split.fcgi ("Career" default)
sched = bbref.get_team_schedule("NYY", 2024)
```

Cells are keyed by B-R's stable `data-stat` attributes; all values are strings.

### Standings, Draft, Box Scores, And The Minor-League Register

```python
standings = bbref.get_standings(2024)
standings["standings_E"]      # AL East (duplicate-id pages: AL first...)
standings["standings_E_2"]    # ...NL East suffixed
standings["expanded_standings_overall"]   # all 30 teams (only table pre-1969)

picks = bbref.get_draft(2022, 1)                    # one round of the draft
tbr = bbref.get_draft_by_team("TBD", 2011)          # historical franchise codes: ANA/FLA/TBD

day = bbref.get_daily("2024-06-15")                 # scoreboard: box-score links + 16 standings tables
box = bbref.get_box_score("NYY", "2024-10-30")      # franchise code auto-mapped to NYA
box["linescore"]; box["play_by_play"]

minors_id = lookup.lookup(mlbam=683953)[0]["key_bbref_minors"]
reg = bbref.get_register_player(minors_id)          # season-by-season MiLB stats by level
```

Box-score URLs use Retrosheet-style home codes (`NYA`, `SLN`, `CHN`, ...) — `get_box_score` maps modern franchise codes automatically (`BOX_SCORE_TEAM_CODES`). Register ids are the Chadwick `key_bbref_minors` values; never construct them from names (the format's sequence numbers are inconsistent).

### Rate Limiting And Etiquette

The limiter cannot be loosened past its safe default, and this namespace has no concurrent-fetch helpers — every request runs sequentially through the limiter. Fetch single pages on demand, cache what you fetch, and use the WAR files / Retrosheet / Lahman / Chadwick for anything bulk. If you get a 403/429, stop — Sports Reference's rate-limit jail can last a day, and retrying extends it.

### Response Caching

An opt-in local cache avoids re-fetching pages you already have. A cache hit skips the rate limiter entirely — no delay, no budget spent:

```python
from fungo import bbref

# Enable once at the top of your script. Historical pages are immutable,
# so no TTL is needed. Pass ttl=<seconds> for current-season pages
# (standings, daily scoreboards) that change as the season progresses.
bbref.enable_cache()

# Repeat calls for the same URL are free — served from disk.
tables = bbref.get_player("troutmi01")
tables_again = bbref.get_player("troutmi01")  # no network request

# Remove cached files (e.g. to force a refresh).
bbref.clear_cache()
```

Cache files land in `~/.cache/fungo/bbref_cache/` (or `$XDG_CACHE_HOME/fungo/bbref_cache/`). Pass `path=` to `enable_cache` for a custom location.

## Retrosheet

The `fungo.retrosheet` namespace downloads Retrosheet's published data files — parsed play-by-play, game logs, schedules, per-game stats, and the biofile. Retrosheet is a static file host refreshed in roughly twice-yearly bulk releases, so each dataset downloads once into the user cache dir (`fungo/retrosheet/`) and is served from disk afterward; `refresh(dataset, year)` re-downloads and `clear_cache()` wipes.

```python
from fungo import retrosheet

plays = retrosheet.get_plays(2024)       # parsed play-by-play (1903+), 177 columns
logs = retrosheet.get_game_logs(2024)    # one row per game (1871+), 161 fields
sked = retrosheet.get_schedule(2026)     # full season schedule (1877+)
bio = retrosheet.get_biofile()           # players/managers/umpires with Retrosheet IDs
info = retrosheet.get_gameinfo(2024)     # per-game metadata: weather, umpires, attendance
```

The per-season accessors — `get_gameinfo`, `get_batting`, `get_pitching`, `get_fielding`, `get_teamstats`, `get_allplayers` — share one `{year}csvs.zip` download (1903+). `get_coaches()` and `get_relatives()` ride the biofile download. The parsed CSVs make Retrosheet's raw event files (and the Chadwick `cwevent`/`cwgame` tools) unnecessary for most uses.

Game logs are headerless and the schedule header carries colliding names, so rows for both are keyed by the `GAME_LOG_FIELDS` (161 names, from Retrosheet's `glfields.txt`) and `SCHEDULE_FIELDS` constants. All values are strings.

Retrosheet's data is free for any use, with one licensing condition — prominent display of this notice:

> The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".

## Lahman Database

The `fungo.lahman` namespace fetches the SABR-hosted Lahman Database CSVs — season-level batting/pitching/fielding, biographical data, teams, awards, salaries, and more, 1871 through the most recent complete season (CC BY-SA 3.0; annual releases). Tables cache under `fungo/lahman/`, and a cache hit makes no network requests until `refresh()`.

```python
from fungo import lahman

lahman.list_tables()                 # 27 tables: People, Batting, Teams, Parks, ...
batting = lahman.get_table("Batting")
people = lahman.get_people()         # shortcuts: People/Batting/Pitching/Fielding/Teams
```

Access rides an undocumented seam: SABR hosts the files as Box shared links that change with each annual release, so fungo discovers the current links at runtime by parsing the SABR page and the (paginated) Box folder listing. If either page's structure changes, calls fail loudly with `LahmanError` naming the failed step — re-verify against [sabr.org/lahman-database](https://sabr.org/lahman-database/) rather than retrying.

## Player ID Lookup

`fungo.lookup` provides player ID cross-reference helpers backed by the Chadwick Bureau register. The register is fetched on demand and cached under your user cache directory (`$XDG_CACHE_HOME` or `~/.cache`, then `fungo/chadwick_people.csv`).

```python
from fungo import lookup

lookup.lookup(name="Trout")
lookup.mlbam_to_fangraphs(545361)
lookup.mlbam_to_bbref(545361)
lookup.fangraphs_to_mlbam(15640)
lookup.bbref_to_mlbam("troutmi01")
lookup.xref_ids(545361)              # MLB Stats API cross-reference map
lookup.refresh()
```

The register updates monthly in-season, and its FanGraphs IDs lag roughly a full season for recent debutants. `mlbam_to_fangraphs` and `mlbam_to_bbref` therefore fall back to a single MLB Stats API `xrefId` call when the register value is blank or missing — that source carries FanGraphs IDs within days of a debut. Pass `live_fallback=False` for fully offline lookups. A cached register older than 35 days triggers a `StaleCacheWarning` recommending `refresh()`.

## DataFrames

The core returns raw rows — wrap them in whatever DataFrame library you already use. Both `polars` and `pandas` accept `list[dict]` directly:

```python
import polars as pl  # or: import pandas as pd
from fungo.statcast import get_expected_statistics

rows = get_expected_statistics(year=2024, type="batter", min_pa=300)
df = pl.DataFrame(rows)   # or: pd.DataFrame(rows)
```

## Command Line

The `fungo` console script exposes eight subcommands. `--format` defaults to `json` for `mlb`, `fangraphs`, and `bbref`, and `csv` for everything else. `-o/--output` writes to a file instead of stdout.

```bash
# Player ID lookup
fungo lookup --name "Gerrit Cole"

# Pitch-level Statcast search
fungo search --start 2024-04-01 --end 2024-04-07 --player-id 543037 --hfPT=FF,SL

# Leaderboards
fungo leaderboard --list --category pitching
fungo leaderboard catcher-framing --season 2024
fungo leaderboard bat-tracking/swing-timing-miss-distance --season 2023,2024

# MLB Stats API
fungo mlb get_schedule --date=2024-07-16
fungo mlb --list

# FanGraphs
fungo fangraphs get_leaders --stats=pit --start-season=2025
fungo fangraphs --list

# Baseball-Reference (rate-limited)
fungo bbref get_player --bbref-id=troutmi01
fungo bbref --list

# Retrosheet
fungo retrosheet get_game_logs --year=2024
fungo retrosheet --list

# Lahman database
fungo lahman get_table --name=Batting
fungo lahman --list
```

`search`, `leaderboard`, `mlb`, `fangraphs`, `bbref`, `retrosheet`, and `lahman` accept arbitrary `--field=value` passthrough arguments. Only `search` pipe-joins comma-separated values for Baseball Savant filters.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.
