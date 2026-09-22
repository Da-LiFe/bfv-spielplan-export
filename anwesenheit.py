"""Training attendance ("Anwesenheit") statistics.

One training session records each kid's status as **P** (present),
**S** (sick), **A** (absent) or **N** (no feedback). Sessions live in
``anwesenheit.json`` (gitignored, contains kid names) and are maintained by
hand, or scaffolded with ``--new`` from the team roster in ``roster.json``.

The CLI renders an A4 portrait PDF with a per-team, per-player summary table:
session count, P/S/A/N totals and the presence quotas ``P / total`` and
``(P+S) / total`` (``N`` counts toward the total, i.e. lowers the quota).
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import kapitane
from config import CSV_DATE_FORMAT, MONTHS_DE, SCRIPT_DIR, WEEKDAYS_DE

ANWESENHEIT_NAME = "anwesenheit.json"
DEFAULT_PATH = SCRIPT_DIR / ANWESENHEIT_NAME
PDF_NAME = "anwesenheit.pdf"

STATUSES = ("P", "S", "A", "N")
STATUS_LABELS = {
    "P": "anwesend",
    "S": "krank",
    "A": "abwesend",
    "N": "keine Rückmeldung",
}

_FONT_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Regular.ttf"
_FONT_BOLD_PATH = SCRIPT_DIR / "fonts" / "NotoSans-Bold.ttf"
if _FONT_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans", str(_FONT_PATH)))
if _FONT_BOLD_PATH.exists():
    pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(_FONT_BOLD_PATH)))


def esc(text: Any) -> str:
    """HTML-escape a string."""
    return htmllib.escape(str(text), quote=True)


def german_now() -> str:
    """Return the current date/time in German format."""
    now = datetime.now()
    return f"{WEEKDAYS_DE[now.weekday()]}, {now.day}. {MONTHS_DE[now.month - 1]} {now.year}, {now:%H:%M} Uhr"


def empty_data() -> dict[str, Any]:
    """Return an empty attendance dataset."""
    return {"sessions": [], "warnings": []}


def parse_session_date(value: Any) -> date | None:
    """Parse an ISO (2026-09-21) or German (21.09.2026) date string."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    for fmt in ("%Y-%m-%d", CSV_DATE_FORMAT):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def normalize_data(raw: Any) -> dict[str, Any]:
    """Coerce arbitrary JSON into the expected sessions structure.

    Malformed sessions are dropped, unknown status letters count as ``N``;
    both produce an entry in the returned ``warnings`` list. Internal sessions
    carry ``date`` as a ``datetime.date`` object.
    """
    sessions: list[dict[str, Any]] = []
    warnings: list[str] = []
    raw_sessions = raw.get("sessions") if isinstance(raw, dict) else None
    if not isinstance(raw_sessions, list):
        if raw_sessions:
            warnings.append("anwesenheit.json: 'sessions' ist keine Liste.")
        return {"sessions": sessions, "warnings": warnings}
    for i, session in enumerate(raw_sessions):
        if not isinstance(session, dict):
            warnings.append(
                f"anwesenheit.json: Eintrag {i} ist kein Objekt – übersprungen."
            )
            continue
        d = parse_session_date(session.get("date"))
        if d is None:
            warnings.append(
                f"anwesenheit.json: ungültiges Datum '{session.get('date')}' – Eintrag übersprungen."
            )
            continue
        team = str(session.get("team", "")).strip()
        if not team:
            warnings.append(
                f"anwesenheit.json: Eintrag am {d.isoformat()} ohne Team – übersprungen."
            )
            continue
        raw_values = session.get("values")
        if not isinstance(raw_values, dict):
            warnings.append(
                f"anwesenheit.json: Eintrag '{team}' am {d.isoformat()} ohne 'values' – übersprungen."
            )
            continue
        values: dict[str, str] = {}
        for kid, status in raw_values.items():
            kid_name = str(kid).strip()
            if not kid_name:
                continue
            code = str(status).strip().upper()
            if code not in STATUSES:
                warnings.append(
                    f"Unbekannter Status '{status}' für '{kid_name}' am {d.isoformat()} "
                    f"– als 'N' gewertet."
                )
                code = "N"
            values[kid_name] = code
        sessions.append({"date": d, "team": team, "values": values})
    return {"sessions": sessions, "warnings": warnings}


def load_data(path: Path | None = None) -> dict[str, Any]:
    """Load and normalize ``anwesenheit.json``; print warnings to stderr."""
    data_path = path or DEFAULT_PATH
    if not data_path.exists():
        return empty_data()
    try:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(
            f"{data_path.name}: ungültiges JSON – keine Daten geladen.",
            file=sys.stderr,
        )
        return empty_data()
    data = normalize_data(raw)
    for warning in data["warnings"]:
        print(f"Warnung: {warning}", file=sys.stderr)
    return data


def save_data(sessions: list[dict[str, Any]], path: Path | None = None) -> None:
    """Write the sessions to ``anwesenheit.json`` (dates as ISO strings)."""
    data_path = path or DEFAULT_PATH
    data_path.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        **s,
                        "date": s["date"].isoformat()
                        if isinstance(s["date"], date)
                        else str(s["date"]),
                    }
                    for s in sessions
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def session_exists(sessions: list[dict[str, Any]], team: str, d: date) -> bool:
    """Return whether a session for ``team`` on ``d`` already exists."""
    d = d if isinstance(d, date) else parse_session_date(d)  # type: ignore[assignment]
    return any(s["team"] == team and s["date"] == d for s in sessions)


def new_session(team: str, session_date: date, roster: list[str]) -> dict[str, Any]:
    """Build a session entry with every roster player defaulting to ``N``."""
    return {
        "date": session_date,
        "team": team,
        "values": {str(kid): "N" for kid in roster if kid},
    }


@dataclass
class PlayerStats:
    """Aggregated attendance numbers for a single player."""

    name: str
    sessions: int = 0
    p: int = 0
    s: int = 0
    a: int = 0
    n: int = 0

    @property
    def presence_rate(self) -> float:
        """Share of tracked sessions the player was present (P / total)."""
        return self.p / self.sessions if self.sessions else 0.0

    @property
    def fit_rate(self) -> float:
        """Share of tracked sessions the player was present or sick ((P+S) / total)."""
        return (self.p + self.s) / self.sessions if self.sessions else 0.0


def stats_per_team(sessions: list[dict[str, Any]]) -> dict[str, list[PlayerStats]]:
    """Map each team to its sorted per-player attendance statistics."""
    by_team: dict[str, dict[str, Counter[str]]] = {}
    team_sessions: dict[str, int] = {}
    for s in sessions:
        team = s["team"]
        team_sessions[team] = team_sessions.get(team, 0) + 1
        counters = by_team.setdefault(team, {})
        for kid, code in s["values"].items():
            kid_stats = counters.setdefault(kid, Counter[str]())
            kid_stats["sessions"] += 1
            kid_stats[code] += 1
    result: dict[str, list[PlayerStats]] = {}
    for team in sorted(by_team):
        stats = [
            PlayerStats(
                name=kid,
                sessions=counters["sessions"],
                p=counters["P"],
                s=counters["S"],
                a=counters["A"],
                n=counters["N"],
            )
            for kid, counters in sorted(by_team[team].items())
        ]
        result[team] = stats
    return result


def _percent(value: float) -> str:
    return f"{value * 100:.0f} %"


def _cell(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(esc(text), style)


def _columns(combined: bool) -> tuple[list[str], list[float]]:
    """Return the summary table headers and column widths (sum = 182 mm)."""
    if combined:
        return (
            [
                "Spieler",
                "Termine",
                "P",
                "A",
                "N",
                "Quote P",
            ],
            [60 * mm, 22 * mm, 30 * mm, 30 * mm, 14 * mm, 26 * mm],
        )
    return (
        ["Spieler", "Termine", "P", "S", "A", "N", "Quote P", "Quote P+S"],
        [60 * mm, 22 * mm, 14 * mm, 14 * mm, 14 * mm, 14 * mm, 22 * mm, 22 * mm],
    )


def _player_values(ps: PlayerStats, combined: bool) -> tuple[Any, ...]:
    """Return the row cells for one player (or the totals row)."""
    if combined:
        return (
            ps.name,
            ps.sessions,
            ps.p,
            ps.s + ps.a,
            ps.n,
            _percent(ps.presence_rate),
        )
    return (
        ps.name,
        ps.sessions,
        ps.p,
        ps.s,
        ps.a,
        ps.n,
        _percent(ps.presence_rate),
        _percent(ps.fit_rate),
    )


def _make_row(
    values: tuple[Any, ...], first_style: ParagraphStyle, cell_style: ParagraphStyle
) -> list[Paragraph]:
    """Assemble one table row from a values tuple."""
    return [_cell(values[0], first_style)] + [_cell(v, cell_style) for v in values[1:]]


def _totals(stats: list[PlayerStats]) -> PlayerStats:
    """Aggregate the per-player statistics into a single totals row."""
    return PlayerStats(
        name="Summe",
        sessions=sum(ps.sessions for ps in stats),
        p=sum(ps.p for ps in stats),
        s=sum(ps.s for ps in stats),
        a=sum(ps.a for ps in stats),
        n=sum(ps.n for ps in stats),
    )


def build_anwesenheit_pdf(
    sessions: list[dict[str, Any]], out_path: Path, combined: bool = False
) -> list[str]:
    """Render the attendance evaluation PDF; return the rendered team names.

    ``combined`` merges ``S`` and ``A`` into a single ``S+A`` column and keeps
    only the ``Quote P`` percentage.
    """
    teams = stats_per_team(sessions)
    font = "NotoSans" if _FONT_PATH.exists() else "Helvetica"
    bold_font = "NotoSans-Bold" if _FONT_BOLD_PATH.exists() else "Helvetica-Bold"

    LEFT_MARGIN = 14 * mm
    RIGHT_MARGIN = 14 * mm
    CONTENT_WIDTH = A4[0] - LEFT_MARGIN - RIGHT_MARGIN

    overline = ParagraphStyle(
        "ov",
        fontName=bold_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#0d6efd"),
        spaceAfter=1,
    )
    title = ParagraphStyle(
        "t",
        fontName=bold_font,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#222222"),
        spaceAfter=1,
    )
    subtitle = ParagraphStyle(
        "st",
        fontName=font,
        fontSize=10,
        leading=13,
        textColor=colors.grey,
        spaceAfter=0,
    )
    section = ParagraphStyle(
        "sec",
        fontName=bold_font,
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1f4e79"),
        spaceBefore=8,
        spaceAfter=2,
    )
    meta = ParagraphStyle(
        "meta",
        fontName=font,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#666666"),
        spaceAfter=4,
    )
    head = ParagraphStyle(
        "hd",
        fontName=bold_font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1f4e79"),
        alignment=1,
        spaceBefore=0,
        spaceAfter=0,
    )
    cell = ParagraphStyle(
        "cl",
        fontName=font,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#333333"),
        alignment=1,
        spaceBefore=0,
        spaceAfter=0,
    )
    name_cell = ParagraphStyle(
        "nm",
        parent=cell,
        alignment=0,
    )
    total_cell = ParagraphStyle(
        "tl",
        parent=cell,
        fontName=bold_font,
        textColor=colors.HexColor("#1f4e79"),
    )
    footnote = ParagraphStyle(
        "ft",
        fontName=font,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#777777"),
        spaceBefore=4,
    )

    band = Table(
        [
            [
                [
                    Paragraph("ANWESENHEIT · TRAINING", overline),
                    Paragraph("Anwesenheit – Auswertung", title),
                    Paragraph(f"Stand: {esc(german_now())}", subtitle),
                ]
            ]
        ],
        colWidths=[CONTENT_WIDTH],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4fb")),
            ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#cfe0f2")),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ],
    )

    story = [band, Spacer(1, 6)]
    if not teams:
        story.append(Paragraph("Keine Anwesenheitsdaten vorhanden.", section))
    for team, stats in teams.items():
        dates = sorted(s["date"] for s in sessions if s["team"] == team)
        span = ""
        if dates:
            first = dates[0].strftime("%d.%m.%Y")
            last = dates[-1].strftime("%d.%m.%Y")
            span = f"{first} – {last}"
        story.append(Paragraph(esc(team), section))
        story.append(
            Paragraph(
                f"{len(stats)} Spieler · {len(dates)} Trainingstermine{(' · ' + span) if span else ''}",
                meta,
            )
        )
        headers, col_widths = _columns(combined)
        rows: list[list[Paragraph]] = [
            [_cell(h, head) for h in headers],
        ]
        for ps in stats:
            rows.append(_make_row(_player_values(ps, combined), name_cell, cell))
        rows.append(
            _make_row(_player_values(_totals(stats), combined), total_cell, total_cell)
        )
        table = Table(
            rows,
            colWidths=col_widths,
            repeatRows=1,
        )
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef4fb")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9dee7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e3ebf5")),
        ]
        for row in range(2, len(rows) - 1, 2):
            style.append(
                ("BACKGROUND", (0, row), (-1, row), colors.HexColor("#f6f9fc"))
            )
        table.setStyle(TableStyle(style))
        story.append(table)

    legend = " · ".join(
        f"{code} = {label}"
        for code, label in STATUS_LABELS.items()
        if not (combined and code == "S")
    )
    story.append(Paragraph(f"Legende: {legend}", footnote))
    story.append(Paragraph(esc(german_now()), footnote))

    SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Anwesenheit – Auswertung",
    ).build(story)
    return list(teams)


def cli_main(argv: list[str] | None = None) -> int:
    """Standalone CLI for scaffolding a new training session entry."""
    ap = argparse.ArgumentParser(
        description="Training attendance evaluation and session scaffolding."
    )
    ap.add_argument(
        "--new",
        action="store_true",
        help="Scaffold a new session entry in anwesenheit.json for a team and "
        "date, pre-filling every roster player with status N",
    )
    ap.add_argument(
        "--team",
        default=None,
        help="Team alias/name (must match a key in roster.json for --new)",
    )
    ap.add_argument(
        "--date",
        default=None,
        help="Session date as 2026-09-21 or 21.09.2026 (required with --new)",
    )
    ap.add_argument(
        "--file",
        default=None,
        help="Path to anwesenheit.json (default: <script_dir>/anwesenheit.json)",
    )
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.new:
        ap.error("only --new is supported")
    if not args.team or not args.date:
        ap.error("--new requires --team and --date")
    d = parse_session_date(args.date)
    if d is None:
        ap.error(f"ungültiges Datum: {args.date}")
    path = Path(args.file) if args.file else DEFAULT_PATH

    roster = kapitane.load_roster()
    players = roster.get(args.team, [])
    data = load_data(path)
    if session_exists(data["sessions"], args.team, d):
        print(
            f"Warnung: Eintrag für '{args.team}' am {d.strftime(CSV_DATE_FORMAT)} "
            "existiert bereits – nicht angelegt.",
            file=sys.stderr,
        )
        return 1
    data["sessions"].append(new_session(args.team, d, players))
    save_data(data["sessions"], path)
    print(
        f"Anwesenheit: {args.team} am {d.strftime(CSV_DATE_FORMAT)} – "
        f"{len(players)} Spieler (alle 'N')."
    )
    if not players:
        print(
            f"Warnung: Kein Kader für '{args.team}' in {kapitane.ROSTER_NAME} "
            "– Eintrag ohne Spieler angelegt.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
