"""Match-day lineup sheet ("Aufstellung") for a single game.

Lineups live in ``aufstellungen.json`` (gitignored, contains kid names) and
are identified by team (alias or original BFV name) plus ISO date. Each entry
lists the nominated squad with shirt numbers (``aufgebot``), the starting
players with their position code (``startelf``), the bench (``bank``), general
team notes (``notizen_team``) and notes for single players
(``notizen_spieler``).

The opponent, kickoff, competition and venue come from the fetched game CSVs;
the meeting time ("Treffpunkt") is always one hour before kickoff and the
"Kapitän der Woche" is looked up in ``kapitane.json``. The PDF is a single A4
page with header (club, opponent, date, venue address with a clickable map
link), info box, a pitch with every starter on their position spot, bench and
team notes, and a notes box with the per-player notes.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
)

import kapitane
from config import (
    CLUB_LOGO_URL,
    CLUB_NAME,
    LINK_COLOR,
    MONTHS_DE,
    SCRIPT_DIR,
    WEEKDAYS_DE,
)
from pdf_common import BOLD_FONT, FONT
from util import esc, load_json_strict, maps_url, parse_date, place_text, write_json

AUFSTELLUNGEN_NAME = "aufstellungen.json"
DEFAULT_PATH = SCRIPT_DIR / AUFSTELLUNGEN_NAME
LOGO_CACHE_PATH = SCRIPT_DIR / ".bfv_cache" / "club_logo.png"
LOGO_CACHE_TTL = 30 * 24 * 3600  # the club logo hardly ever changes
MEETING_OFFSET = timedelta(hours=1)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) spielplan-aufstellung"

ACCENT = "#e5323b"
INK = "#222222"
MUTED = "#6b7280"
PITCH_BG = "#f4f5f9"
PITCH_LINE = "#b8bec9"

# Position code (upper case) -> spot on the pitch as (x, y) fractions of the
# playing field. x runs from the left to the right touchline, y from the own
# goal line (0, bottom of the page) to the opponent's goal line (1).
POSITIONS: dict[str, tuple[float, float]] = {
    "TOR": (0.5, 0.06),
    "TW": (0.5, 0.06),
    "LV": (0.14, 0.24),
    "IV": (0.5, 0.2),
    "RV": (0.86, 0.24),
    "6ER": (0.5, 0.4),
    "ZDM": (0.5, 0.4),
    "ZM": (0.5, 0.5),
    "LM": (0.14, 0.52),
    "RM": (0.86, 0.52),
    "8ER": (0.5, 0.56),
    "10ER": (0.5, 0.66),
    "ZOM": (0.5, 0.66),
    "LF": (0.16, 0.74),
    "RF": (0.84, 0.74),
    "LA": (0.16, 0.78),
    "RA": (0.84, 0.78),
    "9ER": (0.5, 0.84),
    "ST": (0.5, 0.84),
    "MS": (0.5, 0.84),
}

# Compact 7v7 positions (3-2-1): attackers pulled closer to midfield
POSITIONS_7V7: dict[str, tuple[float, float]] = {
    "TOR": (0.5, 0.07),
    "TW": (0.5, 0.07),
    "LV": (0.14, 0.24),
    "IV": (0.5, 0.2),
    "RV": (0.86, 0.24),
    "6ER": (0.5, 0.4),
    "ZDM": (0.5, 0.4),
    "ZM": (0.5, 0.48),
    "LM": (0.14, 0.48),
    "RM": (0.86, 0.48),
    "8ER": (0.5, 0.48),
    "10ER": (0.5, 0.5),
    "ZOM": (0.5, 0.5),
    "LF": (0.16, 0.50),
    "RF": (0.84, 0.50),
    "LA": (0.16, 0.58),
    "RA": (0.84, 0.58),
    "9ER": (0.5, 0.58),
    "ST": (0.5, 0.58),
    "MS": (0.5, 0.58),
}
GOALKEEPER_CODES = {"TOR", "TW"}
AMBIGUOUS_POSITIONS = {"AV": "LV oder RV"}
UNKNOWN_ROW_Y = 0.5
SPREAD = 0.22  # horizontal distance between players sharing a position code


@dataclass
class Starter:
    """A starting player with the position code as written in the JSON."""

    name: str
    pos: str


@dataclass
class Lineup:
    """One game's lineup as read from ``aufstellungen.json``."""

    team: str
    date: date
    system: str = ""
    aufgebot: dict[str, int] = field(default_factory=dict)
    startelf: list[Starter] = field(default_factory=list)
    bank: list[str] = field(default_factory=list)
    notizen_team: list[str] = field(default_factory=list)
    notizen_spieler: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class GameInfo:
    """The fetched schedule data of the game a lineup belongs to."""

    opponent: str
    kickoff: str = ""
    competition: str = ""
    is_home: bool = False
    spielort: str = ""


@dataclass
class PlacedPlayer:
    """A starter with shirt number and computed pitch coordinates."""

    name: str
    pos: str
    number: int | None
    x: float
    y: float


def german_date(d: date) -> str:
    """Render a date as 'Samstag, 2. Mai 2026'."""
    return f"{WEEKDAYS_DE[d.weekday()]}, {d.day}. {MONTHS_DE[d.month - 1]} {d.year}"


def _str_list(value: Any) -> list[str]:
    """Coerce a JSON value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def normalize_entry(raw: Any, index: int) -> tuple[Lineup | None, list[str]]:
    """Convert one raw JSON game entry into a ``Lineup`` plus warnings."""
    where = f"{AUFSTELLUNGEN_NAME}: Eintrag {index}"
    if not isinstance(raw, dict):
        return None, [f"{where} ist kein Objekt – übersprungen."]
    team = str(raw.get("team", "")).strip()
    if not team:
        return None, [f"{where} ohne Team – übersprungen."]
    d = parse_date(raw.get("date"))
    if d is None:
        return None, [f"{where}: ungültiges Datum '{raw.get('date')}' – übersprungen."]

    warnings: list[str] = []
    aufgebot: dict[str, int] = {}
    raw_aufgebot = raw.get("aufgebot")
    if isinstance(raw_aufgebot, dict):
        for name, number in raw_aufgebot.items():
            try:
                aufgebot[str(name).strip()] = int(number)
            except (TypeError, ValueError):
                warnings.append(
                    f"{where}: ungültige Rückennummer '{number}' für {name}."
                )
    startelf: list[Starter] = []
    raw_startelf = raw.get("startelf")
    if isinstance(raw_startelf, list):
        for item in raw_startelf:
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                startelf.append(
                    Starter(
                        name=str(item["name"]).strip(),
                        pos=str(item.get("pos", "")).strip(),
                    )
                )
            else:
                warnings.append(f"{where}: ungültiger Startelf-Eintrag {item!r}.")
    notizen_spieler: dict[str, list[str]] = {}
    raw_notes = raw.get("notizen_spieler")
    if isinstance(raw_notes, dict):
        for name, notes in raw_notes.items():
            items = [notes] if isinstance(notes, str) else notes
            cleaned = _str_list(items)
            if cleaned:
                notizen_spieler[str(name).strip()] = cleaned

    lineup = Lineup(
        team=team,
        date=d,
        system=str(raw.get("system", "")).strip(),
        aufgebot=aufgebot,
        startelf=startelf,
        bank=_str_list(raw.get("bank")),
        notizen_team=_str_list(raw.get("notizen_team")),
        notizen_spieler=notizen_spieler,
    )
    return lineup, warnings


def normalize_data(raw: Any) -> tuple[list[Lineup], list[str]]:
    """Coerce arbitrary JSON into lineups; malformed entries become warnings."""
    raw_games = raw.get("spiele") if isinstance(raw, dict) else None
    if not isinstance(raw_games, list):
        return [], [f"{AUFSTELLUNGEN_NAME}: 'spiele' fehlt oder ist keine Liste."]
    lineups: list[Lineup] = []
    warnings: list[str] = []
    for i, entry in enumerate(raw_games):
        lineup, entry_warnings = normalize_entry(entry, i)
        warnings.extend(entry_warnings)
        if lineup is not None:
            lineups.append(lineup)
    return lineups, warnings


def load_lineups(path: Path | None = None) -> tuple[list[Lineup], list[str]]:
    """Load ``aufstellungen.json``; invalid JSON raises ``SystemExit``."""
    file_path = path or DEFAULT_PATH
    if not file_path.exists():
        return [], [f"{file_path.name} nicht gefunden."]
    raw = load_json_strict(file_path)
    lineups, warnings = normalize_data(raw)
    if not lineups and warnings:
        sys.exit(f"{file_path.name}: {warnings[0]}")
    return lineups, warnings


def lineups_for_team(lineups: list[Lineup], names: set[str]) -> list[Lineup]:
    """Return the lineups whose team matches one of ``names`` (case-insensitive)."""
    lowered = {n.lower() for n in names}
    return sorted(
        (lu for lu in lineups if lu.team.lower() in lowered), key=lambda lu: lu.date
    )


def select_lineup(
    lineups: list[Lineup], day: date | None, today: date | None = None
) -> Lineup | None:
    """Pick the lineup on ``day``, or the next upcoming one when ``day`` is None."""
    if day is not None:
        return next((lu for lu in lineups if lu.date == day), None)
    today = today or datetime.now().date()
    upcoming = [lu for lu in lineups if lu.date >= today]
    return min(upcoming, key=lambda lu: lu.date) if upcoming else None


def system_size(system: str) -> int | None:
    """Return the number of players for a formation like '3-2-1' (incl. keeper)."""
    parts = re.split(r"\s*-\s*", system.strip())
    if not system.strip() or not all(p.isdigit() for p in parts):
        return None
    return sum(int(p) for p in parts) + 1


def meeting_time(kickoff: str) -> str:
    """Return the meeting time one hour before ``kickoff`` ('' if unknown)."""
    try:
        start = datetime.strptime(kickoff.strip(), "%H:%M")
    except ValueError:
        return ""
    return (start - MEETING_OFFSET).strftime("%H:%M")


def validate(lineup: Lineup) -> list[str]:
    """Return human-readable warnings about inconsistencies in ``lineup``."""
    warnings: list[str] = []
    starters = [s.name for s in lineup.startelf]
    squad = set(lineup.aufgebot)

    for name in starters:
        if name not in squad:
            warnings.append(f"{name} (Startelf) hat keine Rückennummer im Aufgebot.")
    for name in lineup.bank:
        if name not in squad:
            warnings.append(f"{name} (Bank) hat keine Rückennummer im Aufgebot.")

    seen: set[str] = set()
    for name in starters:
        if name in seen:
            warnings.append(f"{name} steht mehrfach in der Startelf.")
        seen.add(name)
    for name in sorted(set(starters) & set(lineup.bank)):
        warnings.append(f"{name} steht in Startelf und auf der Bank.")

    placed = set(starters) | set(lineup.bank)
    for name in lineup.aufgebot:
        if name not in placed:
            warnings.append(f"{name} ist nominiert, aber weder in Startelf noch Bank.")

    by_number: dict[int, list[str]] = {}
    for name, number in lineup.aufgebot.items():
        by_number.setdefault(number, []).append(name)
    for number, names in sorted(by_number.items()):
        if len(names) > 1:
            warnings.append(f"Rückennummer {number} doppelt: {', '.join(names)}.")

    expected = system_size(lineup.system)
    if lineup.system and expected is None:
        warnings.append(f"System '{lineup.system}' nicht lesbar (erwartet z.B. 3-2-1).")
    elif expected is not None and expected != len(starters):
        warnings.append(
            f"System {lineup.system} braucht {expected} Spieler, "
            f"Startelf hat {len(starters)}."
        )

    for s in lineup.startelf:
        code = s.pos.upper()
        if code in POSITIONS:
            continue
        hint = AMBIGUOUS_POSITIONS.get(code)
        if hint:
            warnings.append(f"Position '{s.pos}' bei {s.name} ist mehrdeutig – {hint}.")
        else:
            warnings.append(f"Unbekannte Position '{s.pos}' bei {s.name}.")

    for name in lineup.notizen_spieler:
        if name not in squad and name not in placed:
            warnings.append(f"Notiz für {name}, der nicht im Aufgebot steht.")
    return warnings


def _is_7v7(lineup: Lineup) -> bool:
    """Return True if the lineup uses a 7v7 system (7 players incl. keeper)."""
    size = system_size(lineup.system)
    return size is not None and size == 7


def place_players(lineup: Lineup) -> list[PlacedPlayer]:
    """Compute pitch coordinates for every starter from their position code.

    Players sharing a code (e.g. three IV) are spread horizontally around the
    code's spot in ``startelf`` order; unknown codes go to a row in midfield.
    7v7 lineups use compact positions with attackers closer to midfield.
    """
    positions_map = POSITIONS_7V7 if _is_7v7(lineup) else POSITIONS
    groups: dict[str, list[Starter]] = {}
    for s in lineup.startelf:
        code = s.pos.upper()
        key = code if code in positions_map else "?"
        groups.setdefault(key, []).append(s)
    placed: list[PlacedPlayer] = []
    for key, members in groups.items():
        base_x, base_y = positions_map.get(key, (0.5, UNKNOWN_ROW_Y))
        if _is_7v7(lineup):
            spread = 0.8 / max(len(members), 1)
        else:
            spread = SPREAD if key != "?" else 0.8 / max(len(members), 1)
        n = len(members)
        for i, s in enumerate(members):
            x = base_x + (i - (n - 1) / 2) * spread
            placed.append(
                PlacedPlayer(
                    name=s.name,
                    pos=s.pos,
                    number=lineup.aufgebot.get(s.name),
                    x=min(max(x, 0.08), 0.92),
                    y=base_y,
                )
            )
    return placed


def _download(url: str) -> bytes:
    """Fetch ``url`` and return the raw body."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return bytes(resp.read())


def get_logo(
    url: str = CLUB_LOGO_URL,
    cache_path: Path = LOGO_CACHE_PATH,
    ttl: float = LOGO_CACHE_TTL,
) -> Path | None:
    """Return a local copy of the club logo, downloading it when stale.

    A stale cached copy is still used when the download fails; without any
    copy the PDF simply renders without a logo.
    """
    if cache_path.exists() and time.time() - cache_path.stat().st_mtime <= ttl:
        return cache_path
    try:
        data = _download(url)
        if not data.startswith(PNG_MAGIC):
            raise ValueError("keine PNG-Datei")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"Warnung: Vereinslogo nicht geladen ({exc}).", file=sys.stderr)
        return cache_path if cache_path.exists() else None
    return cache_path


class PitchFlowable(Flowable):
    """A football pitch with every starter drawn on their position spot."""

    def __init__(self, players: list[PlacedPlayer], width: float, height: float):
        super().__init__()
        self.players = players
        self.width = width
        self.height = height

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return self.width, self.height

    def _fit_font(self, text: str, font: str, size: float, max_w: float) -> float:
        while size > 5.5 and pdfmetrics.stringWidth(text, font, size) > max_w:
            size -= 0.5
        return size

    def draw(self) -> None:
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(colors.HexColor(PITCH_BG))
        c.roundRect(0, 0, w, h, 3 * mm, stroke=0, fill=1)

        pad = 5 * mm
        fx, fy, fw, fh = pad, pad, w - 2 * pad, h - 2 * pad
        c.setStrokeColor(colors.HexColor(PITCH_LINE))
        c.setLineWidth(0.8)
        c.rect(fx, fy, fw, fh, stroke=1, fill=0)
        c.line(fx, fy + fh / 2, fx + fw, fy + fh / 2)
        c.circle(fx + fw / 2, fy + fh / 2, fw * 0.14, stroke=1, fill=0)
        box_w, box_h = fw * 0.56, fh * 0.13
        goal_w, goal_h = fw * 0.3, fh * 0.05
        for base, sign in ((fy, 1), (fy + fh, -1)):
            c.rect(fx + (fw - box_w) / 2, base, box_w, sign * box_h, stroke=1, fill=0)
            c.rect(
                fx + (fw - goal_w) / 2, base, goal_w, sign * goal_h, stroke=1, fill=0
            )

        radius = 4.6 * mm
        label_w = 30 * mm
        for p in self.players:
            cx = fx + p.x * fw
            cy = fy + p.y * fh + 3 * mm
            c.setFillColor(colors.HexColor(ACCENT))
            c.circle(cx, cy, radius, stroke=0, fill=1)
            c.setFillColor(colors.white)
            number = str(p.number) if p.number is not None else "?"
            c.setFont(BOLD_FONT, 11)
            c.drawCentredString(cx, cy - 3.8, number)
            name_size = self._fit_font(p.name, BOLD_FONT, 8.5, label_w)
            name_w = pdfmetrics.stringWidth(p.name, BOLD_FONT, name_size)
            c.setFillColor(colors.HexColor(PITCH_BG))
            c.rect(
                cx - name_w / 2 - 1,
                cy - radius - 7.2 * mm,
                name_w + 2,
                5.8 * mm,
                stroke=0,
                fill=1,
            )
            c.setFillColor(colors.HexColor(INK))
            c.setFont(BOLD_FONT, name_size)
            c.drawCentredString(cx, cy - radius - 3.6 * mm, p.name)
            c.setFillColor(colors.HexColor(MUTED))
            c.setFont(FONT, 6.5)
            c.drawCentredString(cx, cy - radius - 6.4 * mm, p.pos)


def _style(name: str, **kw: Any) -> ParagraphStyle:
    base: dict[str, Any] = {
        "fontName": FONT,
        "fontSize": 9,
        "leading": 12,
        "textColor": colors.HexColor(INK),
        "spaceAfter": 0,
    }
    base.update(kw)
    return ParagraphStyle(name, **base)


def _player_label(name: str, aufgebot: dict[str, int]) -> str:
    number = aufgebot.get(name)
    return f"#{number} {name}" if number is not None else name


def _address_paragraph(spielort: str, style: ParagraphStyle) -> Paragraph | None:
    """Build the address line with a clickable map link, or None if unknown."""
    text = place_text(spielort)
    if not text:
        return None
    href = maps_url(spielort)
    link = (
        f' · <link href="{esc(href)}"><font color="{LINK_COLOR}">Karte »</font></link>'
        if href
        else ""
    )
    return Paragraph(f"{esc(text)}{link}", style)


HEADER_LOGO_SIZE = 20 * mm


def header_subtitle_style() -> ParagraphStyle:
    """Grey style used for the info lines below the club header title."""
    return _style("su", fontSize=9.5, textColor=colors.HexColor(MUTED))


def build_club_header(
    title: str,
    sub_lines: list[Paragraph | str],
    logo: Path | None,
    content_w: float,
) -> Table:
    """Club-branded page header shared by all team PDFs.

    Club name overline, bold ``title``, grey ``sub_lines`` (plain strings are
    escaped, Paragraphs are used as given) and the club logo on the right,
    underlined by the red accent rule.
    """
    overline = _style("ov", fontSize=9, textColor=colors.HexColor(MUTED))
    title_style = _style("ti", fontName=BOLD_FONT, fontSize=18, leading=22)
    subtitle = header_subtitle_style()
    header_text: list[Paragraph] = [
        Paragraph(esc(CLUB_NAME), overline),
        Paragraph(esc(title), title_style),
    ]
    for line in sub_lines:
        header_text.append(
            line if isinstance(line, Paragraph) else Paragraph(esc(line), subtitle)
        )
    logo_cell: Any = ""
    if logo is not None:
        try:
            ImageReader(str(logo)).getSize()  # fail now, not during build()
            logo_cell = Image(
                str(logo), width=HEADER_LOGO_SIZE, height=HEADER_LOGO_SIZE
            )
        except Exception as exc:
            print(f"Warnung: Vereinslogo nicht lesbar ({exc}).", file=sys.stderr)
    return Table(
        [[header_text, logo_cell]],
        colWidths=[
            content_w - HEADER_LOGO_SIZE - 4 * mm,
            HEADER_LOGO_SIZE + 4 * mm,
        ],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -1), 2.2, colors.HexColor(ACCENT)),
        ],
    )


def build_lineup_pdf(
    lineup: Lineup,
    out_path: Path,
    game: GameInfo | None = None,
    captain: str = "",
    logo: Path | None = None,
) -> None:
    """Render the single-page lineup sheet for ``lineup`` to ``out_path``."""
    margin = 14 * mm
    content_w = A4[0] - 2 * margin

    subtitle = header_subtitle_style()
    label = _style("la", fontSize=8, leading=10, textColor=colors.HexColor(MUTED))
    value = _style("va", fontName=BOLD_FONT, fontSize=10, leading=13)
    heading = _style(
        "he",
        fontName=BOLD_FONT,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor(ACCENT),
        spaceBefore=2,
        spaceAfter=2,
    )
    body = _style("bo", fontSize=9, leading=12)

    opponent = game.opponent if game else "Gegner unbekannt"
    sub_parts = [german_date(lineup.date)]
    if game and game.kickoff:
        sub_parts.append(f"Anpfiff {game.kickoff} Uhr")
    if game:
        sub_parts.append("Heimspiel" if game.is_home else "Auswärtsspiel")
    sub_parts.append(lineup.team)
    if game and game.competition:
        sub_parts.append(game.competition)
    sub_lines: list[Paragraph | str] = [" · ".join(sub_parts)]
    address = _address_paragraph(game.spielort if game else "", subtitle)
    if address is not None:
        sub_lines.append(address)
    header = build_club_header(
        f"Spieltag — gegen {opponent}", sub_lines, logo, content_w
    )

    meet = meeting_time(game.kickoff) if game else ""
    info_items = [
        ("Treffpunkt", f"{meet} Uhr" if meet else "-"),
        ("Formation", lineup.system or "-"),
        ("Kapitän der Woche", captain or "-"),
        ("Kader", f"{len(lineup.startelf) + len(lineup.bank)} Spieler"),
    ]
    info = Table(
        [
            [Paragraph(esc(lbl), label) for lbl, _ in info_items],
            [Paragraph(esc(val), value) for _, val in info_items],
        ],
        colWidths=[content_w / len(info_items)] * len(info_items),
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(PITCH_BG)),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
            ("TOPPADDING", (0, 1), (-1, 1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ],
    )

    pitch_w, pitch_h = 112 * mm, 150 * mm
    pitch = PitchFlowable(place_players(lineup), pitch_w, pitch_h)
    side: list[Any] = [Paragraph(f"Bank ({len(lineup.bank)})", heading)]
    if lineup.bank:
        side += [
            Paragraph(esc(_player_label(n, lineup.aufgebot)), body) for n in lineup.bank
        ]
    else:
        side.append(Paragraph("–", body))
    side += [Spacer(1, 8), Paragraph("Hinweise", heading)]
    if lineup.notizen_team:
        side += [Paragraph(f"• {esc(n)}", body) for n in lineup.notizen_team]
    else:
        side.append(Paragraph("–", body))
    main = Table(
        [[pitch, side]],
        colWidths=[pitch_w + 6 * mm, content_w - pitch_w - 6 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ],
    )

    note_rows: list[list[Any]] = [[Paragraph("Notizen", heading)]]
    for name, notes in lineup.notizen_spieler.items():
        note_rows.append(
            [
                Paragraph(
                    f"<b>{esc(_player_label(name, lineup.aufgebot))}:</b> "
                    + " · ".join(esc(n) for n in notes),
                    body,
                )
            ]
        )
    # Fill the rest of the page with blank lines for handwritten notes.
    top_margin, bottom_margin = 12 * mm, 10 * mm
    frame_h = A4[1] - top_margin - bottom_margin - 12  # frame padding
    gap = 6
    used = 3 * gap
    for flowable in (header, info, main):
        used += flowable.wrap(content_w, frame_h)[1]
    notes_head = Table(
        note_rows,
        colWidths=[content_w],
        style=[
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
        ],
    )
    used += notes_head.wrap(content_w, frame_h)[1] + 2
    line_h = 7.5 * mm
    blank_lines = max(1, int((frame_h - used) // line_h))
    first_blank = len(note_rows)
    note_rows += [[""] for _ in range(blank_lines)]
    notes_box = Table(
        note_rows,
        colWidths=[content_w],
        rowHeights=[None] * first_blank + [line_h] * blank_lines,
        style=[
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#dfe3ea")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            (
                "LINEBELOW",
                (0, first_blank - 1),
                (-1, -2),
                0.5,
                colors.HexColor("#e3e6ec"),
            ),
        ],
    )

    story = [
        header,
        Spacer(1, gap),
        info,
        Spacer(1, gap),
        main,
        Spacer(1, gap),
        notes_box,
    ]
    SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=f"Aufstellung {lineup.team} – {lineup.date.isoformat()}",
    ).build(story)


def save_lineups(lineups: list[Lineup], path: Path | None = None) -> None:
    """Write ``lineups`` back to ``aufstellungen.json`` atomically."""
    file_path = path or DEFAULT_PATH
    entries = []
    for lu in lineups:
        entry: dict[str, Any] = {
            "team": lu.team,
            "date": lu.date.isoformat(),
            "system": lu.system,
            "aufgebot": {str(k): v for k, v in lu.aufgebot.items()},
            "startelf": [{"name": s.name, "pos": s.pos} for s in lu.startelf],
            "bank": list(lu.bank),
            "notizen_team": list(lu.notizen_team),
            "notizen_spieler": {str(k): list(v) for k, v in lu.notizen_spieler.items()},
        }
        entries.append(entry)
    write_json(file_path, {"spiele": entries})


def new_lineup(team: str, game_date: date, roster: list[dict[str, Any]]) -> Lineup:
    """Build a new lineup entry from roster data.

    All roster kids are nominated with shirt numbers (auto-assigned when
    missing).  The first 7 players form the default starting lineup
    (3-2-1), the rest go on the bench.
    """
    # Assign shirt numbers: use existing number if available, else auto-assign
    aufgebot: dict[str, int] = {}
    for i, kid in enumerate(roster):
        name = kid["name"]
        number = kid.get("number")
        if number is None:
            number = i + 1
        aufgebot[name] = int(number)

    # Default positions for a 3-2-1 formation
    default_positions = [
        "Tor",
        "IV",
        "LV",
        "RV",
        "6er",
        "10er",
        "9er",
    ]

    startelf: list[Starter] = []
    bank: list[str] = []

    for i, kid in enumerate(roster):
        name = kid["name"]
        if i < 7:
            pos = default_positions[i] if i < len(default_positions) else "ZM"
            startelf.append(Starter(name=name, pos=pos))
        else:
            bank.append(name)

    return Lineup(
        team=team,
        date=game_date,
        system="3-2-1",
        aufgebot=aufgebot,
        startelf=startelf,
        bank=bank,
    )


def cli_main(argv: list[str] | None = None) -> int:
    """Standalone CLI for scaffolding a new lineup entry."""
    ap = argparse.ArgumentParser(
        description="Lineup sheet generator and session scaffolding."
    )
    ap.add_argument(
        "--new",
        action="store_true",
        help="Scaffold a new lineup entry in aufstellungen.json for a team and "
        "date, pre-filling every roster kid as nominated player",
    )
    ap.add_argument(
        "--team",
        default=None,
        help="Team alias/name (must match a key in roster.json for --new)",
    )
    ap.add_argument(
        "--date",
        default=None,
        help="Game date as 2026-05-02 or 02.05.2026 (required with --new)",
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.new:
        ap.error("only --new is supported")
    if not args.team or not args.date:
        ap.error("--new requires --team and --date")
    game_date = parse_date(args.date)
    if game_date is None:
        ap.error(f"ungültiges Datum: {args.date}")
    path = DEFAULT_PATH

    roster = kapitane.load_roster_with_numbers()
    # Try to match the team name (case-insensitive)
    team_key = None
    for key in roster:
        if key.lower() == args.team.lower():
            team_key = key
            break
    if team_key is None:
        available = ", ".join(sorted(roster.keys())) or "keine"
        sys.exit(f"Kein Kader für '{args.team}' gefunden. Teams mit Kader: {available}")
    kids = roster[team_key]
    if not kids:
        sys.exit(f"Kader für '{args.team}' ist leer.")

    lineups, warnings = load_lineups(path)
    data_warnings = [w for w in warnings if "nicht gefunden" not in w]
    if data_warnings:
        for w in data_warnings:
            print(f"Warnung: {w}", file=sys.stderr)
        sys.exit("Datei enthält ungültige Einträge – nicht überschrieben.")
    for lu in lineups:
        if lu.team.lower() == team_key.lower() and lu.date == game_date:
            print(
                f"Warnung: Eintrag für '{team_key}' am {game_date.isoformat()} "
                "existiert bereits – nichts geändert."
            )
            return 0

    lineup = new_lineup(team_key, game_date, kids)
    lineups.append(lineup)
    save_lineups(lineups, path)
    print(
        f"Aufstellung: {team_key} am {game_date.strftime('%d.%m.%Y')} "
        f"– {len(kids)} Spieler"
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
