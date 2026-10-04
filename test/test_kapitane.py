import json
from datetime import date, timedelta

import kapitane
import visualize_spiele as vis

TG = "TSV Gilching/Argelsried u13-2"


def make_game(days, heim, gast):
    d = date.today() + timedelta(days=days)
    return {
        "date": d,
        "datum": d.strftime(vis.CSV_DATE_FORMAT),
        "wd": vis.WD[d.weekday()],
        "time": "10:00",
        "heim": heim,
        "gast": gast,
        "wettbewerb": "Kreis",
        "spielort": "Ort",
        "link": "",
    }


def make_sources():
    return [{"file": "a.csv", "team": TG, "url": "u", "original": TG}]


def test_empty_config():
    cfg = kapitane.empty_config()
    assert cfg == {"teams": {}, "assignments": {}}


def test_duty_week():
    assert kapitane.duty_week(date(2026, 9, 20)) == "2026-38"
    for d in (date(2026, 12, 28), date(2027, 1, 4), date(2026, 9, 20)):
        year, week, _ = d.isocalendar()
        assert kapitane.duty_week(d) == f"{year}-{week:02d}"


def test_week_range():
    assert kapitane.week_range("2026-37") == "Mo 07.09. – So 13.09."
    assert kapitane.week_range("") == ""
    assert kapitane.week_range("2026-99") == ""
    assert kapitane.week_range("abc") == ""


def test_load_config(tmp_path):
    p = tmp_path / "kapitane.json"
    p.write_text(
        json.dumps(
            {
                "teams": {TG: ["ignored", "data"]},
                "assignments": {TG: {"2026-37": "Lena", "2026-38": ""}},
            }
        ),
        encoding="utf-8",
    )
    cfg = kapitane.load_config(p)
    assert cfg == {"assignments": {TG: {"2026-37": "Lena"}}}

    p.write_text("{kaputt", encoding="utf-8")
    assert kapitane.load_config(p) == {"assignments": {}}
    assert kapitane.load_config(tmp_path / "missing.json") == {"assignments": {}}


def test_load_config_unexpected_shape(tmp_path):
    p = tmp_path / "kapitane.json"
    p.write_text(json.dumps({"teams": {"x": "not-a-list"}}), encoding="utf-8")
    assert kapitane.load_config(p) == {"assignments": {}}


def test_save_config_roundtrip(tmp_path):
    p = tmp_path / "kapitane.json"
    cfg = {"teams": {TG: ["Lena", "Müller"]}, "assignments": {TG: {"2026-37": "Lena"}}}
    kapitane.save_config(cfg, p)
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "assignments": {TG: {"2026-37": "Lena"}}
    }
    assert "Müller" not in p.read_text(encoding="utf-8")


def test_roster_roundtrip(tmp_path):
    p = tmp_path / "roster.json"
    roster = {TG: ["Lena", "Müller"], "B": []}
    kapitane.save_roster(roster, p)
    expected = {
        "teams": {
            TG: {"kids": [{"name": "Lena"}, {"name": "Müller"}]},
            "B": {"kids": []},
        }
    }
    assert json.loads(p.read_text(encoding="utf-8")) == expected
    assert kapitane.load_roster(p) == roster


def test_load_roster_missing_and_bad(tmp_path):
    assert kapitane.load_roster(tmp_path / "missing.json") == {}
    p = tmp_path / "roster.json"
    p.write_text(json.dumps({"teams": {"x": "not-a-list"}}), encoding="utf-8")
    assert kapitane.load_roster(p) == {}
    p.write_text("{kaputt", encoding="utf-8")
    assert kapitane.load_roster(p) == {}


def test_load_all_merges(tmp_path):
    assign_path = tmp_path / "kapitane.json"
    roster_path = tmp_path / "roster.json"
    kapitane.save_roster({TG: ["A", "B"]}, roster_path)
    kapitane.save_config({"assignments": {TG: {"2026-37": "A"}}}, assign_path)
    cfg = kapitane.load_all(assign_path, roster_path)
    assert cfg == {"teams": {TG: ["A", "B"]}, "assignments": {TG: {"2026-37": "A"}}}


def test_round_robin_distributes_fairly():
    roster = ["A", "B", "C", "D"]
    weeks = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    result = kapitane.assign_round_robin(weeks, roster, {})
    assert set(result) == set(weeks)
    counts = {}
    for kid in result.values():
        counts[kid] = counts.get(kid, 0) + 1
    assert sorted(counts.values()) == [1, 1, 1, 2]


def test_round_robin_respects_existing():
    roster = ["A", "B", "C"]
    weeks = ["2026-01", "2026-02", "2026-03"]
    existing = {"2026-01": "A", "2026-02": "A"}
    result = kapitane.assign_round_robin(weeks, roster, existing)
    assert result["2026-03"] == "B"


def test_round_robin_keeps_unknown_existing_names():
    roster = ["A", "B"]
    weeks = ["2026-01", "2026-02"]
    existing = {"2026-01": "Fremd"}
    result = kapitane.assign_round_robin(weeks, roster, existing)
    assert result["2026-01"] == "Fremd"
    assert result["2026-02"] == "A"


def test_round_robin_ignores_past_assignments():
    """Assignments for weeks outside the target set must not affect balance."""
    roster = ["A", "B"]
    upcoming = ["2026-37", "2026-38"]
    existing = {"2026-01": "A", "2026-02": "A", "2026-03": "A"}
    result = kapitane.assign_round_robin(upcoming, roster, existing)
    assert result["2026-37"] == "A"
    assert result["2026-38"] == "B"


def test_ensure_assignments_fills_and_is_idempotent():
    cfg = {"teams": {TG: ["A", "B"]}, "assignments": {}}
    weeks = {TG: ["2026-37", "2026-38", "2026-39"]}
    assert kapitane.ensure_assignments(cfg, weeks) == []
    assert set(cfg["assignments"][TG]) == set(weeks[TG])
    before = dict(cfg["assignments"][TG])
    assert kapitane.ensure_assignments(cfg, weeks) == []
    assert cfg["assignments"][TG] == before


def test_ensure_assignments_warns_without_roster():
    cfg = {"teams": {}, "assignments": {}}
    warnings = kapitane.ensure_assignments(cfg, {TG: ["2026-37"]})
    assert warnings and "Kader" in warnings[0]
    assert TG not in cfg["assignments"]


def test_teams_duty_weeks_filters_recent():
    sources = make_sources()
    games = [
        make_game(-3, TG, "FC Alt"),
        make_game(2, TG, "FC A"),
        make_game(2, "FC B", TG),
        make_game(4, "FC C", TG),
        make_game(2, "FC X", "FC Y"),
    ]
    weeks = kapitane.teams_duty_weeks(games, sources)
    expected = sorted(
        {
            kapitane.duty_week(g["date"])
            for g in games
            if (g["heim"] == TG or g["gast"] == TG) and g["date"] >= date.today()
        }
    )
    assert weeks[TG] == expected


def test_check_distribution_balanced():
    cfg = {
        "teams": {TG: ["A", "B"]},
        "assignments": {TG: {"2026-37": "A", "2026-38": "B"}},
    }
    weeks = {TG: ["2026-37", "2026-38"]}
    res = kapitane.check_distribution(cfg, weeks)
    assert res.balanced
    assert "gleichmäßig" in "".join(res.lines)
    for line in res.lines:
        assert "PROBLEM" not in line


def test_check_distribution_unbalanced():
    cfg = {
        "teams": {TG: ["A", "B"]},
        "assignments": {TG: {"2026-37": "A", "2026-38": "A", "2026-39": "A"}},
    }
    weeks = {TG: ["2026-37", "2026-38", "2026-39"]}
    res = kapitane.check_distribution(cfg, weeks)
    assert not res.balanced
    assert "ungleichmäßig" in "".join(res.lines)


def test_check_distribution_flags_missing_and_unknown():
    cfg = {
        "teams": {TG: ["A", "B"]},
        "assignments": {TG: {"2026-37": "Fremd", "2026-38": "A"}},
    }
    weeks = {TG: ["2026-37", "2026-38", "2026-39"]}
    res = kapitane.check_distribution(cfg, weeks)
    assert not res.balanced
    joined = "".join(res.lines)
    assert "PROBLEM" in joined
    assert "Fremd" in joined
    assert "2026-39" in joined


def test_check_distribution_no_roster():
    cfg = {"teams": {}, "assignments": {TG: {"2026-37": "A"}}}
    res = kapitane.check_distribution(cfg, {TG: ["2026-37"]})
    assert not res.balanced
    assert "kein Kader" in "".join(res.lines)


def test_check_distribution_no_data():
    res = kapitane.check_distribution(kapitane.empty_config(), {})
    assert res.balanced
    assert "Keine Kapitän-Daten" in "".join(res.lines)


def test_run_check_exits_unbalanced(capsys):
    res = kapitane.check_distribution(kapitane.empty_config(), {TG: ["2026-37"]})
    try:
        kapitane.run_check(res)
    except SystemExit as exc:
        assert exc.code == 1
    caught = capsys.readouterr().out
    assert "Kapitän-Verteilung" in caught


def test_load_roster_handles_new_format(tmp_path):
    p = tmp_path / "roster.json"
    p.write_text(
        json.dumps(
            {"teams": {TG: {"kids": [{"name": "Lena"}, {"name": "Max", "number": 2}]}}}
        ),
        encoding="utf-8",
    )
    assert kapitane.load_roster(p) == {TG: ["Lena", "Max"]}


def test_load_roster_with_numbers_basic(tmp_path):
    p = tmp_path / "roster.json"
    p.write_text(
        json.dumps(
            {
                "teams": {
                    TG: {
                        "kids": [
                            {"name": "Lena", "number": 1},
                            {"name": "Max", "number": 2},
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = kapitane.load_roster_with_numbers(p)
    assert result == {TG: [{"name": "Lena", "number": 1}, {"name": "Max", "number": 2}]}


def test_load_roster_with_numbers_missing_numbers(tmp_path):
    p = tmp_path / "roster.json"
    p.write_text(
        json.dumps({"teams": {TG: {"kids": [{"name": "Lena"}]}}}),
        encoding="utf-8",
    )
    result = kapitane.load_roster_with_numbers(p)
    assert result == {TG: [{"name": "Lena", "number": None}]}


def test_load_roster_with_numbers_old_format(tmp_path):
    p = tmp_path / "roster.json"
    p.write_text(
        json.dumps({"teams": {TG: ["Lena", "Max"]}}),
        encoding="utf-8",
    )
    result = kapitane.load_roster_with_numbers(p)
    assert result == {
        TG: [{"name": "Lena", "number": None}, {"name": "Max", "number": None}]
    }


def test_load_roster_with_numbers_missing_file(tmp_path):
    assert kapitane.load_roster_with_numbers(tmp_path / "missing.json") == {}
