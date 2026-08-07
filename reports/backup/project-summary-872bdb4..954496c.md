# Spielplan TSV Gilching/Argelsried — Project Report

As of: 2026-08-02 · last generation: `spielplan.html`/`spielplan.pdf` at 16:22 ·
Tests: pytest 9.1.1 + Node harness (node v22.12.0)

## Goal

Automatically load match schedules of BFV teams of TSV Gilching/Argelsried
(CSV), visualize them (HTML overview with filter + PDF), and export them as a
calendar (.ics).

## Files & structure

| File | Purpose | Committed |
|---|---|---|
| `fetch_bfv_spielplan.py` | Fetches the match schedule of a BFV team and writes CSV. Supports single fetch and `--refresh` (all teams from `teams.txt`). | yes |
| `visualize_spiele.py` | Reads all `*_spiele_web.csv`, generates `spielplan.html` + `spielplan.pdf`. | yes |
| `.gitignore` | Excludes generated artifacts: `spielplan.html`, `spielplan.pdf`, `vereinsspielplan.pdf`, `*_spiele_web.csv`, `__pycache__/`. | yes |
| `pytest.ini` | pytest configuration: `testpaths = test`, `pythonpath = .` (repo-root imports). | yes |
| `test/spielplan.test.mjs` | Node DOM-shim harness for the embedded JS (filter, preselect, hide-past, .ics). | yes |
| `test/test_fetch_bfv_spielplan.py` | pytest suite for the fetcher (incl. real BFV fixture). | yes |
| `test/test_visualize_spiele.py` | pytest suite for the generator. | yes |
| `test/fixtures/bfv_sample.html` | Trimmed real BFV HTML sample (2 complete entries) as fixture. | yes |
| `teams.txt` | List of team URLs (one per line, `#` = comment). | no (untracked) |
| `reports/` | These reports. | no (untracked) |
| `*_spiele_web.csv` (5×) | Raw data per team. Columns: `Wettbewerb,Datum,Uhrzeit,Heim,Gast,Spielort,Link,Quelle` (UTF-8 with BOM). `Quelle` = BFV team page. | generated |
| `spielplan.html` / `spielplan.pdf` | Generated overviews. | generated |
| `vereinsspielplan.pdf` | Club's original PDF (reference, replaced by BFV fetch). | excluded |

## Teams (teams.txt, as of)

| Slug | Competition | Games (CSV) |
|---|---|---|
| `tsv-gilching-argelsried-2-7` | U15 (C-youth) Norwegian Model 03 | 18 |
| `tsv-gilching-argelsried-7` | U15 (C-youth) Norwegian Model | 14 |
| `tsv-gilching-argelsried-9` | U15 (C-youth) Norwegian Model | 22 |
| `tsv-gilching-argelsried-u15-w` | U15 (C-youth) BOL | 14 |
| `tsv-gilching-argelsried-u17-w` | Girls' B-youth | 5 |

Total CSV rows: **73**. Of these shown in HTML/PDF: **71** —
2 rows are `Spielfrei` (bye) entries without a date and are intentionally skipped.

## Usage

```bash
# Update everything (load all teams from teams.txt + regenerate HTML/PDF)
python3 fetch_bfv_spielplan.py --refresh

# Load/update a single team
python3 fetch_bfv_spielplan.py <bfv-url>            # e.g. https://www.bfv.de/mannschaften/.../<id>
python3 fetch_bfv_spielplan.py <bfv-url> <output.csv>

# Generate only HTML/PDF from existing CSVs
python3 visualize_spiele.py

# Tests (Python, requires pytest)
python3 -m pytest -v

# Tests (JS harness, requires node >= 18)
node test/spielplan.test.mjs
```

To add a new team: append a URL line to `teams.txt`, then run `--refresh`
(a single team can also be fetched directly).

## Features of the HTML overview (`spielplan.html`)

- **Team filter (multi-select):** one checkbox per club team (derived from CSV
  names, not opponents). "All teams" = everything. Default: only "All teams"
  active. Clicking a team selects only that one; multiple possible; deselect
  all ⇒ "All teams".
- **"Hide past games":** checkbox, **active by default**. Hides match days
  before today (comparison via `YYYYMMDD` key, correct across month boundaries).
  Can be combined with the team filter. Display appends " · past games hidden".
- **Same-day highlight:** ≥2 games on a date ⇒ amber background + badge
  "⚠ N games" (also in the PDF).
- **H/A badge:** home game (green) / away game (grey) via `CLUB_MARKERS`.
- **Map ↗:** Google Maps link to the venue address.
- **Match ↗:** link to the BFV match.
- **URL preselect:** `?team=<Name>` and multiple `?team=A&team=B` (URL-encoded)
  preselect the teams and deactivate "All teams".
- **Calendar export (.ics):** respects the current selection — team selection
  **and** "hide past games". File name: `spielplan_<slug>.ics`,
  `spielplan_alle.ics`, or `spielplan_auswahl.ics`. Events: 2h duration,
  `Europe/Berlin` with VTIMEZONE, all-day if no time, RFC-5545 escaping,
  73-char folding.
- **Footer:** generation time + links to the BFV team pages instead of CSV
  file names.

## Configuration in the code

- `CLUB_MARKERS` (visualize_spiele.py): `["tsv gilching", "tsv gilching/argelsried", "tsv gilching-argelsried", "tsv gilching/a"]` — determines home/away.
- CSV schema in `fetch_bfv_spielplan.py`: extended by the `Quelle` column.
- Dependencies: `reportlab` (PDF) and `pytest` (tests) —
  `pip install --user --break-system-packages reportlab pytest`.
- JS harness requires Node ≥ 18 (`URLSearchParams`, `vm`, ESM).

## Important bug fixes (history)

1. **`.ics` export crash:** `lines.join(...).map(...)` calls `map()` on a string
   (doesn't exist). Correct: `lines.map(icsFold).join('\r\n')`.
2. **Filter seemed "broken":** checkboxes had no `value` attribute ⇒ for
   checkboxes without `value`, `input.value` is always `"on"` instead of the
   team name. Fix: set `value="{team}"` on the `<input>`.
3. **Default filter state:** all team checkboxes were pre-checked ⇒ clicking
   "deselected" instead of selecting. Fix: only "All teams" pre-checked, team
   checkboxes unchecked.
4. **Past-game comparison:** lexicographic comparison of `DD.MM.YYYY`
   compares the day first (wrong across month boundaries). Fix: `dayKey()` ⇒
   `YYYYMMDD`.

## Tests & verification

- **JS harness (`test/spielplan.test.mjs`):** renders `spielplan.html` via the real
  Python scripts in a temp directory with fixture CSVs (relative dates),
  extracts the `<script>` and runs it in Node `vm` with a DOM shim. Tested:
  hide-past (incl. month boundaries), team filter single/multi, "All teams",
  URL preselect, hot-day badge, .ics contents (≤73 CRLF folding, escaping,
  DTEND overnight rollover, all-day `DTSTART;VALUE=DATE`) and file names.
  Result: **38 tests green**.
- **Python (pytest):**
  - `fetch_bfv_spielplan`: `clean`, `parse_entries` with **real, trimmed BFV HTML**
    (`test/fixtures/bfv_sample.html`) plus synthetic edge cases, pagination
    (`fetch_all_matches`), CSV write with UTF-8 BOM + `Quelle`, `refresh` error
    paths, `SystemExit` cases, `main`.
  - `visualize_spiele`: `parse_datum`, `team_color`, `short_place`, `maps_url`, `esc`,
    `german_now`, `load_games`, `group_by_day`, `build_html`, `build_pdf`, `main`.
  - Result: **43 tests green** (`python3 -m pytest -v`).
- Output: `71 games from 5 files` → HTML + PDF (multi-page).

## Git history (commit range `872bdb4..954496c`)

| Commit | Message |
|---|---|
| `872bdb4` | first commit (README) |
| `980e9fd` | `feat: add BFV match schedule fetcher and overview generator` |
| `954496c` | `test: add Python unit tests for fetcher and generator` |

- Committed: scripts, `.gitignore`, `pytest.ini`, `test/` (JS harness, pytest suites, fixture).
- Not committed: `reports/`, `teams.txt` (intentionally untracked), generated artifacts.

## Possible next steps

- Include any additional teams via `teams.txt`.
- `.ics` export options (e.g. reminders/`DESCRIPTION` details, separator).
- Automatic refresh execution (cron/not needed).
- CI pipeline (GitHub Actions): run `python3 -m pytest` + `node test/spielplan.test.mjs` on every push.
