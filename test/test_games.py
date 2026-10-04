"""Tests for games.py: games between two club teams (T06)."""

import csv
import json
from datetime import date, timedelta

import pytest

import config
import games
import kapitane

CSV_HEADER = ["Wettbewerb", "Datum", "Uhrzeit", "Heim", "Gast", "Spielort", "Link"]
CSV_HEADER += ["Quelle"]
A_BFV, B_BFV = "TSV X U13", "TSV X U13 II"
A_URL, B_URL = "https://bfv/a", "https://bfv/b"


@pytest.fixture(autouse=True)
def _tmp_data(script_dir):
    return script_dir


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)


def row(day, heim, gast, quelle, link="", time="10:00"):
    return {
        "Wettbewerb": "Kreis",
        "Datum": day.strftime(config.CSV_DATE_FORMAT),
        "Uhrzeit": time,
        "Heim": heim,
        "Gast": gast,
        "Spielort": "Platz",
        "Link": link,
        "Quelle": quelle,
    }


def write_two_club_teams(tmp_path, link, aliases=True):
    """Team A and team B play each other once; each has one other game."""
    d0 = date.today() + timedelta(days=3)
    write_csv(
        tmp_path / "a_spiele_web.csv",
        [
            row(d0, A_BFV, B_BFV, A_URL, link),
            row(d0 + timedelta(days=7), A_BFV, "Other FC", A_URL, "https://x/2"),
        ],
    )
    write_csv(
        tmp_path / "b_spiele_web.csv",
        [
            row(d0, A_BFV, B_BFV, B_URL, link),
            row(d0 + timedelta(days=8), "Foo SV", B_BFV, B_URL, "https://x/3"),
        ],
    )
    teams = [{"url": A_URL, "alias": "Club A"}, {"url": B_URL, "alias": "Club B"}]
    (tmp_path / "teams.json").write_text(
        json.dumps(teams if aliases else []), encoding="utf-8"
    )
    return d0


@pytest.mark.parametrize("link", ["https://x/1", ""], ids=["link", "no-link"])
def test_club_internal_game_listed_once_but_seen_by_both(script_dir, link):
    d0 = write_two_club_teams(script_dir, link)
    all_games, _, sources = games.load_games()
    internal = [g for g in all_games if g["date"].date() == d0]
    assert len(internal) == 1
    assert (internal[0]["heim"], internal[0]["gast"]) == ("Club A", "Club B")
    assert len(all_games) == 3
    for team in ("Club A", "Club B"):
        upcoming = games.next_games_for_team(all_games, team, 9)
        assert d0 in [g["date"].date() for g in upcoming]
    weeks = kapitane.teams_duty_weeks(all_games, sources)
    assert kapitane.duty_week(d0) in weeks["Club A"]
    assert kapitane.duty_week(d0) in weeks["Club B"]


def test_dedupe_without_aliases(script_dir):
    d0 = write_two_club_teams(script_dir, "", aliases=False)
    all_games, _, _ = games.load_games()
    assert [g["date"].date() for g in all_games].count(d0) == 1


def test_shared_bfv_name_is_only_renamed_in_own_file(script_dir):
    """Two club teams with the same BFV name: never guess across files."""
    d0 = date.today() + timedelta(days=3)
    d1 = d0 + timedelta(days=7)
    write_csv(
        script_dir / "a_spiele_web.csv",
        [row(d0, A_BFV, "FC 1", A_URL, "l1"), row(d1, A_BFV, "FC 3", A_URL, "l3")],
    )
    write_csv(
        script_dir / "b_spiele_web.csv",
        [row(d0, "FC 2", A_BFV, B_URL, "l2"), row(d1, A_BFV, "FC 4", B_URL, "l4")],
    )
    teams = [{"url": A_URL, "alias": "Club A"}, {"url": B_URL, "alias": "Club B"}]
    (script_dir / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    all_games, _, _ = games.load_games()
    assert {(g["heim"], g["gast"]) for g in all_games} == {
        ("Club A", "FC 1"),
        ("Club A", "FC 3"),
        ("FC 2", "Club B"),
        ("Club B", "FC 4"),
    }


def test_bare_club_name_in_other_file_is_not_renamed(script_dir):
    """A name equal to another team's BFV name stays as BFV wrote it.

    Real case: cup games in the U15 W file list the team as the bare club
    name, which is also the inferred BFV name of the U17 W team.
    """
    d0 = date.today() + timedelta(days=3)
    d1 = d0 + timedelta(days=7)
    write_csv(
        script_dir / "a_spiele_web.csv",
        [row(d0, A_BFV, "FC 1", A_URL, "l1"), row(d1, "FC 2", A_BFV, A_URL, "l2")],
    )
    write_csv(
        script_dir / "b_spiele_web.csv",
        [
            row(d0, B_BFV, "FC 3", B_URL, "l3"),
            row(d1, B_BFV, "FC 4", B_URL, "l4"),
            row(d1, "Cup FC", A_BFV, B_URL, "cup"),  # not a duplicate
        ],
    )
    teams = [{"url": A_URL, "alias": "Club A"}, {"url": B_URL, "alias": "Club B"}]
    (script_dir / "teams.json").write_text(json.dumps(teams), encoding="utf-8")
    all_games, _, _ = games.load_games()
    cup = next(g for g in all_games if g["link"] == "cup")
    assert (cup["heim"], cup["gast"]) == ("Cup FC", A_BFV)
