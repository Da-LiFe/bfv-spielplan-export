from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from string import Template
from typing import TypedDict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import anwesenheit
import aufstellung
import kapitane
from config import (
    CLUB_MARKERS,
    CLUB_NAME,
    CSV_DATE_FORMAT,
    LINK_COLOR,
    PALETTE,
    SCRIPT_DIR,
    WD,
    WEEKDAYS_DE,
)
from pdf_common import (
    AWAY_COLOR,
    BOLD_FONT,
    CONTENT_WIDTH,
    FONT,
    HOME_COLOR,
    PAGE_MARGIN,
    german_now,
)
from util import (
    esc,
    game_sort_key,
    maps_url,
    parse_date,
    place_text,
)


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


def club_logo() -> Path | None:
    """Return the cached club logo (downloaded when stale) for PDF headers."""
    return aufstellung.get_logo(
        cache_path=SCRIPT_DIR / ".bfv_cache" / aufstellung.LOGO_CACHE_PATH.name
    )


def resolve_team(sources: list[Source], arg: str) -> Source:
    """Return the source whose alias or original BFV name matches ``arg``."""
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
    s = re.sub(r"\s*\|\s*", ", ", spielort)
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


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
    font = FONT
    bold_font = BOLD_FONT
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

    HEADER_COL = 16 * mm
    VS_COL = 46 * mm
    COMP_COL = 40 * mm
    HOME_COL = 20 * mm
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
                f'<link href="{esc(g["link"])}"><font color="{LINK_COLOR}">Spiel ↗</font></link>'
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
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Spielplan – {CLUB_NAME}",
    ).build(story)


def _pill(text: str, bg: str, font: str, size: int = 8) -> Table:
    """Render a small colored H/A pill."""
    style = ParagraphStyle(
        "pill",
        fontName=font,
        fontSize=size,
        leading=size + 1,
        textColor=colors.white,
        alignment=1,
        spaceBefore=0,
        spaceAfter=0,
    )
    return Table(
        [[Paragraph(text, style)]],
        colWidths=[6 * mm],
        rowHeights=[5.2 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ],
    )


def _team_game_card(
    g: Game,
    font: str,
    bold_font: str,
    card_width: float,
    captain_name: str | None = None,
    captain_week_txt: str = "",
) -> Table:
    """Render one upcoming game as a friendly card for parents."""
    accent = HOME_COLOR if g["is_home"] else AWAY_COLOR
    accent_bar = 2.6 * mm
    side_pad = 10 * mm
    card_content = card_width - accent_bar
    inner_w = card_content - 2 * side_pad
    time_col = 42 * mm

    date_style = ParagraphStyle(
        "gd",
        fontName=bold_font,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#222222"),
        spaceAfter=0,
    )
    day_txt = f"{WEEKDAYS_DE[g['date'].weekday()]}, {g['datum']}"
    time_txt = f"{g['time']} Uhr" if g["time"] else "Zeit folgt"
    time_para = Paragraph(
        esc(time_txt),
        ParagraphStyle(
            "gt", parent=date_style, alignment=2, textColor=colors.HexColor(accent)
        ),
    )

    pill = _pill("H" if g["is_home"] else "A", accent, font)
    match_para = Paragraph(
        f'<font color="{g["home_color"]}"><b>{esc(g["heim"])}</b></font>'
        f'<font color="#999999">&nbsp;–&nbsp;</font>'
        f'<font color="{g["away_color"]}">{esc(g["gast"])}</font>',
        ParagraphStyle(
            "gm",
            fontName=font,
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#222222"),
            spaceAfter=0,
        ),
    )
    teams_sub = Table(
        [[pill, match_para]],
        colWidths=[8 * mm, inner_w - 8 * mm],
        style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")],
    )

    place = g["spielort"].strip()
    ort_txt = place_text(place) if place else ""
    line1_parts: list[str] = []
    if g["wettbewerb"]:
        line1_parts.append(
            f'Wettbewerb: <font color="#333333"><b>{esc(g["wettbewerb"])}</b></font>'
        )
    if ort_txt:
        map_href = maps_url(place)
        if map_href:
            line1_parts.append(
                f'<link href="{esc(map_href)}"><font color="{LINK_COLOR}">Karte »</font></link>'
            )
    if g["link"]:
        line1_parts.append(
            f'<link href="{esc(g["link"])}"><font color="{LINK_COLOR}"><b>Spiel »</b></font></link>'
        )
    info1_para = Paragraph(
        "&nbsp;·&nbsp;".join(line1_parts),
        ParagraphStyle(
            "gi",
            fontName=font,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#666666"),
            spaceAfter=0,
        ),
    )
    info2_para = Paragraph(
        f'Ort: <font color="#333333"><b>{esc(ort_txt)}</b></font>' if ort_txt else "",
        ParagraphStyle(
            "go",
            fontName=font,
            fontSize=9,
            leading=13,
            spaceAfter=0,
            textColor=colors.HexColor("#444444"),
        ),
    )

    inner_rows: list[list] = [
        [Paragraph(esc(day_txt), date_style), time_para],
        [teams_sub, ""],
    ]
    span_rows: list[int] = [1]
    captain_row = None
    if captain_name is not None:
        cap_style = ParagraphStyle(
            "cap",
            fontName=bold_font,
            fontSize=9,
            leading=12,
            spaceAfter=0,
            textColor=colors.HexColor("#444444"),
        )
        cap_txt = captain_name or "folgt"
        if captain_name and captain_week_txt:
            cap_txt = f"{cap_txt} · {captain_week_txt}"
        cap_para = Paragraph(
            f'<font color="{accent}"><b>Kapitän der Woche</b></font> · {esc(cap_txt)}',
            cap_style,
        )
        captain_row = len(inner_rows)
        inner_rows.append([cap_para, ""])
        span_rows.append(captain_row)
    for para in (info1_para, info2_para):
        inner_rows.append([para, ""])
        span_rows.append(len(inner_rows) - 1)

    cap_tint = "#e9f5ee" if g["is_home"] else "#efeef8"
    inner_style: list = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]
    for row in span_rows:
        inner_style.append(("SPAN", (0, row), (1, row)))
    if captain_row is not None:
        inner_style.append(
            (
                "BACKGROUND",
                (0, captain_row),
                (1, captain_row),
                colors.HexColor(cap_tint),
            )
        )
        inner_style.append(("TOPPADDING", (0, captain_row), (1, captain_row), 3))
        inner_style.append(("BOTTOMPADDING", (0, captain_row), (1, captain_row), 4))
    inner = Table(
        inner_rows,
        colWidths=[inner_w - time_col, time_col],
        style=inner_style,
    )
    card = Table(
        [["", inner]],
        colWidths=[accent_bar, card_content],
        style=[
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(accent)),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#ffffff")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#dfe3ea")),
            ("LEFTPADDING", (0, 0), (-1, -1), side_pad),
            ("RIGHTPADDING", (0, 0), (-1, -1), side_pad),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ],
    )
    card.spaceAfter = 7
    return card


def build_team_pdf(
    games: list[Game],
    team: str,
    sources: list[Source],
    out_path: Path,
    num: int,
    captain_by_week: dict[str, str] | None = None,
    logo: Path | None = None,
) -> None:
    """Build a single-team PDF overview of the next ``num`` games.

    ``captain_by_week`` maps a duty-week key (see ``kapitane.duty_week``) to a
    kid's name; ``None`` hides the Kapitän row entirely. Weeks present in the
    mapping show the name, missing keys fall back to "folgt". ``logo`` is the
    club logo shown in the header (same header as the lineup sheet).
    """
    font = FONT
    bold_font = BOLD_FONT
    styles = getSampleStyleSheet()

    legend = ParagraphStyle(
        "lg",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#777777"),
        spaceAfter=0,
        fontName=font,
    )
    foot = ParagraphStyle(
        "fo",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#999999"),
        spaceBefore=4,
        fontName=font,
    )

    source = next((s for s in sources if s["team"] == team), None)
    first_datum = games[0]["datum"] if games else "?"
    sub_txt = f"Nächste {num} Spiele ab {first_datum} · Stand: {german_now()}"

    header = aufstellung.build_club_header(
        "Überblick Spieltage", [team, sub_txt], logo, CONTENT_WIDTH
    )

    legend_txt = Paragraph("Karte- und Spiel-Links sind im PDF anklickbar.", legend)
    legend_row = Table(
        [
            [
                _pill("H", HOME_COLOR, font, 7),
                Paragraph("Heimspiel", legend),
                _pill("A", AWAY_COLOR, font, 7),
                Paragraph("Auswärtsspiel", legend),
                legend_txt,
            ]
        ],
        colWidths=[
            6 * mm,
            24 * mm,
            6 * mm,
            28 * mm,
            CONTENT_WIDTH - 64 * mm,
        ],
        style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE")],
    )

    story = [header, Spacer(1, 5), legend_row, Spacer(1, 7)]

    for g in games:
        if captain_by_week is None:
            story.append(_team_game_card(g, font, bold_font, CONTENT_WIDTH))
            continue
        wk = kapitane.duty_week(
            g["date"].date() if isinstance(g["date"], datetime) else g["date"]
        )
        captain = captain_by_week.get(wk, "")
        week_txt = kapitane.week_range(wk) if wk in captain_by_week else ""
        story.append(
            _team_game_card(g, font, bold_font, CONTENT_WIDTH, captain, week_txt)
        )

    if source and source.get("url"):
        foot_txt = (
            f"Erstellt am {esc(german_now())}. Datenquelle: "
            f'<link href="{esc(source["url"])}"><font color="{LINK_COLOR}">{esc(team)}</font></link>'
        )
    else:
        foot_txt = f"Erstellt am {esc(german_now())}. Datenquelle: {esc(team)}"
    story.append(Paragraph(foot_txt, foot))

    SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Überblick Spieltage – {team}",
    ).build(story)


def handle_captains(
    games: list[Game], sources: list[Source], assign: bool, check: bool
) -> None:
    """Fill and/or verify the Kapitän assignments from roster.json/kapitane.json."""
    cfg_path = SCRIPT_DIR / kapitane.CONFIG_NAME
    roster_path = SCRIPT_DIR / kapitane.ROSTER_NAME
    cfg = kapitane.load_all(cfg_path, roster_path)
    weeks = kapitane.teams_duty_weeks(games, sources)
    if assign:
        warnings = kapitane.ensure_assignments(cfg, weeks)
        kapitane.save_config(cfg, cfg_path)
        print(f"{kapitane.ROSTER_NAME} / {kapitane.CONFIG_NAME} aktualisiert.")
        for warning in warnings:
            print(f"Warnung: {warning}", file=sys.stderr)
        print()
    result = kapitane.check_distribution(cfg, weeks)
    if check:
        kapitane.run_check(result, cfg_path)
    for line in result.lines:
        print(line)


def handle_anwesenheit(team: str | None, out: str | None, combined: bool) -> None:
    """Render the training attendance evaluation PDF from anwesenheit.json."""
    data = anwesenheit.load_data(SCRIPT_DIR / anwesenheit.ANWESENHEIT_NAME)
    sessions = data["sessions"]
    if team:
        teams = sorted({s["team"] for s in sessions})
        if team not in teams:
            sys.exit(
                f"Team '{team}' nicht gefunden. Verfügbare Teams: "
                f"{', '.join(teams) or 'keine'}"
            )
        sessions = [s for s in sessions if s["team"] == team]
        pdf_name = f"{slugify(team)}_anwesenheit.pdf"
    else:
        pdf_name = anwesenheit.PDF_NAME
    out_path = Path(out) if out else SCRIPT_DIR / pdf_name
    teams_rendered = anwesenheit.build_anwesenheit_pdf(sessions, out_path, combined)
    print(f"{len(sessions)} Trainingstermine aus {len(teams_rendered)} Team(s)")
    print(f"PDF:  {out_path}")


def find_team_game(games: list[Game], team: str, day: datetime) -> Game | None:
    """Return the (earliest) game of ``team`` on the given day, if any."""
    matches = [
        g
        for g in games
        if (g["heim"] == team or g["gast"] == team) and g["date"].date() == day.date()
    ]
    matches.sort(key=lambda g: g["time"] or "99:99")
    return matches[0] if matches else None


def handle_aufstellung(
    team_arg: str | None, date_arg: str | None, out: str | None
) -> None:
    """Render the lineup sheet of one game from aufstellungen.json."""
    if not team_arg:
        sys.exit("--aufstellung benötigt --team.")
    day = None
    if date_arg:
        day = aufstellung.parse_date(date_arg)
        if day is None:
            sys.exit(f"Ungültiges Datum '{date_arg}' (erwartet YYYY-MM-DD).")

    lineups, load_warnings = aufstellung.load_lineups(
        SCRIPT_DIR / aufstellung.AUFSTELLUNGEN_NAME
    )
    for warning in load_warnings:
        print(f"Warnung: {warning}", file=sys.stderr)

    games, _, sources = load_games()
    lowered = team_arg.lower()
    source = next(
        (
            s
            for s in sources
            if s["team"].lower() == lowered
            or (s.get("original") or "").lower() == lowered
        ),
        None,
    )
    names = {team_arg}
    if source:
        names |= {source["team"], source.get("original") or source["team"]}
    team_lineups = aufstellung.lineups_for_team(lineups, names)
    if not team_lineups:
        available = sorted({lu.team for lu in lineups})
        sys.exit(
            f"Keine Aufstellung für '{team_arg}' gefunden. Teams mit Aufstellung: "
            f"{', '.join(available) or 'keine'}"
        )
    lineup = aufstellung.select_lineup(team_lineups, day)
    if lineup is None:
        dates = ", ".join(lu.date.isoformat() for lu in team_lineups)
        what = f"Aufstellung am {day.isoformat()}" if day else "kommende Aufstellung"
        sys.exit(f"Keine {what} für '{team_arg}'. Vorhandene Termine: {dates}")

    team = source["team"] if source else lineup.team
    game = find_team_game(
        games, team, datetime.combine(lineup.date, datetime.min.time())
    )
    info = None
    if game:
        opponent = game["gast"] if game["heim"] == team else game["heim"]
        info = aufstellung.GameInfo(
            opponent=opponent,
            kickoff=game["time"],
            competition=game["wettbewerb"],
            is_home=game["heim"] == team,
            spielort=game["spielort"],
        )
    else:
        print(
            f"Warnung: Kein Spiel von '{team}' am {lineup.date.strftime('%d.%m.%Y')} "
            "in den *_spiele_web.csv – Gegner und Treffpunkt unbekannt.",
            file=sys.stderr,
        )

    assignments = kapitane.load_config(SCRIPT_DIR / kapitane.CONFIG_NAME)["assignments"]
    week = kapitane.duty_week(lineup.date)
    captain = next(
        (
            assignments[name][week]
            for name in (team, lineup.team)
            if assignments.get(name, {}).get(week)
        ),
        "",
    )

    for warning in aufstellung.validate(lineup):
        print(f"Warnung: {warning}", file=sys.stderr)

    logo = club_logo()
    out_path = (
        Path(out)
        if out
        else SCRIPT_DIR / f"{slugify(team)}_aufstellung_{lineup.date.isoformat()}.pdf"
    )
    aufstellung.build_lineup_pdf(lineup, out_path, info, captain, logo)
    opponent_txt = f" gegen {info.opponent}" if info else ""
    print(f"Aufstellung {team} am {lineup.date.strftime('%d.%m.%Y')}{opponent_txt}")
    print(f"PDF:  {out_path}")


def main(argv: list[str] | None = None) -> None:
    """Load games, generate HTML/PDF overviews, or a single-team PDF."""
    ap = argparse.ArgumentParser(
        description="Generate HTML/PDF overviews from *_spiele_web.csv files."
    )
    ap.add_argument(
        "--team",
        default=None,
        help="Generate a single-team PDF with only the next upcoming games, or "
        "filter --anwesenheit to one team (matches a team alias or original "
        "BFV name)",
    )
    ap.add_argument(
        "--next",
        type=int,
        default=4,
        help="Number of upcoming games for --team (default: 4)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Output path for the --team, --anwesenheit or --aufstellung PDF "
        "(default: <slug>_monthly.pdf / anwesenheit.pdf / "
        "<slug>_aufstellung_<date>.pdf)",
    )
    ap.add_argument(
        "--anwesenheit",
        action="store_true",
        help="Render the training attendance evaluation PDF from "
        "anwesenheit.json (no game CSVs needed)",
    )
    ap.add_argument(
        "--kombiniert",
        action="store_true",
        help="With --anwesenheit: merge sick and absent (S+A) into one column "
        "and show only the Quote P percentage",
    )
    ap.add_argument(
        "--captains-assign",
        action="store_true",
        help="Extend kapitane.json with the duty weeks of newly fetched games "
        "(round-robin, fair by construction)",
    )
    ap.add_argument(
        "--captains-check",
        action="store_true",
        help="Verify the Kapitän assignments are equally distributed and exit "
        "non-zero otherwise",
    )
    ap.add_argument(
        "--aufstellung",
        action="store_true",
        help="Render the lineup sheet of one game from aufstellungen.json "
        "(needs --team; picks the next game with a lineup unless --date is set)",
    )
    ap.add_argument(
        "--date",
        default=None,
        help="With --aufstellung: game date as YYYY-MM-DD",
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    if args.aufstellung:
        handle_aufstellung(args.team, args.date, args.out)
        return

    if args.anwesenheit:
        handle_anwesenheit(args.team, args.out, args.kombiniert)
        return

    games, club_teams, sources = load_games()
    if not games:
        sys.exit("Keine *_spiele_web.csv Dateien gefunden.")

    if args.captains_assign or args.captains_check:
        handle_captains(games, sources, args.captains_assign, args.captains_check)
        return

    if args.team:
        if args.next <= 0:
            sys.exit("--next must be a positive number of games.")
        source = resolve_team(sources, args.team)
        team = source["team"]
        next_games = next_games_for_team(games, team, args.next)
        if not next_games:
            sys.exit(f"Keine bevorstehenden Spiele für '{team}' gefunden.")
        out = (
            Path(args.out) if args.out else SCRIPT_DIR / f"{slugify(team)}_monthly.pdf"
        )
        cfg = kapitane.load_all(
            SCRIPT_DIR / kapitane.CONFIG_NAME, SCRIPT_DIR / kapitane.ROSTER_NAME
        )
        captain_by_week = (
            cfg["assignments"].get(team, {})
            if team in cfg["teams"] or team in cfg["assignments"]
            else None
        )
        build_team_pdf(
            next_games,
            team,
            sources,
            out,
            len(next_games),
            captain_by_week,
            logo=club_logo(),
        )
        print(f"{len(next_games)} kommende Spiele für {team}")
        print(f"PDF:  {out}")
        if captain_by_week is not None:
            missing = [
                game
                for game in next_games
                if not captain_by_week.get(kapitane.duty_week(game["date"].date()), "")
            ]
            if missing:
                rng = ", ".join(
                    kapitane.week_range(kapitane.duty_week(g["date"].date()))
                    for g in missing
                )
                print(
                    f"Hinweis: Kapitän offen für {rng} – "
                    "'--captains-assign' führt die Zuteilung durch.",
                    file=sys.stderr,
                )
        return

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
