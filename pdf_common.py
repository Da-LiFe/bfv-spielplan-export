"""Shared PDF helpers for the spielplan project.

Font registration, page margins, colours, club header and footer helpers –
used by the PDF modules (overview, team, lineup sheet, attendance).
"""

from __future__ import annotations

import html as htmllib
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, Table

from config import (
    CLUB_NAME,
    LINK_COLOR,
    MONTHS_DE,
    SCRIPT_DIR,
    WEEKDAYS_DE,
)

# ---------------------------------------------------------------------------
# Font registration (idempotent – called once per process)
# ---------------------------------------------------------------------------

_FONT_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Regular.ttf"
_FONT_BOLD_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Bold.ttf"
if _FONT_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans", str(_FONT_PATH)))
if _FONT_BOLD_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(_FONT_BOLD_PATH)))

FONT = "NotoSans"
BOLD_FONT = "NotoSans-Bold"

# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

PAGE_MARGIN = 14 * mm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

HOME_COLOR = "#198754"
AWAY_COLOR = "#6c75cd"

# ---------------------------------------------------------------------------
# Club header
# ---------------------------------------------------------------------------

HEADER_LOGO_SIZE = 28  # points


def build_club_header(team: str) -> list:
    """Build a PDF table with the club logo and team name."""
    logo_path = SCRIPT_DIR / "assets" / "logo.png"
    if logo_path.exists():
        logo = Image(str(logo_path), width=HEADER_LOGO_SIZE, height=HEADER_LOGO_SIZE)
    else:
        logo = None

    parts: list = [CLUB_NAME]
    if team and team != CLUB_NAME:
        parts.append(team)
    title = " / ".join(parts)

    title_style = ParagraphStyle(
        "club_header", fontName=BOLD_FONT, fontSize=14, textColor=colors.black
    )

    if logo is not None:
        logo_table = Table(
            [[logo, Paragraph(title, title_style)]],
            colWidths=[HEADER_LOGO_SIZE + 4, CONTENT_WIDTH - HEADER_LOGO_SIZE - 4],
            style=[
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("LEFTPADDING", (1, 0), (1, 0), 4),
            ],
        )
    else:
        logo_table = [Paragraph(title, title_style)]

    return logo_table


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


def german_now() -> str:
    """Return the current date/time in German format."""
    now = datetime.now()
    return (
        f"{WEEKDAYS_DE[now.weekday()]}, {now.day}. "
        f"{MONTHS_DE[now.month - 1]} {now.year}, {now:%H:%M} Uhr"
    )


def build_footer(team: str, source_url: str | None = None) -> str:
    """Build the "Erstellt am … Datenquelle:" footer string."""
    if source_url:
        return (
            f"Erstellt am {htmllib.escape(german_now())}. "
            f'Datenquelle: <link href="{htmllib.escape(source_url)}">'
            f'<font color="{LINK_COLOR}">{htmllib.escape(team)}</font></link>'
        )
    return f"Erstellt am {htmllib.escape(german_now())}. Datenquelle: {htmllib.escape(team)}"
