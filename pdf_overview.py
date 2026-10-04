"""Overview of all games: the HTML page and the multi-page PDF.

``run_overview`` is the ``spielplan.py overview`` command; ``build_pdf``
produces the PDF listing every game grouped by date.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import aufstellung
from config import CLUB_NAME, SCRIPT_DIR
from games import Game, group_by_day, load_games, short_place
from pdf_common import (
    BOLD_FONT,
    CONTENT_WIDTH,
    FONT,
    LINK_COLOR,
    PAGE_MARGIN,
)
from render_html import build_html
from util import esc


def build_pdf(days: OrderedDict[str, list[Game]], out_path: Path) -> None:
    """Build a multi-page PDF overview of all games."""
    font = FONT
    bold_font = BOLD_FONT
    styles = getSampleStyleSheet()
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

    # Get club logo (same as team PDF and lineup sheet)
    logo = aufstellung.get_logo(
        cache_path=SCRIPT_DIR / ".bfv_cache" / aufstellung.LOGO_CACHE_PATH.name
    )

    story = [
        aufstellung.build_club_header(
            "Spielplan",
            [
                f"{total} Spiele \u00b7 {len(days)} Spieltage \u00b7 {hot} Tage mit mehreren Spielen"
            ],
            logo,
            CONTENT_WIDTH,
        ),
    ]

    for datum, games in days.items():
        is_hot = len(games) >= 2
        header_text = f"{games[0]['wd']}, {datum}" + (
            f" &nbsp;\u00b7&nbsp; {len(games)} Spiele" if is_hot else ""
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
                f'<font color="#999">\u2013</font> '
                f'<font color="{g["away_color"]}">{esc(away_l)}</font>'
            )
            link = (
                f'<link href="{esc(g["link"])}"><font color="{LINK_COLOR}">Spiel &nearr;</font></link>'
                if g["link"]
                else ""
            )
            data.append(
                [
                    Paragraph(esc(g["time"] or "\u2013"), cell),
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
        title=f"Spielplan \u2013 {CLUB_NAME}",
    ).build(story)


def run_overview() -> int:
    """Write ``spielplan.html`` and ``spielplan.pdf`` from all game CSVs."""
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
    return 0
