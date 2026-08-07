# Spielplan TSV Gilching/Argelsried — Consolidated Project Report

**As of:** 2026-08-08  
**Full commit range:** `872bdb4..cb2df4d` · **30 commits**  
**Tests:** pytest 9.1.1 — **59 green** (Python) · JS harness not runnable (no Node)

---

## Project Overview

Automatically load match schedules of BFV (Bayerischer Fußball-Verband) teams of
TSV Gilching/Argelsried from CSV data, visualize them as an interactive HTML
overview with team filtering and PDF export, and export them as a calendar
(.ics).

---

## File Structure

| File | Purpose |
|------|---------|
| `fetch_bfv_spielplan.py` | Fetches match schedules from BFV team pages, writes CSV. Supports `--refresh` (all teams from `teams.json`). |
| `visualize_spiele.py` | Reads all `*_spiele_web.csv`, generates `spielplan.html` + `spielplan.pdf`. |
| `config.py` | Central constants: `CLUB_NAME`, `CLUB_MARKERS`, `PALETTE`, weekday/month names. |
| `teams.json` | Team URL → display alias mapping (replaced `teams.txt`). |
| `templates/spielplan.html` | External HTML template with `$variable` placeholders. |
| `fonts/NotoSans-Regular.ttf` | Bundled font for PDF umlaut support. |
| `.github/workflows/ci.yml` | CI pipeline: lint-ruff, typecheck-mypy, test-python (parallel jobs). |
| `pyproject.toml` | Project metadata, pytest/coverage/mypy/ruff config. |
| `test/test_fetch_bfv_spielplan.py` | pytest suite for the fetcher (479 lines). |
| `test/test_visualize_spiele.py` | pytest suite for the generator (577 lines). |
| `test/spielplan.test.mjs` | Node DOM-shim harness for embedded JS (filter, preselect, hide-past, .ics). |

Generated (gitignored): `*_spiele_web.csv`, `spielplan.html`, `spielplan.pdf`, `vereinsspielplan.pdf`

---

## Usage

```bash
# Update everything (load all teams from teams.json + regenerate HTML/PDF)
python fetch_bfv_spielplan.py --refresh

# Load a single team
python fetch_bfv_spielplan.py <bfv-url>

# Generate only HTML/PDF from existing CSVs
python visualize_spiele.py

# Run tests
python -m pytest -v --cov=.

# Lint and type check
ruff check .
ruff format --check .
mypy .
```

---

## HTML Overview Features

- **Team filter (multi-select):** checkboxes per club team; "All teams" default.
- **Hide past games:** active by default; works with team filter.
- **Same-day highlight:** ≥2 games → amber background + badge "⚠ N games".
- **H/A badge:** home (green) / away (grey) via `CLUB_MARKERS`.
- **Map ↗:** Google Maps link to venue.
- **Match ↗:** link to BFV match page.
- **Display aliases:** configurable in `teams.json` (e.g. "TSV Gilching/Argelsried 2 (7)" → "TSV Gilching/Argelsried u15w2").
- **Hidden teams on hot days:** shows filtered-out team names when some teams are deselected.
- **URL preselect:** `?team=<Name>` and `?team=A&team=B`.
- **Calendar export (.ics):** respects current selection, 2h duration, `Europe/Berlin` timezone.
- **Footer:** generation time + BFV team page links.
- **Responsive:** card layout on small screens.

---

## Git History (30 commits)

### Phase 1: Foundation (`872bdb4..954496c`) — 3 commits

| Commit | Message |
|--------|---------|
| `872bdb4` | first commit (README) |
| `980e9fd` | feat: add BFV match schedule fetcher and overview generator |
| `954496c` | test: add Python unit tests for fetcher and generator |

### Phase 2: Refactoring (`954496c..3317df4`) — 8 commits

| Commit | Message |
|--------|---------|
| `559908b` | feat: make HTML overview responsive for mobile |
| `31467b7` | fix: make mobile card layout actually render and readable |
| `01503a8` | refactor: extract shared config module and typed models |
| `22dc8a1` | refactor: split refresh() into load_teams, fetch_all, regenerate_html |
| `5681fa1` | refactor: add type hints and decompose build_html into render helpers |
| `19d0ed2` | fix: correct invalid hex color in away-tag styling |
| `955a72c` | test: add unit tests for extracted render helpers |
| `3317df4` | docs: add user's guide to README |

**Key changes:**
- `config.py` — central constants (SCRIPT_DIR, CLUB_MARKERS, PALETTE, etc.)
- `refresh()` split into `load_teams()`, `fetch_all()`, `regenerate_html()`
- `build_html()` split into 5 render helpers: `render_game_row`, `render_day_section`, `render_team_checks`, `render_footer`, `render_games_js`
- `infer_team()` extracted from `load_games()`
- Mobile-responsive card layout

### Phase 3: Display Aliases (`3317df4..35960c0`) — 4 commits

| Commit | Message |
|--------|---------|
| `5703891` | feat: add configurable display aliases for club teams |
| `571a95e` | test: add unit tests for team display aliases |
| `a0a9863` | docs: update README for teams.json and display aliases |
| `35960c0` | feat: show hidden team names on hot days when teams are filtered |

**Key changes:**
- `teams.json` replaces `teams.txt` (URL + optional alias per team)
- `load_teams()` reads JSON, validates entries
- `load_alias_map()` + `load_games(alias_map)` resolve aliases at load time
- Hidden team names shown on hot days when filtered

### Phase 4: Improvements (`35960c0..cb2df4d`) — 14 commits

| Commit | Message |
|--------|---------|
| `35960c0` | feat: show hidden team names on hot days when teams are filtered |
| `90752fb` | chore: add reports/ to .gitignore |
| `3700af8` | refactor: replace regex HTML parser with html.parser |
| `7eab232` | feat: warn on missing team names and fix PDF font handling |
| `256d656` | feat: bundle NotoSans-Regular.ttf for PDF umlaut support |
| `b426d00` | test: add tests for html.parser, caching, error handling, warnings |
| `b2abcdf` | chore: update teams.json configuration |
| `436431c` | chore: add .bfv_cache/ to .gitignore |
| `5249bbb` | chore: add pyproject.toml, coverage config, and CI workflow |
| `c52830e` | feat: add rate limiting, configurable club name, and mypy config |
| `f738743` | refactor: extract HTML template to external file |
| `da5c55d` | chore: add ruff linting and formatting |
| `79ef324` | ci: use virtual environment and remove test-js job |
| `cb2df4d` | chore: add build system, consolidate config, and use venv |

**Key changes:**
- `html.parser.HTMLParser` replaces regex-based HTML parsing
- `NotoSans-Regular.ttf` bundled for PDF umlaut support
- `BFV_RATE_LIMIT` env var for rate limiting between paginated requests
- `CLUB_NAME` configurable via `config.py`
- `pyproject.toml` centralizes all tool config (pytest, coverage, mypy, ruff)
- CI: 3 parallel jobs (lint-ruff, typecheck-mypy, test-python) with 90% coverage threshold
- HTML template extracted to `templates/spielplan.html`
- `pytest.ini` deleted (consolidated into `pyproject.toml`)

---

## Configuration

### `teams.json`

```json
{
  "url": "https://www.bfv.de/mannschaften/...",
  "alias": "TSV Gilching/Argelsried u15w2"
}
```

- `alias` is optional: omitted/empty ⇒ original BFV name used
- Team URLs from BFV pages

### `config.py` constants

| Constant | Default | Meaning |
|----------|---------|---------|
| `CLUB_NAME` | "TSV Gilching/Argelsried" | Display name |
| `CLUB_MARKERS` | `{"tsv gilching", ...}` | Home/away detection |
| `PALETTE` | 15 colors | Deterministic team colors |

### CI Coverage Threshold

`fail_under = 90` in `pyproject.toml`

---

## Tests & Verification

- **Python (pytest):** 59 tests green
  - `test_fetch_bfv_spielplan.py`: fetcher tests (clean, parse_entries, pagination, CSV write, refresh, main)
  - `test_visualize_spiele.py`: generator tests (parse_datum, team_color, short_place, maps_url, esc, german_now, load_games, group_by_day, build_html, build_pdf, main)
- **JS harness:** `test/spielplan.test.mjs` — 38 tests (not runnable without Node)

---

## Coverage Gap

**14 commits from `35960c0` to `cb2df4d` have no dedicated test coverage.**
See `reports/backup/uncovered-commits-35960c0..cb2df4d.md` for details.

---

## Previous Reports

Backup copies of individual reports are in `reports/backup/`:
- `project-summary-872bdb4..954496c.md` — Initial project report
- `project-summary-954496c..3317df4.md` — Refactoring report
- `project-summary-3317df4..a0a9863.md` — Display aliases report
- `uncovered-commits-35960c0..cb2df4d.md` — Uncovered commits report
- `p2_plan.md` — P2 improvement plan
