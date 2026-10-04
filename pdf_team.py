"""Single-team PDF with upcoming games.

Produces a PDF listing the next few games for one team, with optional
Kapit\u00e4n (captain) assignment display. ``run_team`` is the
``spielplan.py team`` command.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

import aufstellung
import kapitane
from config import LINK_COLOR, SCRIPT_DIR, WEEKDAYS_DE
from games import Game, load_games, next_games_for_team, resolve_team, slugify
from pdf_common import (
    AWAY_COLOR,
    BOLD_FONT,
    CONTENT_WIDTH,
    FONT,
    HOME_COLOR,
    PAGE_MARGIN,
    german_now,
)
from util import esc, maps_url, place_text


def _get_logo() -> Path | None:
    """Return the cached club logo (downloaded when stale) for PDF headers."""
    return aufstellung.get_logo(
        cache_path=SCRIPT_DIR / ".bfv_cache" / aufstellung.LOGO_CACHE_PATH.name
    )


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
        f'<font color="#999999">&nbsp;\u2013&nbsp;</font>'
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
                f'<link href="{esc(map_href)}"><font color="{LINK_COLOR}">Karte \u00bb</font></link>'
            )
    if g["link"]:
        line1_parts.append(
            f'<link href="{esc(g["link"])}"><font color="{LINK_COLOR}"><b>Spiel \u00bb</b></font></link>'
        )
    info1_para = Paragraph(
        "&nbsp;\u00b7&nbsp;".join(line1_parts),
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
            cap_txt = f"{cap_txt} \u00b7 {captain_week_txt}"
        cap_para = Paragraph(
            f'<font color="{accent}"><b>Kapit\u00e4n der Woche</b></font> \u00b7 {esc(cap_txt)}',
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
    sources: list,
    out_path: Path,
    num: int,
    captain_by_week: dict[str, str] | None = None,
    logo: Path | None = None,
) -> None:
    """Build a single-team PDF overview of the next ``num`` games.

    ``captain_by_week`` maps a duty-week key (see ``kapitane.duty_week``) to a
    kid's name; ``None`` hides the Kapit\u00e4n row entirely. Weeks present in the
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
    sub_txt = f"N\u00e4chste {num} Spiele ab {first_datum} \u00b7 Stand: {german_now()}"

    header = aufstellung.build_club_header(
        "\u00dcberblick Spieltage", [team, sub_txt], logo, CONTENT_WIDTH
    )

    legend_txt = Paragraph("Karte- und Spiel-Links sind im PDF anklickbar.", legend)
    legend_row = Table(
        [
            [
                _pill("H", HOME_COLOR, font, 7),
                Paragraph("Heimspiel", legend),
                _pill("A", AWAY_COLOR, font, 7),
                Paragraph("Ausw\u00e4rtsspiel", legend),
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
        title=f"\u00dcberblick Spieltage \u2013 {team}",
    ).build(story)


def run_team(name: str, num: int = 4, out: str | Path | None = None) -> int:
    """Write the PDF with the next ``num`` games of one team (alias or BFV name)."""
    if num <= 0:
        sys.exit("--next must be a positive number of games.")
    games, _, sources = load_games()
    if not games:
        sys.exit("Keine *_spiele_web.csv Dateien gefunden.")
    source = resolve_team(sources, name)
    team = source["team"]
    next_games = next_games_for_team(games, team, num)
    if not next_games:
        sys.exit(f"Keine bevorstehenden Spiele f\u00fcr '{team}' gefunden.")
    out_path = Path(out) if out else SCRIPT_DIR / f"{slugify(team)}_spiele.pdf"
    cfg = kapitane.load_all(
        SCRIPT_DIR / kapitane.CONFIG_NAME, SCRIPT_DIR / kapitane.ROSTER_NAME
    )
    names = {team, source.get("original") or team}
    captain_by_week = kapitane.captains_for(cfg, names)
    build_team_pdf(
        next_games,
        team,
        sources,
        out_path,
        len(next_games),
        captain_by_week,
        logo=_get_logo(),
    )
    print(f"{len(next_games)} kommende Spiele f\u00fcr {team}")
    print(f"PDF:  {out_path}")
    open_weeks = [
        kapitane.week_range(kapitane.duty_week(g["date"].date()))
        for g in next_games
        if not captain_by_week.get(kapitane.duty_week(g["date"].date()), "")
    ]
    if open_weeks:
        print(
            f"Hinweis: Kapit\u00e4n offen f\u00fcr {', '.join(open_weeks)} \u2013 "
            "'spielplan.py captains --assign' f\u00fchrt die Zuteilung durch.",
            file=sys.stderr,
        )
    return 0
