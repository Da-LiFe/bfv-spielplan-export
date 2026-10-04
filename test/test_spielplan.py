"""Tests for the new spielplan.py CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import spielplan


def test_build_parser_has_all_subcommands():
    parser = spielplan.build_parser()
    # Check that all expected subcommands exist
    subcommands = [
        "fetch",
        "overview",
        "team",
        "aufstellung",
        "anwesenheit",
        "captains",
    ]
    # Get subparser choices from the parser
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices is not None:
            for cmd in subcommands:
                assert cmd in action.choices, f"Missing subcommand: {cmd}"


def test_cmd_overview(tmp_path, monkeypatch):
    """Test that cmd_overview generates an HTML file."""
    # Create a dummy CSV file
    csv_path = tmp_path / "test_spiele_web.csv"
    csv_path.write_text(
        "Datum,Uhrzeit,Heim,Gast,Wettbewerb,Spielort,Link,Quelle\n"
        "02.05.2026,10:00,Team A,Team B,Liga,Sportplatz,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(spielplan, "SCRIPT_DIR", tmp_path)
    # Mock load_games to return empty data
    monkeypatch.setattr(
        "games.load_games",
        lambda: ([], [], []),
    )
    monkeypatch.setattr(
        "games.group_by_day",
        lambda games: {},
    )
    # Mock build_html to capture the output path
    captured_out: Path | None = None

    def mock_build_html(*args, **kwargs):
        nonlocal captured_out
        captured_out = args[3] if len(args) > 3 else kwargs.get("out_path")

    monkeypatch.setattr("render_html.build_html", mock_build_html)

    args = argparse.Namespace(out=None)
    rc = spielplan.cmd_overview(args)
    assert rc == 0
    assert captured_out == tmp_path / "spielplan.html"


def test_cmd_team(tmp_path, monkeypatch):
    """Test that cmd_team generates a team PDF."""
    captured_out: Path | None = None

    def mock_load_games():
        return (
            [
                {
                    "date": "2026-05-02",
                    "time": "10:00",
                    "heim": "Team A",
                    "gast": "Team B",
                    "wettbewerb": "Liga",
                    "spielort": "Sportplatz",
                    "link": "",
                    "quelle": "",
                    "source": "test_spiele_web.csv",
                    "is_home": True,
                    "home_color": "#ff0000",
                    "away_color": "#0000ff",
                    "datum": "02.05.2026",
                    "wd": "Donnerstag",
                }
            ],
            ["Team A"],
            [{"team": "Team A", "url": ""}],
        )

    def mock_build_team_pdf(*args, **kwargs):
        nonlocal captured_out
        captured_out = args[3] if len(args) > 3 else kwargs.get("out_path")

    def mock_resolve_team(sources, name):
        return sources[0]

    monkeypatch.setattr("games.load_games", mock_load_games)
    monkeypatch.setattr("games.resolve_team", mock_resolve_team)
    monkeypatch.setattr("games.next_games_for_team", lambda games, team, n: games[:n])
    monkeypatch.setattr("pdf_team.build_team_pdf", mock_build_team_pdf)

    args = argparse.Namespace(name="Team A", next=3, out=None)
    rc = spielplan.cmd_team(args)
    assert rc == 0
    assert captured_out is not None


def test_deprecate_prints_notice(capsys):
    """Test that _deprecate prints a deprecation notice."""
    with pytest.raises(SystemExit):
        spielplan._deprecate("old_script.py", "team", ["MyTeam"])
    stderr = capsys.readouterr().err
    assert "Warnung" in stderr
    assert "old_script.py" in stderr
    assert "spielplan.py team MyTeam" in stderr


def test_deprecate_forwards_args(monkeypatch):
    """Test that _deprecate forwards args to main()."""
    captured_argv: list[str] | None = None

    def mock_main(argv):
        nonlocal captured_argv
        captured_argv = argv
        return 0

    monkeypatch.setattr(spielplan, "main", mock_main)
    spielplan._deprecate("old.py", "team", ["MyTeam", "--next", "5"])
    assert captured_argv == ["team", "MyTeam", "--next", "5"]
