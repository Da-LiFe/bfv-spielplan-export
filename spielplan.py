"""Unified CLI entry point for the BFV-Spielplan-Export project.

Subcommands:
    fetch      Fetch CSV data from BFV and generate the overview page.
    overview   Generate the HTML overview page from existing CSV data.
    team       Generate a team-specific PDF for upcoming games.
    aufstellung Generate a lineup sheet PDF.
    anwesenheit Generate the attendance evaluation PDF.
    captains   Fill or check captain assignments.

Old entry points (visualize_spiele.py, fetch_bfv_spielplan.py,
aufstellung.py, anwesenheit.py) are thin wrappers that print a
deprecation notice and forward to the corresponding subcommand.
"""

from __future__ import annotations

import argparse
import sys

from config import SCRIPT_DIR

# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch CSV data and generate the overview page."""
    import fetch_bfv_spielplan as fbv

    extra: list[str] = []
    if args.url:
        extra.append(args.url)
    if args.output:
        extra.append(args.output)
    if args.refresh:
        extra.append("--refresh")
    if args.teams:
        extra.extend(["--teams", args.teams])

    return fbv.main(extra)


def cmd_overview(args: argparse.Namespace) -> int:
    """Generate the HTML overview page from existing CSV data."""
    from games import group_by_day, load_games
    from render_html import build_html

    games, _, sources = load_games()
    days = group_by_day(games)
    out_path = args.out or SCRIPT_DIR / "spielplan.html"
    build_html(days, [], sources, out_path)
    print(f"HTML: {out_path}")
    return 0


def cmd_team(args: argparse.Namespace) -> int:
    """Generate a team-specific PDF for upcoming games."""
    import kapitane
    from games import load_games, next_games_for_team, resolve_team, slugify
    from pdf_team import build_team_pdf

    games, _, sources = load_games()
    source = resolve_team(sources, args.name)
    team = source["team"]
    next_games = next_games_for_team(games, team, args.next)
    if not next_games:
        print(f"Keine bevorstehenden Spiele für '{team}' gefunden.", file=sys.stderr)
        return 1
    slug = slugify(team)
    out_path = args.out or SCRIPT_DIR / f"{slug}_spiele.pdf"

    # Compute captain assignments using the shared lookup
    cfg = kapitane.load_all(
        SCRIPT_DIR / kapitane.CONFIG_NAME, SCRIPT_DIR / kapitane.ROSTER_NAME
    )
    candidate_names = {team}
    from util import match_team

    for team_name in cfg.teams:
        if match_team([team_name], team):
            candidate_names.add(team_name)
    captain_by_week = (
        kapitane.captains_for(cfg, candidate_names)
        if candidate_names & set(cfg.assignments)
        else {}
    )

    build_team_pdf(next_games, team, sources, out_path, args.next, captain_by_week)
    print(f"{args.next} kommende Spiele für {team}")
    print(f"PDF: {out_path}")
    return 0


def cmd_aufstellung(args: argparse.Namespace) -> int:
    """Generate a lineup sheet PDF."""
    import aufstellung

    extra: list[str] = []
    if args.new:
        extra.append("--new")
    if args.date:
        extra.extend(["--date", args.date])
    if args.out:
        extra.extend(["--out", args.out])
    return aufstellung.cli_main([args.team] + extra)


def cmd_anwesenheit(args: argparse.Namespace) -> int:
    """Generate the attendance evaluation PDF."""
    import anwesenheit

    extra: list[str] = []
    if args.team:
        extra.extend(["--team", args.team])
    if args.kombiniert:
        extra.append("--kombiniert")
    if args.new:
        extra.append("--new")
    if args.date:
        extra.extend(["--date", args.date])
    if args.file:
        extra.extend(["--file", args.file])
    if args.out:
        extra.extend(["--out", args.out])
    return anwesenheit.cli_main(extra)


def cmd_captains(args: argparse.Namespace) -> int:
    """Fill or check captain assignments."""
    from games import load_games
    from visualize_spiele import handle_captains

    games, _, sources = load_games()
    handle_captains(games, sources, args.assign, args.check)
    return 0


# ---------------------------------------------------------------------------
# CLI setup
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="spielplan.py",
        description="BFV-Spielplan-Export – unified CLI entry point.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_p = subparsers.add_parser("fetch", help="Fetch CSV data from BFV")
    fetch_p.add_argument(
        "url", nargs="?", default="", help="BFV URL (default: from config)"
    )
    fetch_p.add_argument(
        "output", nargs="?", default="", help="Output path (default: spielplan.html)"
    )
    fetch_p.add_argument(
        "--refresh", action="store_true", help="Force refresh even if data is fresh"
    )
    fetch_p.add_argument("--teams", default=None, help="Teams config path")

    # overview
    overview_p = subparsers.add_parser("overview", help="Generate HTML overview page")
    overview_p.add_argument(
        "--out", default=None, help="Output path (default: spielplan.html)"
    )

    # team
    team_p = subparsers.add_parser("team", help="Generate team-specific PDF")
    team_p.add_argument("name", help="Team name")
    team_p.add_argument(
        "--next", type=int, default=3, help="Number of upcoming games (default: 3)"
    )
    team_p.add_argument("--out", default=None, help="Output path")

    # aufstellung
    aufstellung_p = subparsers.add_parser(
        "aufstellung", help="Generate lineup sheet PDF"
    )
    aufstellung_p.add_argument("team", help="Team name")
    aufstellung_p.add_argument(
        "--date", default=None, help="Date (TT.MM.JJJJ, default: today)"
    )
    aufstellung_p.add_argument("--new", action="store_true", help="Create new lineup")
    aufstellung_p.add_argument("--out", default=None, help="Output path")

    # anwesenheit
    anwesenheit_p = subparsers.add_parser(
        "anwesenheit", help="Generate attendance evaluation PDF"
    )
    anwesenheit_p.add_argument("--team", default=None, help="Filter by team")
    anwesenheit_p.add_argument(
        "--kombiniert", action="store_true", help="Combined S+A view"
    )
    anwesenheit_p.add_argument(
        "--new", action="store_true", help="Create new attendance data"
    )
    anwesenheit_p.add_argument("--date", default=None, help="Date (TT.MM.JJJJ)")
    anwesenheit_p.add_argument("--file", default=None, help="Input file")
    anwesenheit_p.add_argument("--out", default=None, help="Output path")

    # captains
    captains_p = subparsers.add_parser("captains", help="Manage captain assignments")
    captains_p.add_argument(
        "--assign", action="store_true", help="Auto-assign missing captains"
    )
    captains_p.add_argument(
        "--check", action="store_true", help="Check distribution balance"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and dispatch to the appropriate subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "fetch": cmd_fetch,
        "overview": cmd_overview,
        "team": cmd_team,
        "aufstellung": cmd_aufstellung,
        "anwesenheit": cmd_anwesenheit,
        "captains": cmd_captains,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


# ---------------------------------------------------------------------------
# Deprecation wrappers (called by old entry points)
# ---------------------------------------------------------------------------


def _deprecate(
    old_name: str, subcommand: str, extra_args: list[str] | None = None
) -> int:
    """Print a deprecation notice and forward to the new CLI."""
    print(
        f"Warnung: {old_name} ist veraltet. Verwende stattdessen: "
        f"spielplan.py {subcommand} {' '.join(extra_args or [])}",
        file=sys.stderr,
    )
    all_args = [subcommand] + (extra_args or [])
    return main(all_args)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(main())
