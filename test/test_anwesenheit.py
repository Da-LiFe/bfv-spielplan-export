import json
from datetime import date

import pytest
from pdfminer.high_level import extract_text
from reportlab.lib.units import mm

import anwesenheit
import kapitane

PlayerStats = anwesenheit.PlayerStats

TG = "TSV Gilching/Argelsried u13-2"
TG2 = "TSV Gilching/Argelsried u16w"


def raw_session(day, team=TG, values=None):
    return {
        "date": f"2026-09-{day:02d}",
        "team": team,
        "values": values or {"Lena": "P", "Max": "S", "Noah": "N"},
    }


def test_empty_data():
    assert anwesenheit.empty_data() == {"sessions": [], "warnings": []}


def test_parse_session_date():
    assert anwesenheit.parse_session_date("2026-09-21") == date(2026, 9, 21)
    assert anwesenheit.parse_session_date("21.09.2026") == date(2026, 9, 21)
    assert anwesenheit.parse_session_date("kaputt") is None
    assert anwesenheit.parse_session_date(42) is None
    assert anwesenheit.parse_session_date(date(2026, 9, 21)) == date(2026, 9, 21)


def test_normalize_data_valid():
    data = anwesenheit.normalize_data({"sessions": [raw_session(21)]})
    assert data["warnings"] == []
    s = data["sessions"][0]
    assert s["date"] == date(2026, 9, 21)
    assert s["team"] == TG
    assert s["values"] == {"Lena": "P", "Max": "S", "Noah": "N"}


def test_normalize_data_uppercases_and_coerces_unknown_status():
    data = anwesenheit.normalize_data(
        {"sessions": [raw_session(21, values={"Lena": "p", "Max": "x"})]}
    )
    s = data["sessions"][0]
    assert s["values"] == {"Lena": "P", "Max": "N"}
    assert any("Max" in w and "als 'N' gewertet" in w for w in data["warnings"])


def test_normalize_data_drops_malformed_sessions():
    data = anwesenheit.normalize_data(
        {
            "sessions": [
                raw_session(21),
                {"date": "kaputt", "team": TG, "values": {}},
                {"date": "2026-09-22"},  # no team
                {"date": "2026-09-23", "team": TG},  # no values
                "nö",
            ]
        }
    )
    assert len(data["sessions"]) == 1
    assert len(data["warnings"]) >= 4


def test_normalize_data_non_list_sessions():
    data = anwesenheit.normalize_data({"sessions": "nix"})
    assert data["sessions"] == []
    assert data["warnings"] == ["anwesenheit.json: 'sessions' ist keine Liste."]
    data = anwesenheit.normalize_data({"sessions": ["x", "y"]})
    assert data["sessions"] == []
    assert len(data["warnings"]) == 2


def test_load_data_missing_file(tmp_path):
    assert anwesenheit.load_data(tmp_path / "nope.json") == {
        "sessions": [],
        "warnings": [],
    }


def test_load_data_invalid_json(tmp_path, capsys):
    p = tmp_path / "anwesenheit.json"
    p.write_text("{ kaputt", encoding="utf-8")
    data = anwesenheit.load_data(p)
    assert data["sessions"] == []
    assert "ungültiges JSON" in capsys.readouterr().err


def test_load_data_prints_warnings(tmp_path, capsys):
    p = tmp_path / "anwesenheit.json"
    p.write_text(json.dumps({"sessions": [raw_session(21, values={"Lena": "X"})]}))
    data = anwesenheit.load_data(p)
    assert data["sessions"][0]["values"] == {"Lena": "N"}
    assert "Warnung" in capsys.readouterr().err


def test_save_data_roundtrip(tmp_path):
    p = tmp_path / "anwesenheit.json"
    sessions = [
        {"date": date(2026, 9, 21), "team": TG, "values": {"Lena": "P"}},
        {"date": "2026-09-22", "team": TG, "values": {"Max": "S"}},
    ]
    anwesenheit.save_data(sessions, p)
    loaded = anwesenheit.load_data(p)
    assert [s["date"] for s in loaded["sessions"]] == [
        date(2026, 9, 21),
        date(2026, 9, 22),
    ]
    assert loaded["sessions"][0]["values"] == {"Lena": "P"}


def make_sessions():
    return [
        {
            "date": date(2026, 9, 7),
            "team": TG,
            "values": {"Lena": "P", "Max": "S", "Noah": "N"},
        },
        {"date": date(2026, 9, 14), "team": TG, "values": {"Lena": "P", "Max": "N"}},
        {"date": date(2026, 9, 21), "team": TG2, "values": {"Emma": "P", "Paul": "A"}},
    ]


def test_stats_per_team():
    stats = anwesenheit.stats_per_team(make_sessions())
    assert list(stats) == [TG, TG2]
    lena = stats[TG][0]
    assert lena.name == "Lena"
    assert lena.sessions == 2 and lena.p == 2 and lena.s == 0
    assert lena.presence_rate == 1.0
    max_ = stats[TG][1]
    assert max_.sessions == 2 and max_.p == 0 and max_.s == 1 and max_.n == 1
    assert max_.presence_rate == 0.0
    assert max_.fit_rate == 0.5
    emma = stats[TG2][0]
    assert emma.sessions == 1 and emma.p == 1


def test_stats_sorted_by_player_name():
    sessions = [
        {"date": date(2026, 9, 7), "team": TG, "values": {"Ben": "P", "Anna": "P"}}
    ]
    stats = anwesenheit.stats_per_team(sessions)[TG]
    assert [s.name for s in stats] == ["Anna", "Ben"]


def test_new_session_prefills_n_from_roster():
    entry = anwesenheit.new_session(TG, date(2026, 9, 21), ["Lena", "Max", "Noah"])
    assert entry["date"] == date(2026, 9, 21)
    assert entry["team"] == TG
    assert entry["values"] == {"Lena": "N", "Max": "N", "Noah": "N"}


def test_new_session_empty_roster():
    entry = anwesenheit.new_session(TG, date(2026, 9, 21), [])
    assert entry["values"] == {}


def test_session_exists():
    sessions = make_sessions()
    assert anwesenheit.session_exists(sessions, TG, date(2026, 9, 7))
    assert not anwesenheit.session_exists(sessions, TG, date(2026, 9, 21))
    assert not anwesenheit.session_exists(sessions, TG2, date(2026, 9, 7))


def test_cli_new_writes_entry(tmp_path, monkeypatch, capsys):
    roster = tmp_path / kapitane.ROSTER_NAME
    roster.write_text(json.dumps({"teams": {TG: ["Lena", "Max", "Noah"]}}))
    monkeypatch.setattr(kapitane, "DEFAULT_ROSTER_PATH", roster)
    out = tmp_path / "anwesenheit.json"
    rc = anwesenheit.cli_main(
        ["--new", "--team", TG, "--date", "2026-09-21", "--file", str(out)]
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sessions"] == [
        {
            "date": "2026-09-21",
            "team": TG,
            "values": {"Lena": "N", "Max": "N", "Noah": "N"},
        }
    ]
    out_text = capsys.readouterr().out
    assert "Anwesenheit:" in out_text and "3 Spieler" in out_text


def test_cli_new_accepts_german_date(tmp_path, monkeypatch):
    out = tmp_path / "anwesenheit.json"
    rc = anwesenheit.cli_main(
        ["--new", "--team", TG, "--date", "21.09.2026", "--file", str(out)]
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sessions"][0]["date"] == "2026-09-21"


def test_cli_new_unknown_team_warns_stderr(tmp_path, monkeypatch, capsys):
    roster = tmp_path / kapitane.ROSTER_NAME
    roster.write_text(json.dumps({"teams": {TG2: ["Emma"]}}))
    monkeypatch.setattr(kapitane, "DEFAULT_ROSTER_PATH", roster)
    out = tmp_path / "anwesenheit.json"
    rc = anwesenheit.cli_main(
        ["--new", "--team", TG, "--date", "2026-09-21", "--file", str(out)]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "Kein Kader" in err
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sessions"][0]["values"] == {}


def test_cli_new_duplicate_skips(tmp_path, monkeypatch, capsys):
    out = tmp_path / "anwesenheit.json"
    anwesenheit.save_data(
        [{"date": date(2026, 9, 21), "team": TG, "values": {"Lena": "P"}}], out
    )
    rc = anwesenheit.cli_main(
        ["--new", "--team", TG, "--date", "2026-09-21", "--file", str(out)]
    )
    assert rc == 1
    assert "existiert bereits" in capsys.readouterr().err
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sessions"] == [
        {"date": "2026-09-21", "team": TG, "values": {"Lena": "P"}}
    ]


def test_cli_new_missing_args():
    with pytest.raises(SystemExit) as exc:
        anwesenheit.cli_main(["--new", "--team", TG])
    assert exc.value.code == 2


def test_cli_new_invalid_date():
    with pytest.raises(SystemExit) as exc:
        anwesenheit.cli_main(["--new", "--team", TG, "--date", "kaputt"])
    assert exc.value.code == 2


def test_build_anwesenheit_pdf(tmp_path):
    out = tmp_path / "anwesenheit.pdf"
    teams = anwesenheit.build_anwesenheit_pdf(make_sessions(), out)
    assert teams == [TG, TG2]
    text = extract_text(str(out))
    assert "Anwesenheit" in text
    assert TG in text
    assert TG2 in text
    assert "Lena" in text and "Max" in text
    assert "Spieler" in text
    assert "Quote P" in text
    assert "Summe" in text
    assert "50 %" in text


def test_build_anwesenheit_pdf_empty(tmp_path):
    out = tmp_path / "leer.pdf"
    teams = anwesenheit.build_anwesenheit_pdf([], out)
    assert teams == []
    assert "Keine Anwesenheitsdaten" in extract_text(str(out))


def test_columns_and_values_variants():
    headers, widths = anwesenheit._columns(False)
    assert headers == [
        "Spieler",
        "Termine",
        "P",
        "S",
        "A",
        "N",
        "Quote P",
        "Quote P+S",
    ]
    headers, widths = anwesenheit._columns(True)
    assert headers == ["Spieler", "Termine", "P", "A", "N", "Quote P"]
    assert sum(widths) == pytest.approx(182 * mm)


def test_totals_aggregates():
    totals = anwesenheit._totals(
        [
            PlayerStats(name="Lena", sessions=2, p=2),
            PlayerStats(name="Max", sessions=2, s=1, n=1),
        ]
    )
    assert totals.p == 2 and totals.s == 1 and totals.n == 1
    assert totals.sessions == 4


def test_build_anwesenheit_pdf_combined(tmp_path):
    out = tmp_path / "anwesenheit_kombiniert.pdf"
    teams = anwesenheit.build_anwesenheit_pdf(make_sessions(), out, combined=True)
    assert teams == [TG, TG2]
    text = extract_text(str(out))
    assert "S+A" not in text
    assert "A" in text  # merged column now reads just A
    assert "Quote P" in text
    assert "Quote P+S" not in text
    assert "krank" not in text  # sick is completely hidden in combined mode
    assert "S = krank" not in text
    assert "A = abwesend" in text  # legend: only P/A/N, no sick
    assert "Summe" in text
    assert "100 %" in text  # Lena: 2/2 present
