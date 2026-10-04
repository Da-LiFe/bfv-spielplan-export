"""CLI entry point for the Spielplan exporter.

All game loading, HTML rendering and PDF generation logic lives in
``games``, ``render_html``, ``pdf_overview`` and ``pdf_team``.
This module only contains argument parsing and handler dispatch.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import anwesenheit
import aufstellung
import kapitane
from config import CSV_DATE_FORMAT, SCRIPT_DIR, WD  # noqa: F401 (used by tests)
from games import (  # noqa: F401 (used by tests)
    Game,
    find_team_game,
    group_by_day,
    load_alias_map,
    load_games,
    next_games_for_team,
    resolve_team,
    short_place,
    slugify,
    team_color,
)
from pdf_common import german_now  # noqa: F401 (used by tests)
from pdf_overview import build_pdf
from pdf_team import _get_logo as club_logo
from pdf_team import build_team_pdf
from render_html import (  # noqa: F401 (used by tests)
    build_html,
    render_day_section,
    render_footer,
    render_game_row,
    render_games_js,
    render_team_checks,
)
from util import esc, match_team, parse_date  # noqa: F401 (used by tests)


def handle_captains(
    games: list[Game], sources: list, assign: bool, check: bool
) -> None:
    """Fill and/or verify the Kapit\u00e4n assignments from roster.json/kapitane.json."""
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
                f"Team '{team}' nicht gefunden. Verf\u00fcgbare Teams: "
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


def handle_aufstellung(
    team_arg: str | None, date_arg: str | None, out: str | None
) -> None:
    """Render the lineup sheet of one game from aufstellungen.json."""
    if not team_arg:
        sys.exit("--aufstellung ben\u00f6tigt --team.")
    day = None
    if date_arg:
        day = aufstellung.parse_date(date_arg)
        if day is None:
            sys.exit(f"Ung\u00fcltiges Datum '{date_arg}' (erwartet YYYY-MM-DD).")

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
            f"Keine Aufstellung f\u00fcr '{team_arg}' gefunden. Teams mit Aufstellung: "
            f"{', '.join(available) or 'keine'}"
        )
    lineup = aufstellung.select_lineup(team_lineups, day)
    if lineup is None:
        dates = ", ".join(lu.date.isoformat() for lu in team_lineups)
        what = f"Aufstellung am {day.isoformat()}" if day else "kommende Aufstellung"
        sys.exit(f"Keine {what} f\u00fcr '{team_arg}'. Vorhandene Termine: {dates}")

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
            "in den *_spiele_web.csv \u2013 Gegner und Treffpunkt unbekannt.",
            file=sys.stderr,
        )

    week = kapitane.duty_week(lineup.date)
    # Merge captain assignments across all name variants (alias, lineup team name)
    cfg = kapitane.load_all(
        SCRIPT_DIR / kapitane.CONFIG_NAME, SCRIPT_DIR / kapitane.ROSTER_NAME
    )
    candidate_names = {team, lineup.team}
    captain_by_week = kapitane.captains_for(cfg, candidate_names)
    captain = captain_by_week.get(week, "")

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
        "(default: <slug>_spiele.pdf / anwesenheit.pdf / "
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
        help="Verify the Kapit\u00e4n assignments are equally distributed and exit "
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
            sys.exit(f"Keine bevorstehenden Spiele f\u00fcr '{team}' gefunden.")
        out = Path(args.out) if args.out else SCRIPT_DIR / f"{slugify(team)}_spiele.pdf"
        cfg = kapitane.load_all(
            SCRIPT_DIR / kapitane.CONFIG_NAME, SCRIPT_DIR / kapitane.ROSTER_NAME
        )
        # Merge captain assignments across all name variants (alias, original, etc.)
        candidate_names = {team}
        for team_name in cfg.get("teams", {}):
            if match_team([team_name], team):
                candidate_names.add(team_name)
        captain_by_week = (
            kapitane.captains_for(cfg, candidate_names)
            if candidate_names & set(cfg["assignments"])
            else {}
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
        print(f"{len(next_games)} kommende Spiele f\u00fcr {team}")
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
                    f"Hinweis: Kapit\u00e4n offen f\u00fcr {rng} \u2013 "
                    "'--captains-assign' f\u00fchrt die Zuteilung durch.",
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
