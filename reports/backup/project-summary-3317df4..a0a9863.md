# Spielplan TSV Gilching/Argelsried — Project Report (Display Aliases + Hot-Day Hidden Teams)

As of: 2026-08-07 · commit range `3317df4..35960c0` · 4 commits ·
Tests: pytest 9.1.1 — **59 green** (Python), JS harness still not runnable (no Node)

## Contents of this report

A new feature and its tests: configurable display aliases for club team
names, together with the switch from `teams.txt` (plain URLs) to
`teams.json` (URL + optional alias per team). A follow-up commit updates
the README for the new configuration. A follow-up fix shows hidden team
names on hot days when teams are filtered.

## Git history (`3317df4..35960c0`)

| Commit | Type | Message |
|---|---|---|
| `5703891` | feat | add configurable display aliases for club teams |
| `571a95e` | test | add unit tests for team display aliases |
| `a0a9863` | docs | update README for teams.json and display aliases |
| `35960c0` | feat | show hidden team names on hot days when teams are filtered |

## Motivation

The club's team names on the BFV pages are technical (e.g.
"TSV Gilching/Argelsried 2 (7)", "TSV Gilching/Argelsried (7)"). The
overview should display readable aliases instead, and the mapping must be
configurable without touching code.

## `teams.json` (replaces `teams.txt`)

New JSON config, one object per team:

```json
{
  "url": "https://www.bfv.de/mannschaften/tsv-gilching-argelsried-2-7/02Q0...",
  "alias": "TSV Gilching/Argelsried u15w2"
}
```

| Team (BFV) | Alias |
|---|---|
| TSV Gilching/Argelsried 2 (7) | TSV Gilching/Argelsried u15w2 |
| TSV Gilching/Argelsried (7) | TSV Gilching/Argelsried u11w |
| TSV Gilching/Argelsried (9) | TSV Gilching/Argelsried u13w |
| TSV Gilching/Argelsried U15 W | TSV Gilching/Argelsried u15w |
| TSV Gilching/Argelsried U17 W | TSV Gilching/Argelsried u17w |

- `alias` is optional: omitted/empty ⇒ the original BFV name is used.
- `teams.txt` was deleted (untracked before). The old text format is no
  longer supported.

## Implementation

### `fetch_bfv_spielplan.py`

- `load_teams()` reads the JSON file and validates each entry (a `url`
  field is required; malformed JSON and empty files raise a clear error).
- Returns `list[dict]` (`url` + `alias`); `fetch_all()` and `refresh()`
  pass only the URL to `fetch_one()` — the alias does not affect fetching.
- `--refresh` and `--teams` default to `teams.json`.

### `visualize_spiele.py`

- New `load_alias_map()` reads `teams.json` and returns a `URL -> alias`
  mapping (missing/unreadable/invalid file ⇒ empty map, no crash).
- `load_games(alias_map=None)` resolves each CSV's `Quelle` URL to an
  alias and replaces the club team's name **in the game data itself**:
  - the filter checkboxes, table rows, footer, PDF and `.ics` all display
    the alias automatically,
  - opponent names are never touched,
  - colors are recomputed from the alias (deterministic, consistent).
- `Source` gains an `original` field (BFV name) next to `team` (display
  name).
- `build_html()` embeds `TEAM_ALIASES` (`[alias, original]` pairs) into the
  page JS; `?team=` URL preselect now matches both the alias and the
  original BFV name via `aliasToOriginal`.

### `.ics` / PDF

No dedicated code changes: because the alias is applied at load time, the
`.ics` slug/file name and the PDF match display pick it up automatically.

## README update (`a0a9863`)

- `README.md` now documents `teams.json` (quick start, usage, "Add a team")
  and the optional `alias` field with a generic example (no real team names
  or URLs).
- The test count in the README was bumped to 59.

## Hot-day hidden teams (`35960c0`)

When a day has multiple games but some club teams are filtered out, the
badge now shows a line like "Nicht ausgewählt: u11w, u13w" below the
game count. The hot-day count and badge also use total games per day
instead of only visible games.

- `render_day_section()` adds a `<span class="hidden-teams">` to the day
  header (visible by JS when hidden teams exist).
- CSS: badge stacks vertically (`display:block`); `.hidden-teams` shows
  muted yellow text (`#856404`).
- JS: `clubTeamsSet` tracks club team names; hidden teams collected from
  filtered rows and displayed in the day header.
- Test updated: `test_render_day_section_hot` checks badge visibility
  specifically instead of asserting no `display:none` anywhere.

## Tests & verification

- **8 new pytest tests:** `load_alias_map` (mapping + missing file),
  `load_games` with an alias map (club_teams/sources/games aliased, home
  vs away preserved), `render_team_checks` with aliases, `build_html`
  embedded alias map, JSON `load_teams` (+ missing `url` / invalid JSON
  error paths), refresh tests converted to `teams.json`.
- **59 tests green** (`python3 -m pytest -v`).
- End-to-end: `--refresh` → 73 games fetched from 5 teams → 71 shown;
  aliases visible in `spielplan.html` (no original club names remain in
  the visible output; they only appear in the embedded `TEAM_ALIASES`
  map) and in `spielplan.pdf`.
- **JS harness** (`test/spielplan.test.mjs`): still not runnable here
  (`node` not installed); the harness now copies `config.py` into its temp
  dir so it will run correctly under Node/CI.

## File status

| File | Status |
|---|---|
| `teams.json` | new, **committed** |
| `teams.txt` | deleted (was untracked) |
| `fetch_bfv_spielplan.py` / `visualize_spiele.py` | modified, committed |
| `test/test_fetch_bfv_spielplan.py` | modified, committed |
| `test/test_visualize_spiele.py`, `test/spielplan.test.mjs` | modified, committed |
| `reports/` | untracked (convention) |
| `*_spiele_web.csv`, `spielplan.html`, `spielplan.pdf` | generated (gitignored) |

## Possible next steps

- Run the JS harness on a machine with Node (e.g. CI/GitHub Actions).
- Extend aliases to the `.ics` `SUMMARY` or add a per-team `color` in
  `teams.json`.
- Snapshot tests for `build_html()` to guard against regressions.
- Add a "show hidden teams" expand/collapse for hot days.
