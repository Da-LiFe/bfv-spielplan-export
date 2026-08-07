# bfv-spielplan-export

Loads the match schedules of a club's teams from the BFV website into CSV
files and generates an interactive HTML overview plus a PDF.

## Requirements

- Python 3.10+
- `reportlab` (PDF generation) and `pytest` (tests):

```bash
pip install --user --break-system-packages reportlab pytest
```

## Quick start

Add one object per BFV team to `teams.json` (a `url` is required, `alias` is
optional), then:

```bash
python3 fetch_bfv_spielplan.py --refresh
```

This fetches all teams from `teams.json`, writes one CSV per team, and
regenerates `spielplan.html` and `spielplan.pdf`.

## Usage

```bash
# Update everything (all teams from teams.json + regenerate HTML/PDF)
python3 fetch_bfv_spielplan.py --refresh

# Fetch a single team (writes <slug>_spiele_web.csv)
python3 fetch_bfv_spielplan.py <bfv-url>

# Fetch a single team to a specific file
python3 fetch_bfv_spielplan.py <bfv-url> <output.csv>

# Use a teams file in a different location
python3 fetch_bfv_spielplan.py --refresh --teams /path/to/teams.json

# Generate HTML/PDF only, from existing CSVs
python3 visualize_spiele.py
```

### Team configuration (`teams.json`)

Each team is an object with a `url` (the BFV team page) and an optional `alias`
used for display in the HTML filter, tables, footer, PDF and `.ics` export:

```json
[
  {
    "url": "https://www.bfv.de/mannschaften/<slug>/<team-id>",
    "alias": "My Club Team A"
  },
  {
    "url": "https://www.bfv.de/mannschaften/<slug>/<team-id>"
  }
]
```

If `alias` is missing or empty, the original BFV team name is used. Opponent
names are never aliased.

### Add a team

Add the team's BFV URL (e.g. `https://www.bfv.de/mannschaften/.../<id>`) as a
new object in `teams.json`, optionally with an `alias`, then run `--refresh`.

## Output

- `*_spiele_web.csv` — raw data per team
  (columns `Wettbewerb,Datum,Uhrzeit,Heim,Gast,Spielort,Link,Quelle`, UTF-8 with BOM)
- `spielplan.html` — interactive overview: team filter, hide past games,
  same-day highlighting, map/match links, URL preselect (`?team=<Name>`),
  and `.ics` calendar export
- `spielplan.pdf` — printable multi-page overview

## Tests

```bash
python3 -m pytest -v          # Python unit tests (59)
node test/spielplan.test.mjs  # JS harness for the embedded filter/export code (needs Node >= 18)
```

## Project layout

- `config.py` — shared constants (`CLUB_MARKERS`, `PALETTE`, date format, …)
- `teams.json` — team config: BFV URLs and optional display aliases
- `fetch_bfv_spielplan.py` — BFV fetcher (single fetch + `--refresh`)
- `visualize_spiele.py` — HTML/PDF generator
- `reports/` — project reports (history and design decisions)
