"""Game data model and CSV loading.

Provides ``Game``, ``Source`` and functions to load, filter and group
games from the ``*_spiele_web.csv`` files produced by
``fetch_bfv_spielplan.py``.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from config import CLUB_MARKERS, PALETTE, SCRIPT_DIR
from util import game_sort_key, parse_date


class Source(TypedDict, total=False):
    """A source file entry with team name and BFV URL."""

    file: str
    team: str
    url: str
    original: str


class Game(TypedDict):
    """A parsed game record."""

    date: datetime
    datum: str
    wd: str
    time: str
    heim: str
    gast: str
    wettbewerb: str
    spielort: str
    link: str
    quelle: str
    source: str
    is_home: bool
    home_color: str
    away_color: str


def load_alias_map(teams_path: Path | None = None) -> dict[str, str]:
    """Build a mapping of BFV team URL -> display alias from teams.json."""
    path = teams_path or SCRIPT_DIR / "teams.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        str(entry["url"]): str(entry["alias"])
        for entry in data
        if isinstance(entry, dict) and entry.get("url") and entry.get("alias")
    }


def team_color(name: str) -> str:
    """Return a deterministic color for a team name."""
    if not name:
        return "#888888"
    return PALETTE[sum(ord(c) for c in name) % len(PALETTE)]


def slugify(name: str) -> str:
    """Slugify a team name for filenames, mirroring the .ics export slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def resolve_team(sources: list[Source], arg: str) -> Source:
    """Return the source whose alias or original BFV name matches ``arg``."""
    import sys

    lowered = arg.lower()
    matches = [
        s
        for s in sources
        if s["team"].lower() == lowered or (s.get("original") or "").lower() == lowered
    ]
    if not matches:
        available = sorted({s["team"] for s in sources})
        sys.exit(
            f"Team '{arg}' nicht gefunden. Verfügbare Teams: {', '.join(available) or 'keine'}"
        )
    if len(matches) > 1:
        sys.exit(
            f"Team '{arg}' ist nicht eindeutig. Gemeint: "
            f"{', '.join(m['team'] for m in matches)}"
        )
    return matches[0]


def next_games_for_team(
    games: list[Game], team: str, num: int, today: datetime | None = None
) -> list[Game]:
    """Return the next ``num`` upcoming games involving ``team``, sorted."""
    today = today or datetime.now()
    upcoming = [
        g
        for g in games
        if (g["heim"] == team or g["gast"] == team)
        and (g["date"].date() if isinstance(g["date"], datetime) else g["date"])
        >= today.date()
    ]
    upcoming.sort(key=game_sort_key)
    return upcoming[:num]


def infer_team(
    file_games: list[Game], source_file: str, first_quelle: str
) -> tuple[str, Source]:
    """Infer the club team name from game appearances and return source info."""
    counts: Counter[str] = Counter()
    for g in file_games:
        counts[g["heim"]] += 1
        counts[g["gast"]] += 1
    team = max(counts, key=lambda t: counts[t])
    full = next((t for t, c in counts.items() if c == len(file_games)), team)
    return full, Source(file=source_file, team=full, url=first_quelle)


def load_games(
    alias_map: dict[str, str] | None = None,
) -> tuple[list[Game], list[str], list[Source]]:
    """Load all games from *_spiele_web.csv files.

    When ``alias_map`` (URL -> display alias) contains the source URL of a
    file, the club team's name is replaced by the alias in every game.
    """
    if alias_map is None:
        alias_map = load_alias_map()
    games: list[Game] = []
    club_teams: list[str] = []
    sources: list[Source] = []
    for path in sorted(SCRIPT_DIR.glob("*_spiele_web.csv")):
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as exc:
            print(f"Warnung: {path.name} nicht lesbar ({exc})", file=sys.stderr)
            continue
        file_games: list[Game] = []
        skipped = 0
        skipped_teams = 0
        for r in rows:
            d = parse_date(r.get("Datum", ""))
            if d is None:
                skipped += 1
                continue
            heim = (r.get("Heim") or "").strip()
            gast = (r.get("Gast") or "").strip()
            if not heim or not gast:
                skipped_teams += 1
                continue
            home_l = heim.lower()
            file_games.append(
                Game(
                    date=datetime(d.year, d.month, d.day),
                    datum=d.strftime("%d.%m.%Y"),
                    wd=WD[d.weekday()],
                    time=(r.get("Uhrzeit") or "").strip(),
                    heim=heim,
                    gast=gast,
                    wettbewerb=(r.get("Wettbewerb") or "").strip(),
                    spielort=(r.get("Spielort") or "").strip(),
                    link=(r.get("Link") or "").strip(),
                    quelle=(r.get("Quelle") or "").strip(),
                    source=path.name,
                    is_home=any(m in home_l for m in CLUB_MARKERS),
                    home_color=team_color(heim),
                    away_color=team_color(gast),
                )
            )
        if skipped:
            print(
                f"Warnung: {skipped} Zeile(n) in {path.name} wegen ungültigen Datums übersprungen",
                file=sys.stderr,
            )
        if skipped_teams:
            print(
                f"Warnung: {skipped_teams} Zeile(n) in {path.name} ohne Heim/Gast-Team übersprungen",
                file=sys.stderr,
            )
        games.extend(file_games)
        if file_games:
            team, source = infer_team(
                file_games, path.name, file_games[0].get("quelle", "")
            )
            source["original"] = source["team"]
            alias = alias_map.get(source["url"])
            if alias:
                for g in file_games:
                    if g["heim"] == source["original"]:
                        g["heim"] = alias
                        g["home_color"] = team_color(alias)
                    if g["gast"] == source["original"]:
                        g["gast"] = alias
                        g["away_color"] = team_color(alias)
                source["team"] = alias
            club_teams.append(source["team"])
            sources.append(source)
    return games, club_teams, sources


def group_by_day(games: list[Game]) -> OrderedDict[str, list[Game]]:
    """Group games by date, sorted by date then time."""
    games.sort(key=game_sort_key)
    days: OrderedDict[str, list[Game]] = OrderedDict()
    for g in games:
        days.setdefault(g["datum"], []).append(g)
    return days


def short_place(spielort: str, limit: int = 45) -> str:
    """Shorten a location string, replacing pipes with commas."""
    import re

    s = re.sub(r"\s*\|\s*", ", ", spielort)
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


def find_team_game(games: list[Game], team: str, day: datetime) -> Game | None:
    """Return the (earliest) game of ``team`` on the given day, if any."""
    matches = [
        g
        for g in games
        if (g["heim"] == team or g["gast"] == team) and g["date"].date() == day.date()
    ]
    matches.sort(key=lambda g: g["time"] or "99:99")
    return matches[0] if matches else None


# Day-of-week lookup (imported from config in the original module)
WD: list[str] = [
    "Mo",
    "Di",
    "Mi",
    "Do",
    "Fr",
    "Sa",
    "So",
]
