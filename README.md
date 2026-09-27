# bfv-spielplan-export

Loads the match schedules of a club's teams from the BFV website into CSV
files and generates an interactive HTML overview plus a PDF.

## Requirements

- Python 3.10+
- `reportlab` (PDF generation), `pytest` and `ruff` (tests/lint) — best run in a venv:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install reportlab pytest ruff
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

# Single-team overview PDF with the next 4 upcoming games
# (writes <slug>_monthly.pdf, e.g. tsv-gilching-argelsried-u13-2_monthly.pdf)
python3 visualize_spiele.py --team "TSV Gilching/Argelsried u13-2"

# Custom number of games / output path
python3 visualize_spiele.py --team "TSV Gilching/Argelsried u13-2" --next 6 --out team.pdf

# Kapitän (team lead) assignments
python3 visualize_spiele.py --captains-assign   # fill new duty weeks round-robin
python3 visualize_spiele.py --captains-check   # verify equal distribution (exit 1 if off)

# Lineup sheet for one game (next game with a lineup, or a given date)
python3 visualize_spiele.py --aufstellung --team "TSV Gilching/Argelsried u13-2"
python3 visualize_spiele.py --aufstellung --team "TSV Gilching/Argelsried u13-2" --date 2026-10-03
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

### Team overview PDF

`python3 visualize_spiele.py --team <Name/Alias>` generates a single, share-ready PDF
(`<slug>_monthly.pdf`) with the next 4 upcoming games of one team — ideal for parents.
The `--team` value matches a configured `alias` or the original BFV team name
(case-insensitive); `--next N` changes the number of games, `--out` overrides the
output path. Each game card shows weekday/date, time, home and away team, competition,
location with a clickable map link, a home/away badge and the match link — it omits the
"several games on the same day" (collision) highlighting. The PDF uses a portrait A4
layout with one game card per game.

### Kapitän (team lead) assignments

Each team can assign one kid as "Kapitän" for the whole calendar week
(Monday–Sunday) in which a game takes place. Both files are gitignored (they
contain kid names):

- `roster.json` — the kid per team that can be on duty:

```json
{
  "teams": {
    "TSV Gilching/Argelsried u13-2": ["Lena", "Max", "Noah"]
  }
}
```

- `kapitane.json` — the week→kid assignments (created/filled by
  `--captains-assign`, individual weeks stay hand-editable):

```json
{
  "assignments": {
    "TSV Gilching/Argelsried u13-2": { "2026-39": "Lena", "2026-40": "Max" }
  }
}
```

- `--captains-assign` loads the current CSVs and fills any duty week that has an
  upcoming game but no captain yet — round-robin, always giving the week to the
  kid with the fewest appointments (fair by construction). Weeks you filled by
  hand are never overwritten.
- `--captains-check` counts, per team, how many weeks each kid is on duty (only
  weeks with an actual game count) and reports `gleichmäßig` when no kid has more
  than one duty week more than another. It flags missing assignments, kids not in
  the roster and missing rosters, and exits with code 1 when anything is off.
- The `--team` PDF then shows the captain on each game card:
  `Kapitän der Woche · Lena · Mo 07.09. – So 13.09.` A configured team without an
  assignment shows `Kapitän der Woche · folgt` until `--captains-assign` is run.

### Training attendance (Anwesenheit)

Each training session records one status per kid: **P** (anwesend),
**S** (krank), **A** (abwesend), **N** (keine Rückmeldung). The data lives in
`anwesenheit.json` (gitignored, kid names) — copy the attendance list from the
BFV team app and maintain it by hand:

```json
{
  "sessions": [
    { "date": "2026-09-07", "team": "TSV Gilching/Argelsried u13-2",
      "values": { "Lena": "P", "Max": "S", "Noah": "N" } }
  ]
}
```

- Scaffold a new session from the roster (no typing needed, everyone starts as
  `N`, you only set the exceptions; duplicate team+date is skipped with a
  warning):
  ```bash
  python3 anwesenheit.py --new --team "TSV Gilching/Argelsried u13-2" --date 2026-09-21
  ```
- Render the evaluation PDF (stats work standalone, no game CSVs required):
  ```bash
  python3 visualize_spiele.py --anwesenheit
  # only one team / custom output:
  python3 visualize_spiele.py --anwesenheit --team "TSV Gilching/Argelsried u13-2" --out team.pdf
  # combined view: fold sickness into the A column, show only the Quote P rate:
  python3 visualize_spiele.py --anwesenheit --kombiniert
  ```
- The A4 PDF shows one table per team: `Spieler | Termine | P | S | A | N |
  Quote P | Quote P+S` plus a totals row. `Quote P` = `P / total`,
  `Quote P+S` = `(P+S) / total` — `N` counts toward the total, so missing
  feedback lowers the quota. Dates are accepted as `2026-09-21` or `21.09.2026`,
  unknown status letters are reported and counted as `N`.
- With `--kombiniert` the table folds sickness into the `A` column and shows
  only `Quote P` (= `P / total`): sick is treated as absent, and the sick
  status is not mentioned at all — the legend lists just `P`, `A` and `N`. If
  you prefer a single headline number per kidaches, this variant is the compact
  one.

### Lineup sheet (Aufstellung)

`python3 visualize_spiele.py --aufstellung --team <Name/Alias> [--date YYYY-MM-DD]`
renders a one-page A4 lineup sheet for a single game. The lineups live in
`aufstellungen.json` (gitignored, kid names); see `aufstellungen.example.json`:

```json
{
  "spiele": [
    {
      "team": "TSV Gilching/Argelsried u13-2",
      "date": "2026-10-03",
      "system": "3-2-1",
      "aufgebot": { "Lukas": 1, "Leon": 3, "Paul": 7, "Tim": 8 },
      "startelf": [
        { "name": "Lukas", "pos": "Tor" },
        { "name": "Leon", "pos": "IV" },
        { "name": "Paul", "pos": "LV" }
      ],
      "bank": ["Tim"],
      "notizen_team": ["Bälle nicht vergessen!"],
      "notizen_spieler": { "Lukas": ["Nagelschuhe mitbringen"] }
    }
  ]
}
```

- A game is identified by `team` (alias or original BFV name, case-insensitive)
  plus `date` (`2026-10-03` or `03.10.2026`). Without `--date` the next upcoming
  game with a lineup is used. `--out` overrides the output path.
- Opponent, kickoff, home/away and competition come from the fetched CSVs. The
  **Treffpunkt** is always one hour before kickoff; the **Kapitän der Woche**
  comes from `kapitane.json`. When there is no matching game or captain, the
  sheet shows `Gegner unbekannt` / `-`.
- Each starter is drawn on the pitch at the spot of their position code, with
  their shirt number from `aufgebot`. Supported codes (case-insensitive):
  `Tor`/`TW`, `LV`, `IV`, `RV`, `6er`/`ZDM`, `ZM`, `LM`, `RM`, `8er`,
  `10er`/`ZOM`, `LF`, `RF`, `LA`, `RA`, `9er`/`ST`/`MS`. Several players with the
  same code (e.g. three `IV`) are placed side by side in `startelf` order.
- The side column lists the bench (`Bank (n)`) and the team notes (`Hinweise`).
  The per-player notes go into the `Notizen` box, followed by blank lines for
  handwritten notes.
- The club logo is downloaded once from BFV (`CLUB_LOGO_URL` in `config.py`) and
  cached in `.bfv_cache/`; offline, the sheet renders without it.
- Inconsistencies are printed as warnings: a player without a shirt number,
  a starting-lineup size that does not match the system (`3-2-1` = 7 players
  including the keeper), duplicate shirt numbers, a player in both the starting
  lineup and on the bench, nominated players who are in neither, notes for
  unknown players, and unknown position codes (plain `AV` asks for `LV` or `RV`).

### Add a team

Add the team's BFV URL (e.g. `https://www.bfv.de/mannschaften/.../<id>`) as a
new object in `teams.json`, optionally with an `alias`, then run `--refresh`.

## Output

- `*_spiele_web.csv` — raw data per team
  (columns `Wettbewerb,Datum,Uhrzeit,Heim,Gast,Spielort,Link,Quelle`, UTF-8 with BOM)
- `spielplan.html` — interactive overview: team filter, hide past games,
  same-day badge (always shown for days with multiple games), amber header
  highlighting only when 2+ selected teams play on the same day, map/match
  links, URL preselect (`?team=<Name>`), and `.ics` calendar export
- `spielplan.pdf` — printable multi-page overview
- `<slug>_monthly.pdf` — single-team overview of the next games (from `--team`)
- `kapitane.json` / `roster.json` — Kapitän duty assignments and team rosters
  (from `--captains-assign`, kid names stay local)
- `anwesenheit.pdf` — training attendance evaluation (from `--anwesenheit`,
  `anwesenheit.json` is the hand-maintained source data)
- `<slug>_aufstellung_<date>.pdf` — lineup sheet of one game (from
  `--aufstellung`, `aufstellungen.json` is the hand-maintained source data)

## Tests

```bash
.venv/bin/python -m pytest -v   # Python unit tests (176)
node test/spielplan.test.mjs    # JS harness for the embedded filter/export code (needs Node >= 18)
```

## Project layout

- `config.py` — shared constants (`CLUB_MARKERS`, `PALETTE`, date format, …)
- `teams.json` — team config: BFV URLs and optional display aliases
- `fetch_bfv_spielplan.py` — BFV fetcher (single fetch + `--refresh`)
- `visualize_spiele.py` — HTML/PDF generator
- `anwesenheit.py` — training attendance data, stats, PDF and `--new` scaffolding
- `aufstellung.py` — lineup data, validation, pitch placement and lineup PDF
- `reports/` — project reports (history and design decisions)
