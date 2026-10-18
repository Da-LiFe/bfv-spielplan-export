"""Tests for games.py: deduplication (T06), sorting (T12)."""

import csv
import json
from datetime import date, datetime, timedelta

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


def game(datum, time):
    d = datetime.strptime(datum, "%d.%m.%Y")
    return {"date": d, "datum": datum, "time": time, "heim": "H", "gast": "G"}


def test_group_by_day_sorts_times_numerically():
    """T12: 9:00 comes before 10:00; games without time come last."""
    day = [game("01.05.2026", t) for t in ("10:00", "", "9:00")]
    days = games.group_by_day(day)
    assert [g["time"] for g in days["01.05.2026"]] == ["9:00", "10:00", ""]


def test_group_by_day_does_not_mutate_input():
    """T12: the caller's list keeps its order."""
    original = [game("02.05.2026", "10:00"), game("01.05.2026", "9:00")]
    snapshot = list(original)
    games.group_by_day(original)
    assert original == snapshot


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


# ------------------------------------------------ _zusatz_spiele.csv (extra games)

Z_URL = "https://www.bfv.de/mannschaften/club-a/0123456789abcdef"
Z_SLUG = "club-a"
Z_ALIAS = "Club A"


def write_zusatz(tmp_path, slug, rows):
    write_csv(tmp_path / f"{slug}_zusatz_spiele.csv", rows)


def write_teams(tmp_path):
    teams = [{"url": Z_URL, "alias": Z_ALIAS}]
    (tmp_path / "teams.json").write_text(json.dumps(teams), encoding="utf-8")


def test_zusatz_adds_game_to_fetched_team(script_dir):
    d = date.today() + timedelta(days=5)
    write_csv(
        script_dir / f"{Z_SLUG}_spiele_web.csv",
        [row(d, A_BFV, "FC Beispiel", Z_URL, "l1")],
    )
    write_teams(script_dir)
    write_zusatz(
        script_dir,
        Z_SLUG,
        [row(d + timedelta(days=2), Z_ALIAS, "FC Extra", "", "", time="11:00")],
    )

    all_games, club_teams, sources = games.load_games()

    assert club_teams == [Z_ALIAS]
    assert len(sources) == 1
    assert sources[0]["file"] == f"{Z_SLUG}_spiele_web.csv"
    assert sources[0]["url"] == Z_URL
    extra = next(g for g in all_games if g["gast"] == "FC Extra")
    assert extra["heim"] == Z_ALIAS
    assert extra["source"] == f"{Z_SLUG}_zusatz_spiele.csv"


def test_zusatz_only_team_gets_alias_and_source(script_dir):
    d = date.today() + timedelta(days=5)
    write_teams(script_dir)
    write_zusatz(script_dir, Z_SLUG, [row(d, Z_ALIAS, "FC Extra", "", "")])

    all_games, club_teams, sources = games.load_games()

    assert club_teams == [Z_ALIAS]
    assert sources[0]["file"] == f"{Z_SLUG}_zusatz_spiele.csv"
    assert sources[0]["url"] == Z_URL
    assert (all_games[0]["heim"], all_games[0]["gast"]) == (Z_ALIAS, "FC Extra")


def test_zusatz_bfv_name_is_aliased(script_dir):
    d = date.today() + timedelta(days=5)
    write_csv(
        script_dir / f"{Z_SLUG}_spiele_web.csv",
        [row(d, A_BFV, "FC Beispiel", Z_URL, "l1")],
    )
    write_teams(script_dir)
    write_zusatz(
        script_dir, Z_SLUG, [row(d + timedelta(days=7), A_BFV, "FC Extra", "", "")]
    )

    all_games, _, _ = games.load_games()

    extra = next(g for g in all_games if g["gast"] == "FC Extra")
    assert extra["heim"] == Z_ALIAS


def test_zusatz_survives_refresh(script_dir):
    d = date.today() + timedelta(days=5)
    fetched = script_dir / f"{Z_SLUG}_spiele_web.csv"
    write_csv(fetched, [row(d, A_BFV, "FC Beispiel", Z_URL, "l1")])
    write_teams(script_dir)
    write_zusatz(
        script_dir, Z_SLUG, [row(d + timedelta(days=2), Z_ALIAS, "FC Extra", "", "")]
    )

    games.load_games()
    # A refresh rewrites the fetched file; the zusatz file is not touched.
    write_csv(fetched, [row(d + timedelta(days=9), A_BFV, "FC New", Z_URL, "l9")])
    all_games, _, _ = games.load_games()

    gasts = {g["gast"] for g in all_games}
    assert "FC Extra" in gasts
    assert "FC New" in gasts
    assert "FC Beispiel" not in gasts


def test_fetched_vs_fetched_still_dedupes_silently(script_dir):
    d = date.today() + timedelta(days=3)
    write_two_club_teams(script_dir, "https://x/1")
    all_games, _, _ = games.load_games()
    assert [g["date"].date() for g in all_games].count(d) == 1


@pytest.mark.parametrize(
    "extra_heim, extra_link",
    [(Z_ALIAS, ""), (A_BFV, ""), (Z_ALIAS, "l1")],
    ids=["alias-no-link", "bfv-name-no-link", "same-link"],
)
def test_zusatz_duplicate_of_fetched_aborts(script_dir, extra_heim, extra_link):
    d = date.today() + timedelta(days=5)
    write_csv(
        script_dir / f"{Z_SLUG}_spiele_web.csv",
        [row(d, A_BFV, "FC Beispiel", Z_URL, "l1")],
    )
    write_teams(script_dir)
    write_zusatz(
        script_dir, Z_SLUG, [row(d, extra_heim, "FC Beispiel", "", extra_link)]
    )

    with pytest.raises(SystemExit, match="steht schon in"):
        games.load_games()


def test_zusatz_duplicate_within_file_aborts(script_dir):
    d = date.today() + timedelta(days=5)
    write_teams(script_dir)
    write_zusatz(
        script_dir,
        Z_SLUG,
        [row(d, Z_ALIAS, "FC Extra", "", ""), row(d, Z_ALIAS, "FC Extra", "", "")],
    )

    with pytest.raises(SystemExit, match="steht schon in"):
        games.load_games()


def test_zusatz_unknown_slug_aborts(script_dir):
    write_teams(script_dir)
    write_zusatz(
        script_dir,
        "ghost",
        [row(date.today() + timedelta(days=5), "Ghost", "FC Extra", "", "")],
    )

    with pytest.raises(SystemExit, match="kein Team mit dem Slug 'ghost'"):
        games.load_games()


def test_zusatz_invalid_rows_warn(script_dir, capsys):
    write_teams(script_dir)
    bad = row(date.today() + timedelta(days=5), Z_ALIAS, "FC Extra", "", "")
    bad["Datum"] = "kaputt"
    no_team = row(date.today() + timedelta(days=6), Z_ALIAS, "", "", "")
    write_zusatz(script_dir, Z_SLUG, [bad, no_team])

    all_games, club_teams, sources = games.load_games()

    assert all_games == []
    assert club_teams == []
    assert sources == []
    err = capsys.readouterr().err
    assert f"1 Zeile(n) in {Z_SLUG}_zusatz_spiele.csv wegen ungültigen Datums" in err
    assert f"1 Zeile(n) in {Z_SLUG}_zusatz_spiele.csv ohne Heim/Gast-Team" in err
