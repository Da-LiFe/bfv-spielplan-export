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


WEB_SUFFIX = "_spiele_web.csv"
ZUSATZ_SUFFIX = "_zusatz_spiele.csv"


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


def slug_from_url(url: str) -> str:
    """Return the BFV slug (the second-to-last path segment) of a team URL."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-2] if len(parts) >= 2 else ""


def load_team_slugs(teams_path: Path | None = None) -> dict[str, dict[str, str]]:
    """Map BFV team slug -> ``{"alias", "url"}`` from teams.json.

    The slug is the same one the fetcher uses for the CSV filename, so a
    ``<slug>_zusatz_spiele.csv`` file can be tied back to its team.
    """
    path = teams_path or SCRIPT_DIR / "teams.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    slugs: dict[str, dict[str, str]] = {}
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        url = str(entry["url"])
        slug = slug_from_url(url)
        if slug:
            slugs[slug] = {"alias": str(entry.get("alias") or slug), "url": url}
    return slugs


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


def _read_games(path: Path) -> list[Game]:
    """Parse one schedule CSV (fetched or ``_zusatz_spiele``) into games."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as exc:
        print(f"Warnung: {path.name} nicht lesbar ({exc})", file=sys.stderr)
        return []
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
    return file_games


# One file's games, its inferred source and whether it is a manual file.
Entry = tuple[list[Game], Source, bool]


def _load_fetched(alias_map: dict[str, str]) -> list[Entry]:
    """Load every ``*_spiele_web.csv`` file, aliasing each team's own name."""
    entries: list[Entry] = []
    for path in sorted(SCRIPT_DIR.glob(f"*{WEB_SUFFIX}")):
        file_games = _read_games(path)
        if not file_games:
            continue
        _, source = infer_team(file_games, path.name, file_games[0].get("quelle", ""))
        source["original"] = source["team"]
        alias = alias_map.get(source["url"])
        if alias:
            source["team"] = alias
        entries.append((file_games, source, False))
    return entries


def _load_zusatz(entries: list[Entry]) -> list[Entry]:
    """Load ``<slug>_zusatz_spiele.csv`` files (hand-maintained, refresh-safe).

    A missing slug in ``teams.json`` is an error: the file cannot be tied to a
    team, so the team's alias and source link would be guessed.
    """
    paths = sorted(SCRIPT_DIR.glob(f"*{ZUSATZ_SUFFIX}"))
    if not paths:
        return []
    original_by_url = {
        s["url"]: s["original"] for _fg, s, is_extra in entries if not is_extra
    }
    slugs = load_team_slugs()
    extra: list[Entry] = []
    for path in paths:
        slug = path.name[: -len(ZUSATZ_SUFFIX)]
        info = slugs.get(slug)
        if info is None:
            sys.exit(
                f"{path.name}: kein Team mit dem Slug '{slug}' in teams.json. "
                "Lege das Team dort zuerst an."
            )
        file_games = _read_games(path)
        if not file_games:
            continue
        source = Source(
            file=path.name,
            team=info["alias"],
            original=original_by_url.get(info["url"], info["alias"]),
            url=info["url"],
        )
        extra.append((file_games, source, True))
    return extra


def _merge_games(entries: list[Entry]) -> list[Game]:
    """Merge all entries, deduplicating games that appear in two CSVs.

    Fetched games (pass 1) dedupe on the raw BFV names, which are identical in
    both teams' files; the kept copy then gets both aliases. Manual
    ``_zusatz_spiele`` games (pass 2) are compared against the final, aliased
    games: a duplicate is an error, because the fetch now lists the game too.
    """
    unique: list[Game] = []
    seen: dict[tuple, Game] = {}
    for file_games, source, is_extra in entries:
        if is_extra:
            continue
        for g in file_games:
            key = (
                ("link", g["link"])
                if g["link"]
                else ("fallback", g["datum"], g["time"], g["heim"], g["gast"])
            )
            kept = seen.get(key)
            if kept is None:
                seen[key] = kept = g
                unique.append(g)
            _rename_team(kept, source["original"], source["team"])

    by_link = {("link", g["link"]): g for g in unique if g["link"]}
    by_fallback = {
        ("fallback", g["datum"], g["time"], g["heim"], g["gast"]): g for g in unique
    }
    for file_games, source, is_extra in entries:
        if not is_extra:
            continue
        for g in file_games:
            _rename_team(g, source["original"], source["team"])
            link_key = ("link", g["link"]) if g["link"] else None
            fallback_key = ("fallback", g["datum"], g["time"], g["heim"], g["gast"])
            kept = (by_link.get(link_key) if link_key else None) or by_fallback.get(
                fallback_key
            )
            if kept is not None:
                sys.exit(
                    f"{source['file']}: {g['datum']} {g['time']} {g['heim']} "
                    f"\u2013 {g['gast']} steht schon in {kept['source']} \u2013 "
                    "die Zeile in der Zusatzdatei bitte entfernen."
                )
            if link_key:
                by_link[link_key] = g
            by_fallback[fallback_key] = g
            unique.append(g)
    return unique


def load_games(
    alias_map: dict[str, str] | None = None,
) -> tuple[list[Game], list[str], list[Source]]:
    """Load all games from the fetched CSVs and the ``_zusatz_spiele`` files.

    When ``alias_map`` (URL -> display alias) contains the source URL of a
    file, the club team's name is replaced by the alias in that file's games.
    Extra games live in ``<slug>_zusatz_spiele.csv`` files that ``fetch`` never
    writes, so they survive ``--refresh``.
    """
    if alias_map is None:
        alias_map = load_alias_map()
    fetched = _load_fetched(alias_map)
    entries = fetched + _load_zusatz(fetched)
    return _merge_with_sources(entries)


def _merge_with_sources(
    entries: list[Entry],
) -> tuple[list[Game], list[str], list[Source]]:
    """Merge games and collect one source/team per distinct team (in order)."""
    games = _merge_games(entries)
    club_teams: list[str] = []
    sources: list[Source] = []
    seen: set[str] = set()
    for _file_games, source, _is_extra in entries:
        team = source["team"]
        if team not in seen:
            seen.add(team)
            club_teams.append(team)
            sources.append(source)
    return games, club_teams, sources


def _rename_team(g: Game, original: str, alias: str) -> None:
    """Replace ``original`` by ``alias`` as home or away team of ``g``."""
    if g["heim"] == original:
        g["heim"] = alias
        g["home_color"] = team_color(alias)
    if g["gast"] == original:
        g["gast"] = alias
        g["away_color"] = team_color(alias)


def group_by_day(games: list[Game]) -> OrderedDict[str, list[Game]]:
    """Group games by date, sorted by date then time."""
    sorted_games = sorted(games, key=game_sort_key)
    days: OrderedDict[str, list[Game]] = OrderedDict()
    for g in sorted_games:
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
