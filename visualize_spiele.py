from __future__ import annotations

import csv
import html as htmllib
import json
import re
import sys
import urllib.parse
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from string import Template
from typing import TypedDict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import (
    CLUB_MARKERS,
    CLUB_NAME,
    CSV_DATE_FORMAT,
    MONTHS_DE,
    PALETTE,
    SCRIPT_DIR,
    WD,
    WEEKDAYS_DE,
)

# Register NotoSans for proper umlaut/support in PDFs
_FONT_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Regular.ttf"
_FONT_BOLD_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Bold.ttf"
if _FONT_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans", str(_FONT_PATH)))
if _FONT_BOLD_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(_FONT_BOLD_PATH)))


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


def parse_datum(s: str) -> datetime | None:
    """Parse a DD.MM.YYYY date string, or return None."""
    try:
        return datetime.strptime(s.strip(), CSV_DATE_FORMAT)
    except ValueError:
        return None


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
            d = parse_datum(r.get("Datum", ""))
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
                    date=d,
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
    games.sort(key=lambda g: (g["date"], g["time"] or "99:99"))
    days: OrderedDict[str, list[Game]] = OrderedDict()
    for g in games:
        days.setdefault(g["datum"], []).append(g)
    return days


def short_place(spielort: str, limit: int = 45) -> str:
    """Shorten a location string, replacing pipes with commas."""
    s = re.sub(r"\s*\|\s*", ", ", spielort)
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


def maps_url(spielort: str) -> str:
    """Build a Google Maps search URL for a location."""
    q = re.sub(r"\s*\|\s*", ", ", spielort).strip()
    if not q:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


def esc(t: str) -> str:
    """HTML-escape a string."""
    return htmllib.escape(t, quote=True)


def german_now() -> str:
    """Return the current date/time in German format."""
    now = datetime.now()
    return f"{WEEKDAYS_DE[now.weekday()]}, {now.day}. {MONTHS_DE[now.month - 1]} {now.year}, {now:%H:%M} Uhr"


def render_games_js(days: OrderedDict[str, list[Game]]) -> str:
    """Serialize games to JSON for embedding in the HTML."""
    return json.dumps(
        [
            {
                "d": g["datum"],
                "t": g["time"],
                "h": g["heim"],
                "a": g["gast"],
                "w": g["wettbewerb"],
                "p": g["spielort"],
                "l": g["link"],
            }
            for day in days.values()
            for g in day
        ],
        ensure_ascii=False,
    )


def render_game_row(g: Game, is_hot: bool) -> str:
    """Render a single game table row."""
    home_tag = (
        '<span class="tag home" title="Heimspiel">H</span>'
        if g["is_home"]
        else '<span class="tag away" title="Auswärtsspiel">A</span>'
    )
    link_html = (
        f'<a class="link" href="{esc(g["link"])}" target="_blank">Link zum Spiel ↗</a>'
        if g["link"]
        else ""
    )
    place = g["spielort"].strip()
    map_html = (
        f'<a class="map" href="{maps_url(place)}" target="_blank">Karte ↗</a>'
        if place
        else ""
    )
    return (
        f'<tr class="{"hot" if is_hot else ""}" data-heim="{esc(g["heim"])}" data-gast="{esc(g["gast"])}">'
        f'<td class="time" data-label="Zeit"><span class="cell">{esc(g["time"] or "–")}</span></td>'
        f'<td class="team" data-label="Heim" style="--c:{g["home_color"]}"><span class="cell">{esc(g["heim"])}</span></td>'
        f'<td class="vs" data-label=""><span class="cell">vs</span></td>'
        f'<td class="team" data-label="Gast" style="--c:{g["away_color"]}"><span class="cell">{esc(g["gast"])}</span></td>'
        f'<td class="comp" data-label="Wettbewerb"><span class="cell">{esc(g["wettbewerb"])}</span></td>'
        f'<td class="place" data-label="Spielort"><span class="cell"><span class="addr">{esc(place)}</span>{map_html}</span></td>'
        f'<td class="home" data-label=""><span class="cell">{home_tag}</span></td>'
        f'<td data-label="Spiel"><span class="cell">{link_html}</span></td>'
        f"</tr>"
    )


def render_day_section(datum: str, games: list[Game]) -> str:
    """Render a full day section with header, table, and game rows."""
    is_hot = len(games) >= 2
    badge_style = "" if is_hot else ' style="display:none"'
    badge = f'<span class="badge"{badge_style}>⚠ {len(games)} Spiele</span>'
    header_cls = "day-header hot" if is_hot else "day-header"
    hidden_cls = ' class="hidden-teams" style="display:none"'
    unfold_btn = ""
    if is_hot:
        unfold_btn = f'<button type="button" class="unfold-btn" data-datum="{esc(datum)}">Alle Spiele</button>'
    rows_html = "".join(render_game_row(g, is_hot) for g in games)
    return (
        f'<section class="day" data-datum="{esc(datum)}">'
        f'<div class="{header_cls}"><span class="when">{esc(games[0]["wd"])}, {esc(datum)}</span><span>{badge}{unfold_btn}<span{hidden_cls}></span></span></div>'
        f'<div class="table-wrap"><table><colgroup>'
        f'<col style="width:4%"><col style="width:23%"><col style="width:3%"><col style="width:23%">'
        f'<col style="width:12%"><col style="width:24%"><col style="width:3%"><col style="width:8%">'
        f"</colgroup><thead><tr>"
        f"<th>Zeit</th><th>Heim</th><th></th><th>Gast</th><th>Wettbewerb</th><th>Spielort</th><th></th><th></th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
        f"</section>"
    )


def render_team_checks(club_teams: list[str]) -> str:
    """Render team filter checkboxes."""
    return "".join(
        f'<label class="chk"><input type="checkbox" value="{esc(t)}" data-team="{esc(t)}"> {esc(t)}</label>'
        for t in club_teams
    )


def render_footer(sources: list[Source]) -> str:
    """Render the page footer with source links."""
    src_links: list[str] = []
    for s in sources:
        if s["url"]:
            src_links.append(
                f'<a href="{esc(s["url"])}" target="_blank">{esc(s["team"])}</a>'
            )
        else:
            src_links.append(esc(s["team"]))
    return f"Erstellt am {esc(german_now())}. Datenquelle: {', '.join(src_links)}"


def build_html(
    days: OrderedDict[str, list[Game]],
    club_teams: list[str],
    sources: list[Source],
    out_path: Path,
) -> None:
    """Build the full HTML overview page."""
    total = sum(len(v) for v in days.values())
    hot_days = {d: len(v) for d, v in days.items() if len(v) >= 2}

    team_checks_html = render_team_checks(club_teams)

    sections: list[str] = []
    for datum, games in days.items():
        sections.append(render_day_section(datum, games))

    games_js = render_games_js(days)
    aliases_js = json.dumps(
        [[s["team"], s.get("original", s["team"])] for s in sources],
        ensure_ascii=False,
    )

    footer_html = render_footer(sources)

    template_path = Path(__file__).parent / "templates" / "spielplan.html"
    template = Template(template_path.read_text(encoding="utf-8"))
    html = template.safe_substitute(
        club_name=esc(CLUB_NAME),
        total=str(total),
        num_days=str(len(days)),
        num_hot_days=str(len(hot_days)),
        team_checks=team_checks_html,
        sections="".join(sections),
        footer=footer_html,
        games_js=games_js,
        aliases_js=aliases_js,
    )
    out_path.write_text(html, encoding="utf-8")


def build_pdf(days: OrderedDict[str, list[Game]], out_path: Path) -> None:
    """Build a multi-page PDF overview of all games."""
    font = "NotoSans" if _FONT_PATH.exists() else "Helvetica"
    bold_font = "NotoSans-Bold" if _FONT_BOLD_PATH.exists() else "Helvetica-Bold"
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "t", parent=styles["Title"], fontSize=18, spaceAfter=2, fontName=font
    )
    subtitle = ParagraphStyle(
        "st",
        parent=styles["Normal"],
        textColor=colors.grey,
        fontSize=10,
        spaceAfter=14,
        fontName=font,
    )
    day_head = ParagraphStyle(
        "dh",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=0,
        fontName=font,
    )
    day_head_hot = ParagraphStyle(
        "dhh", parent=day_head, textColor=colors.HexColor("#8a6d1a")
    )
    cell = ParagraphStyle(
        "c",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        spaceAfter=0,
        fontName=font,
    )
    _cell_white = ParagraphStyle(
        "cw", parent=cell, textColor=colors.white, fontSize=9, fontName=font
    )

    LEFT_MARGIN = 14 * mm
    RIGHT_MARGIN = 14 * mm
    HEADER_COL = 16 * mm
    VS_COL = 46 * mm
    COMP_COL = 40 * mm
    HOME_COL = 20 * mm
    CONTENT_WIDTH = A4[0] - LEFT_MARGIN - RIGHT_MARGIN
    DYNAMIC_COL = CONTENT_WIDTH - HEADER_COL - VS_COL - COMP_COL - HOME_COL
    col_w = [HEADER_COL, DYNAMIC_COL, VS_COL, COMP_COL, HOME_COL]

    total = sum(len(v) for v in days.values())
    hot = sum(1 for v in days.values() if len(v) >= 2)

    story = [
        Paragraph(f"Spielplan – {CLUB_NAME}", title),
        Paragraph(
            f"{total} Spiele · {len(days)} Spieltage · {hot} Tage mit mehreren Spielen",
            subtitle,
        ),
    ]

    for datum, games in days.items():
        is_hot = len(games) >= 2
        header_text = f"{games[0]['wd']}, {datum}" + (
            f" &nbsp;·&nbsp; {len(games)} Spiele" if is_hot else ""
        )
        story.append(Spacer(1, 6))
        story.append(Paragraph(header_text, day_head_hot if is_hot else day_head))

        data = [
            [
                Paragraph("Zeit", cell),
                Paragraph("Begegnung", cell),
                Paragraph("Wettbewerb", cell),
                Paragraph("Spielort", cell),
                Paragraph("", cell),
            ]
        ]
        for g in games:
            home_l, away_l = g["heim"], g["gast"]
            if not g["is_home"]:
                home_l, away_l = away_l, home_l
            match = (
                f'<font color="{g["home_color"]}"><b>{esc(home_l)}</b></font> '
                f'<font color="#999">–</font> '
                f'<font color="{g["away_color"]}">{esc(away_l)}</font>'
            )
            link = (
                f'<link href="{esc(g["link"])}"><font color="#0d6efd">Spiel ↗</font></link>'
                if g["link"]
                else ""
            )
            data.append(
                [
                    Paragraph(esc(g["time"] or "–"), cell),
                    Paragraph(match, cell),
                    Paragraph(esc(g["wettbewerb"]), cell),
                    Paragraph(esc(short_place(g["spielort"], 45)), cell),
                    Paragraph(link, cell),
                ]
            )
        t = Table(data, colWidths=col_w, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#666666")),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, -1), font),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        if is_hot:
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fff8e1")),
                        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#f0ad4e")),
                    ]
                )
            )
        story.append(t)

    SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Spielplan – {CLUB_NAME}",
    ).build(story)


def main() -> None:
    """Load games, generate HTML and PDF overviews."""
    games, club_teams, sources = load_games()
    if not games:
        sys.exit("Keine *_spiele_web.csv Dateien gefunden.")
    days = group_by_day(games)
    html_path = SCRIPT_DIR / "spielplan.html"
    pdf_path = SCRIPT_DIR / "spielplan.pdf"
    build_html(days, club_teams, sources, html_path)
    build_pdf(days, pdf_path)
    print(f"{len(games)} Spiele aus {len({g['source'] for g in games})} Dateien")
    print(f"HTML: {html_path}")
    print(f"PDF:  {pdf_path}")


if __name__ == "__main__":
    main()
