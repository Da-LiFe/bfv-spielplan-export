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
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import aufstellung
import kapitane
from config import CSV_DATE_FORMAT, SCRIPT_DIR
from games import slugify
from pdf_common import (
    BOLD_FONT,
    CONTENT_WIDTH,
    FONT,
    PAGE_MARGIN,
    german_now,
)
from util import esc, load_json_strict, parse_date, write_json

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


def format_quota(pct: float) -> str:
    """Format a percentage as 'X.X%'."""
    return f"{pct:.1f}%"


def empty_data() -> dict[str, Any]:
    """Return an empty attendance dataset."""
    return {"sessions": [], "warnings": []}


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
        d = parse_date(session.get("date"))
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
    """Load and normalize ``anwesenheit.json``; invalid JSON raises ``SystemExit``."""
    data_path = path or DEFAULT_PATH
    raw = load_json_strict(data_path)
    data = normalize_data(raw)
    if data["warnings"]:
        for warning in data["warnings"]:
            print(f"Warnung: {warning}", file=sys.stderr)
        sys.exit(f"{data_path.name}: ungültige Einträge – nicht überschrieben.")
    return data


def save_data(sessions: list[dict[str, Any]], path: Path | None = None) -> None:
    """Write the sessions to ``anwesenheit.json`` atomically."""
    data_path = path or DEFAULT_PATH
    write_json(
        data_path,
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
    )


def session_exists(sessions: list[dict[str, Any]], team: str, d: date) -> bool:
    """Return whether a session for ``team`` on ``d`` already exists."""
    d = d if isinstance(d, date) else parse_date(d)  # type: ignore[assignment]
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
    font = FONT
    bold_font = BOLD_FONT

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

    # Get club logo (same as other PDFs)
    logo = aufstellung.get_logo(
        cache_path=SCRIPT_DIR / ".bfv_cache" / aufstellung.LOGO_CACHE_PATH.name
    )

    story = [
        aufstellung.build_club_header(
            "Anwesenheit – Auswertung",
            [f"Stand: {esc(german_now())}"],
            logo,
            CONTENT_WIDTH,
        ),
        Spacer(1, 6),
    ]
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
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Anwesenheit – Auswertung",
    ).build(story)
    return list(teams)


def run_report(
    team: str | None = None,
    out: str | Path | None = None,
    combined: bool = False,
    path: str | Path | None = None,
) -> int:
    """``spielplan.py anwesenheit``: render the attendance evaluation PDF."""
    data = load_data(Path(path) if path else SCRIPT_DIR / ANWESENHEIT_NAME)
    sessions = data["sessions"]
    if team:
        teams = sorted({s["team"] for s in sessions})
        if team not in teams:
            sys.exit(
                f"Team '{team}' nicht gefunden. Verf\u00fcgbare Teams: "
                f"{', '.join(teams) or 'keine'}"
            )
        sessions = [s for s in sessions if s["team"] == team]
        pdf_name = f"{slugify(team)}_anwesenheit.pdf"
    else:
        pdf_name = PDF_NAME
    out_path = Path(out) if out else SCRIPT_DIR / pdf_name
    teams_rendered = build_anwesenheit_pdf(sessions, out_path, combined)
    print(f"{len(sessions)} Trainingstermine aus {len(teams_rendered)} Team(s)")
    print(f"PDF:  {out_path}")
    return 0


def scaffold_session(team: str, day: date, path: str | Path | None = None) -> int:
    """``spielplan.py anwesenheit --new``: add a session with every player 'N'."""
    data_path = Path(path) if path else SCRIPT_DIR / ANWESENHEIT_NAME
    roster = kapitane.load_roster()
    players = roster.get(team, [])
    data = load_data(data_path)
    if session_exists(data["sessions"], team, day):
        print(
            f"Warnung: Eintrag f\u00fcr '{team}' am {day.strftime(CSV_DATE_FORMAT)} "
            "existiert bereits \u2013 nicht angelegt.",
            file=sys.stderr,
        )
        return 1
    data["sessions"].append(new_session(team, day, players))
    save_data(data["sessions"], data_path)
    print(
        f"Anwesenheit: {team} am {day.strftime(CSV_DATE_FORMAT)} \u2013 "
        f"{len(players)} Spieler (alle 'N')."
    )
    if not players:
        print(
            f"Warnung: Kein Kader f\u00fcr '{team}' in {kapitane.ROSTER_NAME} "
            "\u2013 Eintrag ohne Spieler angelegt.",
            file=sys.stderr,
        )
    return 0


def legacy_argv(argv: list[str]) -> list[str]:
    """Translate an old ``anwesenheit.py`` call into ``spielplan.py`` arguments."""
    ap = argparse.ArgumentParser(prog="anwesenheit.py")
    ap.add_argument("--new", action="store_true")
    ap.add_argument("--team", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--file", default=None)
    args = ap.parse_args(argv)
    if not args.new:
        ap.error("only --new is supported")
    if not args.team or not args.date:
        ap.error("--new requires --team and --date")
    new = ["anwesenheit", "--new", "--team", args.team, "--date", args.date]
    if args.file:
        new += ["--file", args.file]
    return new


if __name__ == "__main__":
    import spielplan

    sys.exit(spielplan.deprecated("anwesenheit.py", legacy_argv(sys.argv[1:])))
