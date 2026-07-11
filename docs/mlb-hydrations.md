# MLB Stats API hydrations

The MLB Stats API (`statsapi.mlb.com`) expands its responses through the
`hydrate` query parameter: a comma-separated list of named expansions that
attach related objects (a person's current team, a game's win probability,
a team's venue) to the base payload. The official documentation at
`docs.statsapi.mlb.com` is login-gated, so the practical references are the
API's own discovery mechanism (below) and community documentation.

## Discovering valid hydrations

The API self-documents: passing `hydrate=hydrations` to any hydrate-capable
endpoint returns the hydration names that endpoint accepts.

```
GET /api/v1/people/545361?hydrate=hydrations
GET /api/v1/teams/119?hydrate=hydrations&sportId=1
```

`fungo.mlb.get_hydrations(path, params=None)` wraps this:

```python
from fungo.mlb import get_hydrations

get_hydrations("/api/v1/people/545361")
# ['awards', 'currentTeam', 'preferredTeam', 'team', 'rosterEntries',
#  'jobs', 'relatives', 'transactions', 'social', 'education', 'stats',
#  'draft', 'xrefId', 'nicknames', 'depthChart', 'nextStarts',
#  'rookieSeasons', 'prospectGrades', 'prospectLists']

get_hydrations("/api/v1/teams/119", {"sportId": 1})
# ['previousSchedule', 'nextSchedule', 'venue', 'springVenue', 'social',
#  'deviceProperties', 'game(promotions)', 'game(atBatPromotions)',
#  'game(tickets)', 'game(atBatTickets)', 'game(sponsorships)', 'league',
#  'person', 'sport', 'standings', 'division', 'xrefId', 'location']
```

(Both lists verified live 2026-07-11.)

Mechanism details worth knowing:

- **Placement is inconsistent.** `/api/v1/people/{id}` returns the
  `hydrations` array both at the response top level and inside each person
  object; `/api/v1/teams/{id}` returns it only inside each team object.
  `get_hydrations` normalizes both placements to a `list[str]`.
- **There is no `/hydrations` path form.** `GET /api/v1/teams/hydrations`
  is a 400; the discovery keyword only works as a `hydrate=` value.
- **`fields=hydrations` strips the rest of the payload** on endpoints with
  top-level placement. On nested-placement endpoints it strips everything
  (the `fields` filter needs the parent section name too, e.g.
  `fields=teams,hydrations`), so `get_hydrations` retries once without
  `fields` when the first response comes back empty.
- **Unknown hydration names are silently ignored.** A typo in `hydrate=`
  does not error; the expansion just doesn't appear. Missing data looks
  identical to "no data" — consistent with the API's general posture of
  returning `200 OK` with a structurally valid but empty payload on
  malformed input.
- **Availability varies per endpoint.** The same name (e.g. `stats`) can be
  valid on one endpoint and absent on another; discover per path rather
  than assuming.

`get_hydrations` is exported from `fungo.mlb.__all__`, so it is also
reachable from the CLI: `fungo mlb get_hydrations --path=/api/v1/people/545361`.

## Hydration syntax grammar

```
hydrate = item ("," item)*
item    = name
        | name "(" arg ("," arg)* ")"          # parameterized
        | name "(" key "=" value ("," ...) ")" # keyword form
value   = scalar
        | "[" scalar ("," scalar)* "]"          # array
```

- **Comma-separated top-level items**: `hydrate=currentTeam,awards`.
- **Parameterized form** — parentheses pass arguments to a hydration:
  `hydrate=game(content)`.
- **Keyword form** — `key=value` pairs inside the parens:
  `hydrate=stats(group=hitting,type=season,season=2024)`.
- **Parens nest** arbitrarily deep: `hydrate=game(content(media(epg)))`.
- **Brackets make arrays** where a key accepts multiple values:
  `hydrate=stats(group=[hitting,pitching],type=[season],season=2024)`.
- The `stats(...)` hydration accepts most of the parameters that
  `/api/v1/stats` itself takes (`group`, `type`, `season`, `sportId`,
  `limit`, `startDate`/`endDate`, `sitCodes`, `metrics`, opposing
  player/team ids, ...). `fungo.mlb.build_stats_hydrate` builds this form
  programmatically — including the API's date formatting (`MM/DD/YYYY`)
  and the scalar-only `sportId` constraint.

## References

- **Discovery mechanism** — `hydrate=hydrations` on any hydrate-capable
  endpoint (see above); `fungo.mlb.get_hydrations` in
  `src/fungo/mlb/discovery.py`.
- **toddrob99/MLB-StatsAPI wiki** — the Endpoints page documents per-endpoint
  parameters, including known hydration names:
  <https://github.com/toddrob99/MLB-StatsAPI/wiki>
- **pseudo-r/Public-MLB-API** — community notes on the public Stats API
  surface: <https://github.com/pseudo-r/Public-MLB-API>
- **Official docs** — <https://docs.statsapi.mlb.com> (login-gated).

## Why fungo ships no static hydration catalog

The API self-documents via `hydrate=hydrations`, and the set of valid names
drifts as MLB adds and removes expansions. A frozen list in this repo would
go stale silently; `get_hydrations` asks the live API instead.
