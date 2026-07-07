# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`fungo` acquires baseball data from public web sources: Baseball Savant (Statcast pitch-level search + ~42 leaderboards), the MLB Stats API (`statsapi.mlb.com`), FanGraphs (leaderboards, player stats, RosterResource, Guts!, THE BOARD), Baseball-Reference (rate-limited single-page fetchers + WAR flat files), and the Chadwick Bureau player-ID register.

Runtime dependencies are exactly **`beautifulsoup4` + `curl_cffi`** (both first-class, both existing solely for Baseball-Reference — table parsing and Cloudflare TLS impersonation respectively); every other source is stdlib-only. It returns **raw data**, not DataFrames:

- CSV endpoints (Statcast search, most leaderboards, lookup, B-R tables/WAR files) return `list[dict]`; **every value is a string** (`""` for empty cells). Callers cast themselves.
- JSON endpoints (the MLB Stats API, FanGraphs, HTML-backed Savant leaderboards) return the raw `dict` / `list` exactly as the source produced it. **FanGraphs values are native JSON numbers**, not strings.

There is **no DataFrame helper** — `pl.DataFrame(rows)` / `pd.DataFrame(rows)`
accept fungo output directly, and callers wrap `list[dict]` output themselves.
`rich` progress bars are an opt-in extra. The library never writes to stdout
unless `progress=True` is passed.

## Commands

- Env / install (Python `>=3.12`): `uv venv` then `uv pip install -e ".[dev]"`.
- Lint / format: `uv run ruff check .` and `uv run ruff format .` (line length 88; lint selects `E,F,W,I,UP,B,SIM,C4,RUF`).
- Types: `uv run mypy src` (strict mode; `files = ["src"]`).
- Tests: `uv run pytest`. Tests are **offline by default** — `addopts = "-m 'not live'"` deselects network tests. Live tests are marked `@pytest.mark.live`; run them with `uv run pytest -m live`. Run one test: `uv run pytest tests/statcast/test_leaderboards.py::test_name`.

### CLI

A single console script, `fungo`, with six subcommands (registered via `[project.scripts]` in `pyproject.toml`). `cli.py` has no `__main__` guard and there is no `__main__.py`, so **`python -m fungo` does not work** — invoke the installed `fungo` script.

```
fungo lookup [--name NAME | --mlbam ID] [--no-mlb-only] [-o OUT] [--format {csv,json}]
fungo search --start YYYY-MM-DD --end YYYY-MM-DD [--player-type pitcher|batter] [--player-id ID] [--level mlb|milb] [--<field>=val ...]
fungo leaderboard SLUG [--season YEARS] [--type T] [--player-id ID] [--<field>=val ...]   |   fungo leaderboard --list [--category C]
fungo mlb FUNCTION [--<field>=val ...]         |   fungo mlb --list
fungo fangraphs FUNCTION [--<field>=val ...]   |   fungo fangraphs --list
fungo bbref FUNCTION [--<field>=val ...]       |   fungo bbref --list
```

- `--format` defaults to `csv` for `lookup`/`search`/`leaderboard` and `json` for `mlb`/`fangraphs`/`bbref`. CSV rendering requires a `list[dict]`; non-tabular results error and ask for `--format json`.
- `search` and the function-passthrough subcommands accept arbitrary `--field=value` (or `--field value`) via `parse_known_args` → `_parse_extras`. **Only `search`** pipe-joins comma-separated values (`--pitch-type=FF,SL` → `FF|SL`, Savant's convention); the others pass values verbatim.
- `mlb`/`fangraphs`/`bbref` share one handler (`_run_module_function`) that dispatches `FUNCTION` onto the module's `__all__` (non-callables are excluded from `--list` and dispatch).
- `--season 2023,2024` parses as a `list[int]`, valid only for the
  bat-tracking season-array / camelCase boards (see below). Passing a
  multi-year value to any other (`int`-format) board raises `ValidationError` —
  `_emit_year` fails loud rather than silently sending a mangled `year=`.

## Architecture

Two layers: a **stdlib generic engine** and a **source-specific specialization** on top of it.

### Generic engine

- `http.py` — stdlib transport. `request_bytes` (urlencode with `safe="|"` so pipe-delimited params survive, `doseq=True` so list values become repeated keys, drops `None` values, exponential-backoff retry on 5xx/network, raises `RequestError` on 4xx or exhausted retries). `request_json` = `request_bytes` + JSON decode. `parse_csv` (BOM-aware via `utf-8-sig`, preserves empty strings). `map_concurrent` (bounded `ThreadPoolExecutor`, preserves input order, optional inter-submit `delay`, opt-in silent `rich` progress). Uses PEP-695 generics.
- `exceptions.py` — `FungoError` base; `RequestError`, `SavantError`, `MLBStatsError`, and `ValidationError(value, field_name, valid_values=None)` (also a `ValueError`; emits a `difflib` "did you mean?" suggestion). Reuse these — don't raise bare `ValueError`.
- `constants.py` — `PITCH_TYPES`, `TEAMS` (enriched club metadata), and resolvers `resolve_team` / `resolve_pitch_type` / `resolve_hand` (raise `ValidationError` on a miss).
- `lookup.py` — Chadwick register cross-reference (MLBAM ↔ FanGraphs ↔ Baseball-Reference ↔ Retrosheet). Downloads the ~6 MB register (16 shards) on first use and caches it under the stdlib user cache dir (`$XDG_CACHE_HOME` or `~/.cache` → `fungo/chadwick_people.csv`). `lookup(...)`, `refresh()`, and `mlbam_to_*` / `*_to_mlbam` converters — the id bridge into both `fangraphs/` (`mlbam_to_fangraphs`) and `bbref/` (`mlbam_to_bbref`).

### Statcast specialization (`statcast/`)

- `search.py` — `statcast_search(start_date, end_date, ...)` and the convenience wrappers `search_game`, `search_matchup`, `search_team`, plus `aggregate_pitcher_arsenal` / `get_pitcher_arsenal`. `fetch_csv` adds Savant-specific **HTML-vs-CSV detection**: Savant serves an HTML page with HTTP 200 (not a 4xx) when given params it can't fulfill — that's caught and raised as `SavantError`. `statcast_search` returns **raw rows**; it does NOT add physics columns.
- `leaderboards.py` — the `LEADERBOARDS` registry (~42 entries), the `year_format`-aware `fetch_leaderboard` + registry-checked `get_leaderboard`, ~33 typed CSV wrappers (`get_exit_velocity_barrels`, `get_expected_statistics`, `get_pitch_movement`, `get_poptime`, `get_catcher_framing`, …), 4 HTML-backed wrappers (`get_park_factors`, `get_hot_stove`, `get_top_performers`, `get_rolling_windows`, via `fetch_html_json`), and the introspection helpers `list_leaderboards` / `describe_leaderboard`. **To add or change a Statcast field, edit the registry dict in `leaderboards.py`** — that's the single source of truth.
- `physics.py` — Nathan (2021) spin-physics derived columns (stdlib `math` only). `add_spin_columns(rows)` is **opt-in** — call it explicitly on search output; nothing applies it automatically. `compute_row`, `axis_to_clock`, `DERIVED_COLUMNS`.

### MLB Stats API (`mlb/`)

A pure pass-through port (~90 functions across `stats_api`, `people`, `teams`, `games`, `stats`, `misc`, `discovery`, `constants`). Every function returns the raw JSON `dict`/`list`. `mlb_api(path, params)` is the low-level escape hatch; the typed functions (`get_person`, `get_schedule`, `get_roster`, `get_stats`, …) wrap specific endpoints. `mlb.__all__` lists every public function (the CLI's `fungo mlb --list` reads it).

### FanGraphs (`fangraphs/`)

JSON pass-through like `mlb/`, stdlib-only. `api.py` is the fragile seam: every call sends `User-Agent: okhttp/4.12.0` (see non-obvious thing #3) and maps HTTP 403 → `FangraphsError` with the Cloudflare-exemption diagnosis. `fg_json` (GET routes), `fg_json_post` (the splits API is POST-only), `fg_html` (guts.aspx), `fg_page_data` (`__NEXT_DATA__` extraction for pages with no API twin). On top: `leaders.py` (`get_leaders`/`fetch_leaders`/`get_splits` — handles the inverted `season`/`season1` params; `league="minor"` switches endpoints), `splits.py` (`get_split_leaders` — the POST splits leaderboards; full 292-code table in `SPLIT_CODE_TABLE`, named shortcuts in `SPLIT_CODES`, position-aware home/away resolution, raw ints accepted; `pitch_splits` param feeds `strSplitArrPitch` with pitch-type/count/zone codes from `PITCH_SPLIT_CODES`/`PITCH_SPLIT_CODE_TABLE` (47 codes); `strType` 1/2/3 = standard/advanced/batted-ball), `projections.py` (`get_projections` — bare-list response; RoS slugs are `r`-prefixed except `steamerr`), `players.py` (`get_player_stats`, `get_game_log`), `roster_resource.py` (`get_depth_chart` walks the dehydrated React-Query cache in `__NEXT_DATA__` — no public API route exists), `guts.py` (stdlib `html.parser` table scrape; all-string values), `prospects.py` (THE BOARD). Leaders rows include `playerid` (FG) + `xMLBAMID` (MLBAM); the ~540-column pitching board carries Stuff+ (`sp_*`) and PitchingBot (`pb_*`) — none of it membership-gated.

### Baseball-Reference (`bbref/`)

The **inverse of fungo's usual throughput posture**: polite single-page fetchers, never bulk. `session.py` routes every request through a process-wide `_RateLimiter` (6.5s spacing ≈ 9 req/min — under both Sports Reference's published 20/min and the community-tested 10/min block threshold) and maps 403/429 → `BBRefError` with do-not-retry jail guidance; transport is `curl_cffi` `impersonate="chrome"` (B-R Cloudflare-fingerprint-blocked plain clients for months in 2025). `tables.py` strips HTML-comment markers then parses once with `beautifulsoup4` (B-R defers secondary tables inside `<!-- -->`; the live/commented split shifts per page since their 2024 table upgrade), keying cells by the stable `data-stat` attributes; duplicate table ids (the standings page ships `standings_E` twice — AL then NL) get positional suffixes (`standings_E_2`) instead of overwriting. `players.py`/`teams.py` return **all tables from one page fetch** (`get_player`, `get_game_log`, `get_splits`, `get_team_schedule`). `leagues.py` adds standings (pre-1969 = only `expanded_standings_overall`) and the amateur draft (`query_type=franch_year` wants historical franchise codes: ANA/FLA/TBD). `boxes.py` adds box scores (Retrosheet-style home codes — `BOX_SCORE_TEAM_CODES` maps the 12 that differ from franchise codes; team table ids embed the season's club name, so enumerate them from the result, never hard-code; the id-less linescore is returned under `"linescore"`) and `get_daily` (scoreboard links + the 16 `standings-{upto|after}-*` tables). `register.py` fetches MiLB register pages — ids are Chadwick `key_bbref_minors` verbatim; never synthesize them from names. `war.py` fetches the `war_daily_{bat,pitch}.txt` CSV flat files (bWAR, no HTML). `cache.py` is an opt-in local response cache (off by default; activated via `enable_cache`): checked inside `bbref_bytes` *before* `_limiter.wait()` so a cache hit costs no rate-limit budget, and written only after a successful fetch so errors are never cached. **Never add `map_concurrent` fan-out here.**

## The non-obvious things (the library's hard-won value)

### 1. Bat-tracking boards ignore `year=` (the `year_format` mechanism)

The three Hawk-Eye bat-tracking boards — `bat-tracking`, `bat-tracking/swing-path-attack-angle`, `bat-tracking/swing-timing-miss-distance` — **silently return the current season if you pass the standard `year=` param.** `_emit_year` in `leaderboards.py` branches per slug on the registry's `year_format`:

- `int` / `special` → `year=<str>` (`special`, e.g. active-spin, wants a composite `"2024_spin-based"` — build it with `active_spin_year`).
- `camelCase_season` → `seasonStart` + `seasonEnd`. A `(start, end)` tuple/list is a **contiguous range**; multi-year returns **one aggregated row per player across the span, with no year column** (`bat-tracking`, `swing-path-attack-angle`).
- `season_array` → repeated `season[]` keys (this is why `request_bytes` uses `doseq=True`). A list is a **true multi-select**; multi-year returns **one row per player per year, with a year column** (`swing-timing-miss-distance`).

The tuple-vs-list / range-vs-array distinction is the whole point — it dictates whether you get a year column. Also: `swing-timing-miss-distance` uses the plain `min` threshold, not `minSwings`, and `miss_distance` is in inches.

### 2. Day-chunking defends the ~30k-row cap

Savant silently truncates responses at ~30,000 rows (`MAX_ROWS_PER_QUERY`). `statcast_search` auto-chunks any range longer than 5 days into 1-day requests, fanned through `map_concurrent` (bounded pool, 1s politeness delay between submits), and flattens per-day results in date order. Pipe-delimited multi-value filters must **not** be URL-encoded — `request_bytes` sets `safe="|"` for exactly this.

### 3. FanGraphs access rides one Cloudflare exemption (`okhttp/4.12.0`)

Cloudflare TLS-fingerprint-blocks every generic HTTP client on fangraphs.com — a browser User-Agent alone gets a 403 JS challenge (pybaseball has been broken on FG since 2025 because of this). The one exemption is the FanGraphs mobile app's client: **`User-Agent: okhttp/4.12.0`** (verified live 2026-07). `fangraphs/api.py` sends it on every call and raises `FangraphsError` naming the condition on any 403 — if that error starts appearing, the exemption was withdrawn and the module needs a new access path (do not "fix" it by retrying). Also inverted param naming: `season` = END year, `season1` = START.

### 4. Baseball-Reference tolerance is conditional on the rate limiter

Sports Reference publishes limits *for bots* (20 req/min stated; >10/min earns ~1-hour blocks per community testing; jail can last a day) and prohibits bulk harvesting outright. The `bbref/` module is only defensible while every request goes through `session._limiter` and stays single-page/on-demand. Never bypass the limiter, never make it user-raisable above the ceiling, never add concurrency, never build anything crawler-shaped on top. B-R also Cloudflare-fingerprint-blocked plain `requests` for months in 2025 — `curl_cffi` impersonation is the durable transport; the stdlib fallback works from residential IPs today but can break without notice.

## Conventions

- Additional sources follow the same shape: a fetch seam per source (stdlib
  `http.py` where possible), source-specific quirks (HTML detection, param
  emission, UA requirements, rate limiting) isolated in that source's module,
  raw `list[dict]`/JSON out, DataFrame conversion left to the caller.
- Fail loud — let stdlib/transport exceptions propagate; raise the typed `ValidationError`/`SavantError`/`MLBStatsError`/`RequestError` for input and source problems rather than bare exceptions or silent fallbacks.
- Keep dependencies minimal: `beautifulsoup4` + `curl_cffi` are the only runtime deps (bbref needs them); `rich` stays an optional extra imported lazily. No DataFrame dependency ever — users wrap `list[dict]` output themselves.
