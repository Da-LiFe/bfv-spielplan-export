# bfv-spielplan-export

Loads the match schedules of TSV Gilching/Argelsried teams from the BFV website
into CSV files and generates an interactive HTML overview plus a PDF.

## Requirements

- Python 3.10+
- `reportlab` (PDF generation) and `pytest` (tests):

```bash
pip install --user --break-system-packages reportlab pytest
```

## Quick start

Add one BFV team URL per line to `teams.txt` (`#` starts a comment), then:

```bash
python3 fetch_bfv_spielplan.py --refresh
```

This fetches all teams from `teams.txt`, writes one CSV per team, and
regenerates `spielplan.html` and `spielplan.pdf`.

## Usage

```bash
# Update everything (all teams from teams.txt + regenerate HTML/PDF)
python3 fetch_bfv_spielplan.py --refresh

# Fetch a single team (writes <slug>_spiele_web.csv)
python3 fetch_bfv_spielplan.py <bfv-url>

# Fetch a single team to a specific file
python3 fetch_bfv_spielplan.py <bfv-url> <output.csv>

# Generate HTML/PDF only, from existing CSVs
python3 visualize_spiele.py
```

### Add a team

Append the team's BFV URL (e.g. `https://www.bfv.de/mannschaften/.../<id>`) as a
new line in `teams.txt`, then run `--refresh`.

## Output

- `*_spiele_web.csv` — raw data per team
  (columns `Wettbewerb,Datum,Uhrzeit,Heim,Gast,Spielort,Link,Quelle`, UTF-8 with BOM)
- `spielplan.html` — interactive overview: team filter, hide past games,
  same-day highlighting, map/match links, URL preselect (`?team=<Name>`),
  and `.ics` calendar export
- `spielplan.pdf` — printable multi-page overview

## Tests

```bash
python3 -m pytest -v          # Python unit tests (51)
node test/spielplan.test.mjs  # JS harness for the embedded filter/export code (needs Node >= 18)
```

## Project layout

- `config.py` — shared constants (`CLUB_MARKERS`, `PALETTE`, date format, …)
- `fetch_bfv_spielplan.py` — BFV fetcher (single fetch + `--refresh`)
- `visualize_spiele.py` — HTML/PDF generator
- `reports/` — project reports (history and design decisions)
