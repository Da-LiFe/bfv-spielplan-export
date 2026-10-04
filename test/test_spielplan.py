"""Tests for the ``spielplan.py`` CLI and the deprecated entry points."""

import csv
import json
import runpy
from datetime import date, timedelta
from pathlib import Path

import pytest
from pdfminer.high_level import extract_text

import anwesenheit
import aufstellung
import config
import fetch_bfv_spielplan
import kapitane
import pdf_overview
import pdf_team
import spielplan
import visualize_spiele

ROOT = Path(__file__).resolve().parent.parent
CSV_HEADER = ["Wettbewerb", "Datum", "Uhrzeit", "Heim", "Gast", "Spielort", "Link"]
CSV_HEADER += ["Quelle"]
BFV_NAME = "TSV Gilching/Argelsried U15"
ALIAS = "U15 Alias"
URL = "https://bfv/u15"


@pytest.fixture(autouse=True)
def _offline(script_dir, monkeypatch):
    """All data lives in tmp_path; the club logo is never downloaded."""
    monkeypatch.setattr(aufstellung, "get_logo", lambda **kw: None)
    return script_dir


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)


def row(day, heim, gast, link="", quelle=URL, time="10:00"):
    return {
        "Wettbewerb": "Kreis",
        "Datum": day.strftime(config.CSV_DATE_FORMAT),
        "Uhrzeit": time,
        "Heim": heim,
        "Gast": gast,
        "Spielort": "Sportpark",
        "Link": link,
        "Quelle": quelle,
    }


def write_team(tmp_path, days=(1, 8)):
    """One club team (BFV name ``BFV_NAME``, alias ``ALIAS``) with games."""
    today = date.today()
    rows = [row(today + timedelta(days=d), BFV_NAME, f"FC {d}") for d in days]
    write_csv(tmp_path / "u15_spiele_web.csv", rows)
    (tmp_path / "teams.json").write_text(
        json.dumps([{"url": URL, "alias": ALIAS}]), encoding="utf-8"
    )


def real_logo(tmp_path):
    from PIL import Image

    logo = tmp_path / "logo.png"
    Image.new("RGB", (20, 20), "red").save(logo)
    return logo


# ------------------------------------------------- parsing + dispatch


@pytest.mark.parametrize(
    "argv, module, func, expected",
    [
        (
            ["fetch", "https://x", "o.csv", "--teams", "t.json"],
            fetch_bfv_spielplan,
            "run_fetch",
            ("https://x", "o.csv", False, "t.json"),
        ),
        (
            ["fetch", "--refresh"],
            fetch_bfv_spielplan,
            "run_fetch",
            (None, None, True, None),
        ),
        (["overview"], pdf_overview, "run_overview", ()),
        (["team", "X"], pdf_team, "run_team", ("X", 4, None)),
        (
            ["team", "X", "--next", "2", "--out", "o.pdf"],
            pdf_team,
            "run_team",
            ("X", 2, "o.pdf"),
        ),
        (
            ["aufstellung", "X", "--date", "2026-05-02", "--out", "o.pdf"],
            aufstellung,
            "run_lineup",
            ("X", "2026-05-02", "o.pdf"),
        ),
        (
            ["aufstellung", "X", "--new", "--date", "02.05.2026"],
            aufstellung,
            "scaffold_lineup",
            ("X", date(2026, 5, 2)),
        ),
        (
            ["anwesenheit", "--team", "X", "--kombiniert", "--out", "o.pdf"],
            anwesenheit,
            "run_report",
            ("X", "o.pdf", True, None),
        ),
        (
            ["anwesenheit", "--new", "--team", "X", "--date", "2026-09-21"],
            anwesenheit,
            "scaffold_session",
            ("X", date(2026, 9, 21), None),
        ),
        (["captains", "--assign", "--check"], kapitane, "run_captains", (True, True)),
    ],
)
def test_subcommand_dispatch(monkeypatch, argv, module, func, expected):
    calls = []
    monkeypatch.setattr(module, func, lambda *a: calls.append(a) or 7)
    assert spielplan.main(argv) == 7
    assert calls == [expected]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["fetch"],
        ["team"],
        ["team", "X", "--next", "drei"],
        ["aufstellung", "X", "--new"],
        ["aufstellung", "X", "--new", "--date", "morgen"],
        ["aufstellung", "X", "--new", "--date", "2026-05-02", "--out", "o.pdf"],
        ["anwesenheit", "--new", "--team", "X"],
        ["anwesenheit", "--new", "--date", "2026-09-21"],
        ["anwesenheit", "--new", "--team", "X", "--date", "kaputt"],
        ["anwesenheit", "--new", "--team", "X", "--date", "2026-09-21", "--kombiniert"],
        ["anwesenheit", "--date", "2026-09-21"],
    ],
)
def test_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        spielplan.main(argv)
    assert exc.value.code == 2


# ------------------------------------------------------------ end-to-end


def test_overview_writes_html_and_pdf(script_dir, capsys):
    write_team(script_dir)
    assert spielplan.main(["overview"]) == 0
    html = (script_dir / "spielplan.html").read_text(encoding="utf-8")
    assert f'data-team="{ALIAS}"' in html  # club team filter is populated
    assert (script_dir / "spielplan.pdf").read_bytes()[:4] == b"%PDF"
    assert "2 Spiele aus 1 Dateien" in capsys.readouterr().out


def test_overview_without_csvs():
    with pytest.raises(SystemExit, match="Keine .*_spiele_web.csv"):
        spielplan.main(["overview"])


def test_team_pdf_logo_captain_and_hint(script_dir, monkeypatch, capsys):
    """T04: a captain stored under the original BFV name shows up."""
    write_team(script_dir, days=(1, 8, 15, 22, 29))
    first = kapitane.duty_week(date.today() + timedelta(days=1))
    (script_dir / "kapitane.json").write_text(
        json.dumps({"assignments": {BFV_NAME.lower(): {first: "Lena"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(aufstellung, "get_logo", lambda **kw: real_logo(script_dir))
    assert spielplan.main(["team", ALIAS]) == 0
    out = script_dir / "u15-alias_spiele.pdf"
    text = extract_text(str(out))
    assert "Lena" in text
    assert "folgt" in text
    assert b"/Subtype /Image" in out.read_bytes()
    captured = capsys.readouterr()
    assert "4 kommende Spiele" in captured.out  # default --next is 4
    assert "Kapitän offen" in captured.err


def test_team_next_must_be_positive():
    with pytest.raises(SystemExit, match="must be a positive"):
        spielplan.main(["team", ALIAS, "--next", "0"])


def test_aufstellung_pdf_captain_under_original_name(script_dir, capsys):
    """T04: the lineup sheet finds the same captain as the team PDF."""
    write_team(script_dir)
    day = date.today() + timedelta(days=1)
    roster = [{"name": "Lena", "number": 1}, {"name": "Max", "number": 2}]
    aufstellung.save_lineups(
        [aufstellung.new_lineup(ALIAS, day, roster)],
        script_dir / aufstellung.AUFSTELLUNGEN_NAME,
    )
    (script_dir / "kapitane.json").write_text(
        json.dumps({"assignments": {BFV_NAME: {kapitane.duty_week(day): "Max"}}}),
        encoding="utf-8",
    )
    assert spielplan.main(["aufstellung", ALIAS]) == 0
    out = script_dir / f"u15-alias_aufstellung_{day.isoformat()}.pdf"
    text = extract_text(str(out))
    assert "Kapitän der Woche" in text
    assert "Max" in text
    assert "gegen FC 1" in capsys.readouterr().out


def test_aufstellung_new_then_render(script_dir, monkeypatch):
    roster = script_dir / kapitane.ROSTER_NAME
    roster.write_text(json.dumps({"teams": {ALIAS: ["Lena", "Max"]}}), encoding="utf-8")
    monkeypatch.setattr(kapitane, "DEFAULT_ROSTER_PATH", roster)
    day = (date.today() + timedelta(days=1)).isoformat()
    assert spielplan.main(["aufstellung", ALIAS, "--new", "--date", day]) == 0
    assert (script_dir / aufstellung.AUFSTELLUNGEN_NAME).exists()
    assert spielplan.main(["aufstellung", ALIAS, "--date", day]) == 0


def test_anwesenheit_new_then_report(script_dir, capsys):
    rc = spielplan.main(
        ["anwesenheit", "--new", "--team", ALIAS, "--date", "2026-09-21"]
    )
    assert rc == 0
    assert (script_dir / anwesenheit.ANWESENHEIT_NAME).exists()
    assert spielplan.main(["anwesenheit", "--team", ALIAS, "--kombiniert"]) == 0
    out = script_dir / "u15-alias_anwesenheit.pdf"
    assert "Anwesenheit – Auswertung" in extract_text(str(out))
    # Same entry again: warning and exit code 1
    rc = spielplan.main(
        ["anwesenheit", "--new", "--team", ALIAS, "--date", "2026-09-21"]
    )
    assert rc == 1


def test_captains_assign_and_check(script_dir, capsys):
    write_team(script_dir)
    (script_dir / kapitane.ROSTER_NAME).write_text(
        json.dumps({"teams": {ALIAS: ["Lena", "Max"]}}), encoding="utf-8"
    )
    assert spielplan.main(["captains", "--assign", "--check"]) == 0
    cfg = json.loads((script_dir / "kapitane.json").read_text(encoding="utf-8"))
    assert sorted(cfg["assignments"][ALIAS].values()) == ["Lena", "Max"]
    out = capsys.readouterr().out
    assert out.count("Kapitän-Verteilung") == 1  # report printed once


def test_captains_without_csvs():
    with pytest.raises(SystemExit, match="Keine .*_spiele_web.csv"):
        spielplan.main(["captains", "--check"])


# ------------------------------------------------- deprecated entry points


@pytest.mark.parametrize(
    "old, new",
    [
        ([], ["overview"]),
        (["--next", "3"], ["overview"]),
        (["--team", "X"], ["team", "X", "--next", "4"]),
        (
            ["--team", "X", "--next", "2", "--out", "o.pdf"],
            ["team", "X", "--next", "2", "--out", "o.pdf"],
        ),
        (["--aufstellung", "--team", "X"], ["aufstellung", "X"]),
        (
            ["--aufstellung", "--team", "X", "--date", "2026-05-02", "--out", "o"],
            ["aufstellung", "X", "--date", "2026-05-02", "--out", "o"],
        ),
        (["--anwesenheit"], ["anwesenheit"]),
        (
            ["--anwesenheit", "--kombiniert", "--team", "X", "--out", "o"],
            ["anwesenheit", "--team", "X", "--kombiniert", "--out", "o"],
        ),
        (["--captains-assign"], ["captains", "--assign"]),
        (["--captains-check"], ["captains", "--check"]),
        (
            ["--captains-assign", "--captains-check"],
            ["captains", "--assign", "--check"],
        ),
    ],
)
def test_visualize_spiele_legacy_argv(old, new):
    assert visualize_spiele.legacy_argv(old) == new


def test_visualize_spiele_aufstellung_needs_team():
    with pytest.raises(SystemExit, match="benötigt --team"):
        visualize_spiele.legacy_argv(["--aufstellung"])


def test_aufstellung_legacy_argv():
    assert aufstellung.legacy_argv(["--new", "--team", "X", "--date", "D"]) == [
        "aufstellung",
        "X",
        "--new",
        "--date",
        "D",
    ]


def test_anwesenheit_legacy_argv():
    old = ["--new", "--team", "X", "--date", "D", "--file", "f.json"]
    assert anwesenheit.legacy_argv(old) == [
        "anwesenheit",
        "--new",
        "--team",
        "X",
        "--date",
        "D",
        "--file",
        "f.json",
    ]


@pytest.mark.parametrize(
    "legacy_argv, argv, message",
    [
        (aufstellung.legacy_argv, [], "only --new is supported"),
        (aufstellung.legacy_argv, ["--new", "--team", "X"], "--new requires"),
        (anwesenheit.legacy_argv, [], "only --new is supported"),
        (anwesenheit.legacy_argv, ["--new", "--date", "D"], "--new requires"),
    ],
)
def test_legacy_usage_errors(legacy_argv, argv, message, capsys):
    with pytest.raises(SystemExit) as exc:
        legacy_argv(argv)
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    "script, argv, new_argv",
    [
        ("visualize_spiele.py", ["--team", "X"], ["team", "X", "--next", "4"]),
        (
            "fetch_bfv_spielplan.py",
            ["--refresh", "--teams", "t.json"],
            ["fetch", "--refresh", "--teams", "t.json"],
        ),
        (
            "aufstellung.py",
            ["--new", "--team", "X", "--date", "D"],
            ["aufstellung", "X", "--new", "--date", "D"],
        ),
        (
            "anwesenheit.py",
            ["--new", "--team", "X", "--date", "D"],
            ["anwesenheit", "--new", "--team", "X", "--date", "D"],
        ),
    ],
)
def test_old_script_forwards_with_one_notice(
    monkeypatch, capsys, script, argv, new_argv
):
    """Run the real ``__main__`` block: one notice, same argv, same exit code."""
    calls = []
    monkeypatch.setattr(spielplan, "main", lambda a: calls.append(a) or 3)
    monkeypatch.setattr("sys.argv", [script, *argv])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / script), run_name="__main__")
    assert exc.value.code == 3
    assert calls == [new_argv]
    err_lines = capsys.readouterr().err.strip().splitlines()
    assert len(err_lines) == 1
    assert script in err_lines[0]
    assert "veraltet" in err_lines[0]
    assert "spielplan.py " + new_argv[0] in err_lines[0]


def test_old_script_keeps_exit_code(script_dir, monkeypatch):
    """A failing command fails the same way through the old entry point."""
    monkeypatch.setattr("sys.argv", ["visualize_spiele.py", "--captains-check"])
    with pytest.raises(SystemExit, match="Keine .*_spiele_web.csv"):
        runpy.run_path(str(ROOT / "visualize_spiele.py"), run_name="__main__")
