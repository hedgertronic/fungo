# Baseball Savant Statcast search — input parameter reference

**Provenance**: extracted from the `statcast-search-new` JS bundle (build
`c8488670`, fetched 2026-07-11). Savant documents only the *output* columns
(the csv-docs page); no official input-parameter documentation exists.

**Regeneration**: fetch `baseballsavant.mlb.com/statcast_search` once, follow
its `index.bundle.js` script tag to `builds.mlbstatic.com`, and grep the
bundle for the filter registry array (objects of shape
`{name, shortId, description, values}`); the query parameter name is `hf` +
`shortId`. The scalar params are the remaining named form controls on the
page.

## Serialization rules

1. **Multi-value `hf*` params are pipe-joined WITH a trailing pipe**:
   `hfPT=FF|SL|`. The pipes must not be URL-encoded (fungo's
   `request_bytes` uses `safe="|"` for this).
2. **Literal dots in values are backslash-escaped on the wire**: the registry
   value `ground..ball` is sent as `ground\.\.ball`
   (`hfBBT=ground\.\.ball|`).
3. **`hfFlag` / `hfABSFlag` values are negatable** by appending `\.\.not`:
   exclude bunts = `hfFlag=is\.\.bunt\.\.not|`. Unlike the other selectors,
   flag filters must **all** be satisfied (AND, not OR).

## CSV export skeleton

```
/statcast_search/csv?{query}&all=true&type=details&minors={true|false}&wbc={true|false}
```

Per-player export replaces `all=true` with `player_id={MLBAM}`.

## Multi-select `hf*` filters

| Param | Meaning | Values |
|---|---|---|
| `hfPT` | Pitch type | `FF` 4-Seam, `SI` Sinker, `FC` Cutter, `CH` Changeup, `FS` Split-finger, `FO` Forkball, `SC` Screwball, `CU` Curveball, `KC` Knuckle Curve, `CS` Slow Curve, `SL` Slider, `ST` Sweeper, `SV` Slurve, `KN` Knuckleball, `EP` Eephus, `FA` Other, `IN` Intentional Ball, `PO` Pitchout |
| `hfPTM` | Pitch type (merged groups) | Same codes as `hfPT`; populated by the UI's grouped selector (`pitch_types_merged` in shareable URLs) |
| `hfPR` | Pitch result | `ball`, `blocked..ball` (ball in dirt), `called..strike`, `foul`, `foul..bunt`, `bunt..foul..tip`, `foul..pitchout`, `pitchout`, `hit..by..pitch`, `intent..ball`, `hit..into..play`, `missed..bunt`, `foul..tip`, `swinging..pitchout`, `swinging..strike`, `swinging..strike..blocked` |
| `hfAB` | PA result | `single`, `double`, `triple`, `home..run`, `field..out`, `strikeout`, `strikeout..double..play`, `walk`, `double..play`, `field..error`, `grounded..into..double..play`, `fielders..choice`, `fielders..choice..out`, `batter..interference`, `catcher..interf`, `force..out`, `hit..by..pitch`, `intent..walk`, `sac..bunt`, `sac..bunt..double..play`, `sac..fly`, `sac..fly..double..play`, `triple..play` |
| `hfBBL` | Batted ball location (fielder) | `1` P, `2` C, `3` 1B, `4` 2B, `5` 3B, `6` SS, `7` LF, `8` CF, `9` RF |
| `hfBBT` | Batted ball type | `fly..ball`, `popup`, `line..drive`, `ground..ball` |
| `hfC` | Count | `00` `01` `02` `10` `11` `12` `20` `21` `22` `30` `31` `32`, `ahead` (hitter ahead), `even`, `behind` (hitter behind), `2strikes`, `3balls` |
| `hfZ` | Gameday zone | `1`–`9` (in zone), `11`–`14` (out of zone) |
| `hfNewZones` | Attack zone | Heart `1`–`9`; Shadow `11`–`14`, `16`–`19`; Chase `21`–`24`, `26`–`29`; Waste `31`–`34`, `36`–`39` |
| `hfGT` | Season/game type | Majors: `R` regular, `PO` postseason (all), `F` wildcard, `D` division series, `L` LCS, `W` World Series, `S` spring training, `A` All-Star. Minors: `R`, `PO`. WBC: `F` pool play, `D` quarterfinals, `L` semifinals, `W` championship |
| `hfSea` | Season (year) | `2008`–present for majors (pitch tracking 2008+, Statcast proper 2015+); minors `2021`+; WBC `2023`, `2026` |
| `hfMo` | Month | `4` Mar/Apr, `5` May, `6` Jun, `7` Jul, `8` Aug, `9` Sep/Oct; majors also `1st` and `2nd` (season halves — months and halves cannot be combined) |
| `hfTeam` | Team | MLBAM numeric team ids in the current UI (`147` Yankees, `119` Dodgers, ...), plus `AmericanL` / `NationalL`. Legacy 3-letter codes may still be accepted (unverified). WBC pages use country ids (`843` Japan, ...) |
| `hfOpponent` | Opponent | Same value space as `hfTeam` |
| `hfStadium` | Venue | MLBAM venue ids (`3313` Yankee Stadium, `22` Dodger Stadium, `2392` Daikin Park, ...) — includes historical venues (`10` Oakland Coliseum) |
| `hfInn` | Inning | `1`–`9`, `10` = extra innings |
| `hfOuts` | Outs (pre-pitch) | `0`, `1`, `2` |
| `hfEventOuts` | Outs recorded on play | `0`–`3` |
| `hfEventRuns` | Runs scored on play | `0`–`4` |
| `hfRO` | Runner on | `0` none, `5` RISP, `4` any on base, `1`/`2`/`3` runner on 1st/2nd/3rd, `6`/`7`/`8` runner NOT on 1st/2nd/3rd (only-1st = `1` + `7` + `8`) |
| `hfSit` | Game situation | `Go..Ahead.run.at.plate`, `Go..Ahead.run.on.base`, `Tying.run.at.plate`, `Tying.run.on.base`, `Tying.run.on.deck` |
| `hfSA` | Speed & angle (contact quality) | `6` Barrel, `5` Solid Contact, `4` Flare/Burner, `3` Poorly/Under, `2` Poorly/Topped, `1` Poorly/Weak |
| `hfPull` | Batted ball direction | `Pull`, `Straightaway`, `Opposite` |
| `hfLS` | Launch spin | `BackSpin`, `LeftBackSpin`, `LeftSpin`, `LeftTopSpin`, `RightBackSpin`, `RightSpin`, `RightTopSpin`, `TopSpin` |
| `hfSN` | Speed needed (catch difficulty) | `0..Gimme`, `1..Easy`, `2..Routine`, `3..Fifty50`, `4..Tough`, `5..Highlight`, `6..Impossible` |
| `hfInfield` | Infield alignment | `1` Standard, `2` Strategic, `3` Shift, `4` Shade |
| `hfOutfield` | Outfield alignment | `1` Standard, `2` Strategic, `3` = 3 OF to one side of 2B, `4` = 4th outfielder |
| `hfPos` | Fielder positioning | `1B-2B.hole`, `2B.spot`, `2B-P.hole`, `Back`, `CF.rover`, `CF.spot`, `Deep`, `Gap`, `Guarding.Line`, `Hole`, `In`, `Infield`, `LF.Gap`, `LF.spot`, `Left.side`, `Line`, `Middle.to.Left`, `Middle.to.Right`, `RF.Gap`, `RF.rover`, `RF.spot`, `Right.side`, `Rover`, `SS.spot`, `SS-P.hole`, `Standard`, `Standard.Back`, `Standard.Holding.Runner`, `Standard.In`, `Standard.Left`, `Standard.Right` |
| `hfFlag` | Flags (all must hold; negatable) | see flag table below |
| `hfABSFlag` | ABS challenge flags (negatable) | see flag table below |
| `hfLevel` | Level (minors search only) | Level codes from the minors page's `levels` variable |
| `hfTeamAffiliate` | Team affiliate (minors only) | MLBAM affiliate ids from the minors page |
| `hfOpponentAffiliate` | Opponent affiliate (minors only) | MLBAM affiliate ids from the minors page |

### `hfFlag` values (majors)

`is..swing`, `is..take`, `is..pa`, `is..tracked` (tracked pitch),
`is..hit..into..play` (batted ball), `is..putout`,
`is..hit..into..play..basehit` (base hit),
`is..hit..into..play..basehit..home..run..insidepark` (inside-the-park HR),
`is..hit..into..play..hardhit` (hard hit), `is..bunt`, `is..lastpitch`,
`is..launch..angle..sweetspot` (sweet spot), `is..nonpitcher..pitcher`
(position player pitching), `is..starter..batter` (starting position
player), `is..rookie..bat`, `is..rookie..pit`, `is..runner..pb` (passed
ball), `is..runner..wp` (wild pitch), `is..runner..pbwp`,
`is..bestspeed..batter` (EV50 batter), `is..bestspeed..pitcher` (EV50
pitcher), `is..competitive` (competitive swing), `is..swing..sword`
(sword), `is..squaredup..with..speed` (blast), `is..sweetspot`
(squared-up), `is..ideal..attack..angle`, `is..runner..sba` (steal
attempt), `is..runner..sb` (stolen base), `is..runner..cs` (caught
stealing), `is..runner..cs2`, `is..runner..sb2`, `is..runner..cs3`,
`is..runner..sb3`, `is..runner..cs4`, `is..runner..sb4` (per-base SB/CS).

Minors pages drop the rookie/EV50/bat-tracking flags and add the ABS
challenge flags inline. Swing/take filtering is done here:
`hfFlag=is..swing` / `is..take` — there is no separate swing param.

### `hfABSFlag` values

`is..challengeabs..review` (is challenge), `is..challengeabs..overturned`,
`is..challengeabs..lost` (confirmed), `is..challengeabs..opp`
(challengeable pitch), `is..challengeabs..review..bat` (by batter),
`is..challengeabs..review..pit` (by pitcher),
`is..challengeabs..review..cat` (by catcher),
`is..challengeabs..review..fld` (by fielder).

## Scalar params

| Param | Meaning | Values |
|---|---|---|
| `player_type` | Perspective of the returned rows | `pitcher`, `batter`, `fielder_2` (C), `fielder_3` (1B), `fielder_4` (2B), `fielder_5` (3B), `fielder_6` (SS), `fielder_7` (LF), `fielder_8` (CF), `fielder_9` (RF) |
| `game_date_gt` | Game date >= | `YYYY-MM-DD` |
| `game_date_lt` | Game date <= | `YYYY-MM-DD` |
| `home_road` | Home or away | `Home`, `Road` |
| `pitcher_throws` | Pitcher handedness | `R`, `L` |
| `batter_stands` | Batter side | `R`, `L` |
| `position` | Player's fielding position | `2`–`9` (C–RF), `10` DH, `1` P, `IF`, `OF`, `SP`, `RP` |
| `batters_lookup[]` | Specific batters | MLBAM person ids; repeatable key |
| `pitchers_lookup[]` | Specific pitchers | MLBAM person ids; repeatable key |
| `runners_1b_lookup[]` / `runners_2b_lookup[]` / `runners_3b_lookup[]` | Specific runner on 1st/2nd/3rd | MLBAM person ids; repeatable key (the UI pairs them with `hfRO=1|`/`2|`/`3|`) |
| `metric_{N}` | Metric-range filter column (N = 1, 2, 3, ...) | see metric column table below |
| `metric_{N}_gt` / `metric_{N}_lt` | Metric range bounds (>= / <=) | numeric |
| `group_by` | Aggregation grain | `name-event` (per pitch), `name`, `name-date`, `name-month`, `name-month-year`, `name-year`, `pitch-type`, `team`, `team-pitch-type`, `team-date`, `team-month`, `team-month-year`, `team-year`, `venue`, `league`, `league-year` |
| `min_pitches` | Min total pitches | `0` (none), `2`–`10000` (fixed steps) |
| `min_results` | Min results | `0` (none), `2`–`10000` (fixed steps) |
| `min_pas` | Min plate appearances | `0` (none), `5`–`1000` (fixed steps) |
| `sort_col` | Sort column (aggregated group-bys) | see sort column list below |
| `player_event_sort` | Sort column when `group_by=name-event` | per-pitch column names (`api_p_release_speed`, `api_h_launch_speed`, `arm_angle`, `sweetspot_speed_mph`, ...) — the UI submits exactly one of `sort_col` / `player_event_sort` depending on `group_by` |
| `sort_order` | Sort direction | `desc`, `asc` |
| `chk_stats_*` | Include an aggregate stat column in results | flag params, `on` when checked (e.g. `chk_stats_pa`, `chk_stats_xwoba`, `chk_stats_velocity`) |
| `chk_event_*` | Include a per-pitch column in results | flag params (e.g. `chk_event_release_speed`, `chk_event_launch_angle`) |
| `chk_{total_name}` | Per-filter-group breakdown rows | flag params keyed by a filter's total name (`chk_pitch_type`, `chk_team`, `chk_count`, `chk_zones`, ...) plus `chk_swings`, `chk_takes`, `chk_pa`, `chk_bip`, `chk_tracked_pitch` |

### Metric columns (`metric_{N}` vocabulary)

Arm angle is a `metric_N` column (`arm_angle`), not an `hf` filter.

| Group | Columns |
|---|---|
| Pitch Metrics | `api_p_release_speed`, `api_p_release_spin_rate`, `api_p_effective_speed`, `api_release_pos_x`, `api_release_pos_z`, `api_plate_x`, `api_plate_z`, `arm_angle` |
| Pitch Movement | `api_break_x_arm`, `api_break_x_glove`, `api_break_x_batter_in`, `api_break_x_batter_out`, `api_break_z_with_gravity`, `api_break_z_induced` (bounds in inches) |
| Hit Metrics | `api_h_launch_speed`, `hyper_speed` (adjusted EV), `api_h_launch_angle`, `api_h_distance_projected` |
| Bat Tracking Metrics | `sweetspot_speed_mph` (bat speed), `attack_angle`, `swing_length`, `attack_direction`, `swing_path_tilt`, `miss_distance`, `intercept_ball_minus_batter_pos_x_inches`, `intercept_ball_minus_batter_pos_y_inches` |
| Results | `estimated_ba_using_speedangle` (xBA), `estimated_slg_using_speedangle` (xSLG), `fangraphs_est_woba_numer` (xwOBA), `delev_delta_run_exp`, `delev_delta_pitcher_run_exp`, `unadj_delta_run_exp`, `unadj_delta_pitcher_run_exp` |
| Game State | `home_score`, `away_score`, `home_score_diff`, `bat_score`, `fld_score`, `bat_score_diff`, `home_win_exp`, `bat_win_exp` |
| Lineup + Rest | `lineup_cd`, `n_thruorder_pitcher`, `n_priorpa_thisgame_player_at_bat`, `pitcher_days_since_prev_game`, `pitcher_days_until_next_game`, `batter_days_since_prev_game`, `batter_days_until_next_game` |
| Age | `age_bat`, `age_pit` (as of 12/31), `age_bat_legacy`, `age_pit_legacy` (as of 6/30) |

### Sort columns (`sort_col` vocabulary)

`pitches`, `pitch_percent`, `ba`, `xba`, `xbadiff`, `woba`, `xwoba`,
`wobadiff`, `slg`, `xslg`, `xslgdiff`, `obp`, `xobp`, `xobpdiff`,
`barrels_total`, `iso`, `babip`, `swing_miss_percent`, `swings`, `whiffs`,
`delev_run_exp`, `delev_pitcher_run_exp`, `delev_batter_run_value_per_100`,
`delev_pitcher_run_value_per_100`, `unadj_run_exp`,
`unadj_pitcher_run_exp`, `unadj_batter_run_value_per_100`,
`unadj_pitcher_run_value_per_100`, `velocity`, `effective_speed`,
`spin_rate`, `release_pos_x`, `release_pos_z`, `release_extension`,
`plate_x`, `plate_z`, `arm_angle`, `api_break_x_arm`,
`api_break_x_batter_in`, `api_break_z_with_gravity`, `api_break_z_induced`,
`launch_speed`, `hyper_speed`, `bbdist`, `launch_angle`,
`hardhit_percent`, `barrels_per_bbe_percent`, `barrels_per_pa_percent`,
`sweetspot_speed_mph`, `attack_angle`, `swing_length`, `attack_direction`,
`swing_path_tilt`, `miss_distance`,
`intercept_ball_minus_batter_pos_x_inches`,
`intercept_ball_minus_batter_pos_y_inches`,
`pos3_int_start_distance` ... `pos9_int_start_distance` (fielder start
distances, 1B–RF).

## Notable gotchas

- **`hfTeam` / `hfOpponent` emit MLBAM numeric team ids** in the current UI
  (`147`, not `NYY`); legacy 3-letter codes may still be accepted by the
  backend, but that is unverified.
- **Arm angle is a metric filter**, not an `hf` multi-select:
  `metric_1=arm_angle&metric_1_gt=...&metric_1_lt=...`.
- **Swing/take** = `hfFlag=is..swing` / `hfFlag=is..take` — there is no
  dedicated swing param.
- **`hfMo` includes `1st`/`2nd` half values** alongside months `4`–`9`
  (majors only; months and halves are mutually exclusive).
- **`hfSea` coverage**: majors pitch-level data 2008+ (Statcast proper
  2015+), minors 2021+, WBC 2023/2026.
- **The UI auto-populates complementary flags**: sorting or showing
  `launch_speed`/`launch_angle`/`hyper_speed` checks `is..bunt..not`;
  bat-tracking columns check `is..competitive`. When building queries
  directly, add these yourself if you want UI-equivalent results.
- Savant serves an HTML error page with HTTP 200 (not a 4xx) for parameter
  combinations it can't fulfill, and silently truncates responses at
  ~30,000 rows — see `fungo.statcast.search` for the detection and
  day-chunking defenses.
