# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-07-07

### Added

- `fungo.bbref`: opt-in local response cache (`enable_cache`, `disable_cache`,
  `clear_cache`). A cache hit skips the rate limiter entirely. Historical pages
  are immutable and need no TTL; current-season pages (standings, daily
  scoreboards) accept a `ttl=` in seconds. Cache files live under
  `~/.cache/fungo/bbref_cache/` by default (same `$XDG_CACHE_HOME` convention
  as the Chadwick register).
- `fungo.fangraphs`: FanGraphs JSON API access — major/minor-league
  leaderboards (including Stuff+ and PitchingBot columns), player stats and
  game logs, RosterResource depth charts (via embedded `__NEXT_DATA__`
  payloads), Guts! constants and park factors, and THE BOARD prospect
  rankings. Stdlib-only; rides the Cloudflare-exempt FanGraphs mobile-app
  User-Agent and raises `FangraphsError` with a diagnosis if that exemption
  is withdrawn.
- `fungo.bbref`: polite Baseball-Reference access — player pages, game logs,
  splits, team schedules (comment-aware table extraction keyed by `data-stat`
  attributes), and the bWAR daily CSV flat files. Every request routes
  through a process-wide rate limiter (~9 req/min) and blocks raise
  `BBRefError` with do-not-retry guidance. `beautifulsoup4` and `curl_cffi`
  become fungo's first (and only) runtime dependencies to support this
  first-class.
- FanGraphs splits leaderboards (`get_split_leaders` — the POST-only splits
  API with named split codes) and projections (`get_projections` — ZiPS,
  Steamer, ATC, THE BAT/X, OOPSY, Depth Charts, plus rest-of-season slugs).
- `fungo.fangraphs` splits: complete built-in code tables — `SPLIT_CODE_TABLE`
  (292 codes from the splits-leaderboards page inline JS) and
  `PITCH_SPLIT_CODE_TABLE` (47 pitch-split codes). Position-aware home/away
  resolution (`"home"` → code 7 for batters, 9 for pitchers). New
  `pitch_splits` parameter on `get_split_leaders` for filtering by pitch type,
  count, or zone.
- Baseball-Reference standings (duplicate-table-id handling for the AL/NL
  division pairs), amateur draft (by round and by team), box scores and daily
  scoreboards (Retrosheet-style team-code mapping, linescore extraction), and
  minor-league register pages (keyed by Chadwick `key_bbref_minors` ids).
- `fangraphs` and `bbref` CLI subcommands (function passthrough, `--list`).
- `FangraphsError` and `BBRefError` exception types.

### Removed

- `fungo.to_frame` and the `[polars]`/`[pandas]` extras. fungo returns
  `list[dict]` / `dict`, which `pl.DataFrame(rows)` and `pd.DataFrame(rows)`
  accept directly — the wrapper added nothing.

## [1.0.0]

### Added

- `fungo.mlb`, a typed pass-through wrapper surface for MLB Stats API
  endpoints.
- Baseball Savant leaderboard registry with typed wrappers and explicit
  season-parameter handling for bat-tracking boards.
- Statcast pitch-level search helpers for games, teams, matchups, and pitcher
  arsenal aggregation.
- Nathan-style derived spin physics columns via `fungo.statcast.physics`.
- Chadwick Bureau player lookup and ID converters with local cache refresh.
- `fungo` CLI with lookup, search, leaderboard, and MLB subcommands.
- Optional pandas/polars DataFrame conversion through `fungo.to_frame`.
- `py.typed` marker for inline type annotations.
- GitHub Actions CI across Python 3.12-3.14 with ruff, mypy, offline pytest
  coverage, package build, and wheel install smoke tests.

### Changed

- Packaged with Hatchling, uv, PEP 621 metadata, and runtime-only extras.
- The public API is organized around `fungo.statcast`, `fungo.mlb`, and
  `fungo.lookup`.
- Live tests are opt-in; default test runs are fully offline.

### Removed

- Removed pre-1.0 experimental modules: `fungo.download`, `fungo.field`,
  `fungo.query`, `fungo.statcast.analysis`, `fungo.statcast.base`,
  `fungo.statcast.leaderboard`, and `fungo.statcast.query`.

### Notes

- `fungo.statcast.get_top_performers` raises `SavantError` because Baseball
  Savant currently serves that page with an empty inline JSON payload and
  renders the cards directly in HTML.
