"""Deprecated entry point; use ``python spielplan.py <command>``.

Translates the old options into the matching ``spielplan.py`` command:

    visualize_spiele.py                          -> overview
    visualize_spiele.py --team X [--next N]      -> team X [--next N]
    visualize_spiele.py --aufstellung --team X   -> aufstellung X
    visualize_spiele.py --anwesenheit [--team X] -> anwesenheit [--team X]
    visualize_spiele.py --captains-assign/-check -> captains --assign/--check
"""

from __future__ import annotations

import argparse
import sys

import spielplan


def legacy_argv(argv: list[str]) -> list[str]:
    """Translate old ``visualize_spiele.py`` options into ``spielplan.py`` ones."""
    ap = argparse.ArgumentParser(prog="visualize_spiele.py")
    ap.add_argument("--team", default=None)
    ap.add_argument("--next", type=int, default=4)
    ap.add_argument("--out", default=None)
    ap.add_argument("--anwesenheit", action="store_true")
    ap.add_argument("--kombiniert", action="store_true")
    ap.add_argument("--captains-assign", action="store_true")
    ap.add_argument("--captains-check", action="store_true")
    ap.add_argument("--aufstellung", action="store_true")
    ap.add_argument("--date", default=None)
    args = ap.parse_args(argv)
    out = ["--out", args.out] if args.out else []

    if args.aufstellung:
        if not args.team:
            sys.exit("--aufstellung ben\u00f6tigt --team.")
        date = ["--date", args.date] if args.date else []
        return ["aufstellung", args.team, *date, *out]
    if args.anwesenheit:
        team = ["--team", args.team] if args.team else []
        combined = ["--kombiniert"] if args.kombiniert else []
        return ["anwesenheit", *team, *combined, *out]
    if args.captains_assign or args.captains_check:
        return [
            "captains",
            *(["--assign"] if args.captains_assign else []),
            *(["--check"] if args.captains_check else []),
        ]
    if args.team:
        return ["team", args.team, "--next", str(args.next), *out]
    return ["overview"]


def main(argv: list[str] | None = None) -> int:
    """Run the old command line via ``spielplan.py``; return its exit code."""
    new_argv = legacy_argv(sys.argv[1:] if argv is None else argv)
    return spielplan.deprecated("visualize_spiele.py", new_argv)


if __name__ == "__main__":
    sys.exit(main())
