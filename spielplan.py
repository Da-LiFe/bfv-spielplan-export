"""Command-line entry point: ``python spielplan.py <command>``.

Commands:
    fetch        Fetch one team's games from BFV, or all teams (``--refresh``).
    overview     Write spielplan.html and spielplan.pdf from the game CSVs.
    team         PDF with the next games of one team.
    aufstellung  Lineup sheet PDF of one game, or a new lineup entry (``--new``).
    anwesenheit  Attendance evaluation PDF, or a new session entry (``--new``).
    captains     Assign (``--assign``) and/or check (``--check``) captains.

Each command calls the function of its feature module directly. The old
scripts (``visualize_spiele.py``, ``fetch_bfv_spielplan.py``,
``aufstellung.py``, ``anwesenheit.py``) translate their old options into
these commands via :func:`deprecated`.
"""

from __future__ import annotations

import argparse
import shlex
import sys

from util import parse_date


def cmd_fetch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import fetch_bfv_spielplan

    if not args.url and not args.refresh:
        parser.error("URL oder --refresh angeben")
    return fetch_bfv_spielplan.run_fetch(
        args.url, args.output, args.refresh, args.teams
    )


def cmd_overview(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import pdf_overview

    return pdf_overview.run_overview()


def cmd_team(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import pdf_team

    return pdf_team.run_team(args.name, args.next, args.out)


def cmd_aufstellung(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import aufstellung

    if not args.new:
        return aufstellung.run_lineup(args.team, args.date, args.out)
    if args.out:
        parser.error("--out geht nicht zusammen mit --new")
    if not args.date:
        parser.error("--new braucht --date")
    day = parse_date(args.date)
    if day is None:
        parser.error(f"ungültiges Datum: {args.date}")
    return aufstellung.scaffold_lineup(args.team, day)


def cmd_anwesenheit(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import anwesenheit

    if not args.new:
        if args.date:
            parser.error("--date gibt es nur zusammen mit --new")
        return anwesenheit.run_report(args.team, args.out, args.kombiniert, args.file)
    if args.out or args.kombiniert:
        parser.error("--out/--kombiniert gehen nicht zusammen mit --new")
    if not args.team or not args.date:
        parser.error("--new braucht --team und --date")
    day = parse_date(args.date)
    if day is None:
        parser.error(f"ungültiges Datum: {args.date}")
    return anwesenheit.scaffold_session(args.team, day, args.file)


def cmd_captains(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import kapitane

    return kapitane.run_captains(args.assign, args.check)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="spielplan.py",
        description="BFV-Spielplan-Export: Spielpläne, Team-PDFs, Aufstellungen, "
        "Anwesenheit und Kapitäne.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser("fetch", help="Spiele eines Teams oder aller Teams laden")
    p.add_argument("url", nargs="?", help="BFV-Mannschaftsseite (URL)")
    p.add_argument(
        "output", nargs="?", help="CSV-Pfad (Standard: <slug>_spiele_web.csv)"
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="alle Teams aus teams.json neu laden und die Übersicht neu erzeugen",
    )
    p.add_argument("--teams", help="Pfad zur teams.json (Standard: neben dem Skript)")
    p.set_defaults(handler=cmd_fetch, cmd_parser=p)

    p = sub.add_parser(
        "overview", help="spielplan.html und spielplan.pdf aus den CSVs erzeugen"
    )
    p.set_defaults(handler=cmd_overview, cmd_parser=p)

    p = sub.add_parser("team", help="PDF mit den nächsten Spielen eines Teams")
    p.add_argument("name", help="Alias oder BFV-Name des Teams")
    p.add_argument(
        "--next", type=int, default=4, help="Anzahl der Spiele (Standard: 4)"
    )
    p.add_argument("--out", help="PDF-Pfad (Standard: <slug>_spiele.pdf)")
    p.set_defaults(handler=cmd_team, cmd_parser=p)

    p = sub.add_parser(
        "aufstellung", help="Aufstellungsbogen als PDF, oder neuen Eintrag anlegen"
    )
    p.add_argument("team", help="Alias oder BFV-Name des Teams")
    p.add_argument(
        "--date",
        help="Spieltag als YYYY-MM-DD oder TT.MM.JJJJ (Standard: nächste Aufstellung; "
        "Pflicht mit --new)",
    )
    p.add_argument(
        "--new",
        action="store_true",
        help="neuen Eintrag in aufstellungen.json mit dem ganzen Kader anlegen",
    )
    p.add_argument("--out", help="PDF-Pfad (Standard: <slug>_aufstellung_<datum>.pdf)")
    p.set_defaults(handler=cmd_aufstellung, cmd_parser=p)

    p = sub.add_parser(
        "anwesenheit", help="Anwesenheits-Auswertung als PDF, oder neuen Termin anlegen"
    )
    p.add_argument("--team", help="nur dieses Team (Pflicht mit --new)")
    p.add_argument(
        "--kombiniert",
        action="store_true",
        help="S und A in einer Spalte, nur Quote P",
    )
    p.add_argument(
        "--new",
        action="store_true",
        help="neuen Trainingstermin anlegen (alle Spieler 'N')",
    )
    p.add_argument("--date", help="Trainingstag (nur mit --new)")
    p.add_argument("--file", help="Pfad zur anwesenheit.json")
    p.add_argument(
        "--out", help="PDF-Pfad (Standard: anwesenheit.pdf / <slug>_anwesenheit.pdf)"
    )
    p.set_defaults(handler=cmd_anwesenheit, cmd_parser=p)

    p = sub.add_parser("captains", help="Kapitäne zuteilen und/oder prüfen")
    p.add_argument(
        "--assign",
        action="store_true",
        help="fehlende Wochen in kapitane.json reihum zuteilen",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Verteilung prüfen; Exit-Code 1 wenn ungleich",
    )
    p.set_defaults(handler=cmd_captains, cmd_parser=p)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and run the selected command; return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args, args.cmd_parser))


def deprecated(old_name: str, new_argv: list[str]) -> int:
    """Print one deprecation line for ``old_name`` and run ``new_argv``."""
    print(
        f"Hinweis: {old_name} ist veraltet, verwende: "
        f"python spielplan.py {shlex.join(new_argv)}",
        file=sys.stderr,
    )
    return main(new_argv)


if __name__ == "__main__":
    sys.exit(main())
