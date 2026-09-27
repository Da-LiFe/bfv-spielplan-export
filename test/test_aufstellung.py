import csv
import json
import os
import time
import urllib.error
from datetime import date, timedelta

import pytest
from pdfminer.high_level import extract_text

import aufstellung
import visualize_spiele as vis

TEAM = "TSV Gilching/Argelsried U8"
PNG = aufstellung.PNG_MAGIC + b"rest"
CSV_HEADER = [
    "Wettbewerb",
    "Datum",
    "Uhrzeit",
    "Heim",
    "Gast",
    "Spielort",
    "Link",
    "Quelle",
]


def raw_game(day="2026-05-02", team=TEAM, **overrides):
    entry = {
        "team": team,
        "date": day,
        "system": "3-2-1",
        "aufgebot": {
            "Lukas": 1,
            "Mia": 2,
            "Leon": 3,
            "Emma": 4,
            "Felix": 5,
            "Hannah": 6,
            "Paul": 7,
            "Tim": 8,
        },
        "startelf": [
            {"name": "Lukas", "pos": "Tor"},
            {"name": "Leon", "pos": "IV"},
            {"name": "Felix", "pos": "RV"},
            {"name": "Paul", "pos": "LV"},
            {"name": "Mia", "pos": "6er"},
            {"name": "Hannah", "pos": "8er"},
            {"name": "Emma", "pos": "9er"},
        ],
        "bank": ["Tim"],
        "notizen_team": ["Bälle nicht vergessen!"],
        "notizen_spieler": {"Lukas": ["Nagelschuhe mitbringen"]},
    }
    entry.update(overrides)
    return entry


def make_lineup(**overrides):
    lineup, warnings = aufstellung.normalize_entry(raw_game(**overrides), 0)
    assert lineup is not None
    return lineup


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)


def csv_row(day, heim, gast, time_="10:00"):
    return {
        "Wettbewerb": "U8 Kreis",
        "Datum": day.strftime("%d.%m.%Y"),
        "Uhrzeit": time_,
        "Heim": heim,
        "Gast": gast,
        "Spielort": "Sportpark",
        "Link": "",
        "Quelle": "https://bfv/u8",
    }


# --- loading ---------------------------------------------------------------


def test_normalize_entry_valid():
    lineup = make_lineup()
    assert lineup.team == TEAM
    assert lineup.date == date(2026, 5, 2)
    assert lineup.aufgebot["Paul"] == 7
    assert lineup.startelf[0] == aufstellung.Starter("Lukas", "Tor")
    assert lineup.bank == ["Tim"]
    assert lineup.notizen_spieler == {"Lukas": ["Nagelschuhe mitbringen"]}


def test_normalize_entry_german_date_and_string_note():
    lineup, _ = aufstellung.normalize_entry(
        raw_game(day="02.05.2026", notizen_spieler={"Mia": "Trikot", "Leon": []}), 0
    )
    assert lineup.date == date(2026, 5, 2)
    assert lineup.notizen_spieler == {"Mia": ["Trikot"]}


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("nö", "kein Objekt"),
        ({"date": "2026-05-02"}, "ohne Team"),
        ({"team": TEAM, "date": "kaputt"}, "ungültiges Datum"),
        ({"team": TEAM, "date": 42}, "ungültiges Datum"),
    ],
)
def test_normalize_entry_rejects(raw, fragment):
    lineup, warnings = aufstellung.normalize_entry(raw, 3)
    assert lineup is None
    assert fragment in warnings[0]
    assert "Eintrag 3" in warnings[0]


def test_normalize_entry_bad_fields_warn():
    lineup, warnings = aufstellung.normalize_entry(
        raw_game(
            aufgebot={"Lukas": "eins", "Mia": 2},
            startelf=[{"name": "Mia", "pos": "IV"}, "Leon", {"pos": "RV"}],
        ),
        0,
    )
    assert lineup.aufgebot == {"Mia": 2}
    assert [s.name for s in lineup.startelf] == ["Mia"]
    assert len(warnings) == 3


def test_normalize_data():
    lineups, warnings = aufstellung.normalize_data(
        {"spiele": [raw_game(), "x", raw_game(day="2026-05-09")]}
    )
    assert [lu.date.day for lu in lineups] == [2, 9]
    assert len(warnings) == 1
    assert aufstellung.normalize_data({"spiele": "x"})[0] == []
    assert "keine Liste" in aufstellung.normalize_data([])[1][0]


def test_load_lineups(tmp_path):
    path = tmp_path / "aufstellungen.json"
    lineups, warnings = aufstellung.load_lineups(path)
    assert lineups == [] and "nicht gefunden" in warnings[0]
    path.write_text("{kaputt", encoding="utf-8")
    lineups, warnings = aufstellung.load_lineups(path)
    assert lineups == [] and "ungültiges JSON" in warnings[0]
    path.write_text(json.dumps({"spiele": [raw_game()]}), encoding="utf-8")
    lineups, warnings = aufstellung.load_lineups(path)
    assert len(lineups) == 1 and warnings == []


def test_example_file_is_valid():
    lineups, warnings = aufstellung.load_lineups(
        aufstellung.SCRIPT_DIR / "aufstellungen.example.json"
    )
    assert warnings == []
    assert len(lineups) == 2
    # The first example is fully consistent; the second deliberately has a
    # bench player without a shirt number.
    assert aufstellung.validate(lineups[0]) == []
    assert any("Jonas Ersatz" in w for w in aufstellung.validate(lineups[1]))


def test_lineups_for_team_and_select():
    lineups = [
        make_lineup(day="2026-05-09"),
        make_lineup(day="2026-05-02", team=TEAM.lower()),
        make_lineup(team="Andere"),
    ]
    mine = aufstellung.lineups_for_team(lineups, {TEAM})
    assert [lu.date.day for lu in mine] == [2, 9]
    assert aufstellung.select_lineup(mine, date(2026, 5, 9)).date.day == 9
    assert aufstellung.select_lineup(mine, date(2026, 5, 3)) is None
    assert aufstellung.select_lineup(mine, None, today=date(2026, 5, 3)).date.day == 9
    assert aufstellung.select_lineup(mine, None, today=date(2026, 6, 1)) is None


# --- helpers ---------------------------------------------------------------


def test_system_size():
    assert aufstellung.system_size("3-2-1") == 7
    assert aufstellung.system_size("3 - 2 - 3") == 9
    assert aufstellung.system_size("") is None
    assert aufstellung.system_size("Raute") is None


def test_meeting_time():
    assert aufstellung.meeting_time("10:00") == "09:00"
    assert aufstellung.meeting_time("00:30") == "23:30"
    assert aufstellung.meeting_time("") == ""
    assert aufstellung.meeting_time("folgt") == ""


def test_parse_iso_date_and_german_date():
    assert aufstellung.parse_iso_date("2026-05-02") == date(2026, 5, 2)
    assert aufstellung.parse_iso_date(None) is None
    assert aufstellung.german_date(date(2026, 5, 2)) == "Samstag, 2. Mai 2026"


# --- validation ------------------------------------------------------------


def test_validate_clean():
    assert aufstellung.validate(make_lineup()) == []


def test_validate_reports_everything():
    lineup = make_lineup(
        system="3-3-1",
        aufgebot={"Lukas": 1, "Mia": 1, "Leon": 3, "Ohne": 9},
        startelf=[
            {"name": "Lukas", "pos": "Tor"},
            {"name": "Mia", "pos": "AV"},
            {"name": "Leon", "pos": "Libero"},
            {"name": "Leon", "pos": "IV"},
            {"name": "Neu", "pos": "ST"},
        ],
        bank=["Mia", "Gast"],
        notizen_spieler={"Fremd": ["?"]},
    )
    warnings = "\n".join(aufstellung.validate(lineup))
    assert "Neu (Startelf) hat keine Rückennummer" in warnings
    assert "Gast (Bank) hat keine Rückennummer" in warnings
    assert "Leon steht mehrfach" in warnings
    assert "Mia steht in Startelf und auf der Bank" in warnings
    assert "Ohne ist nominiert" in warnings
    assert "Rückennummer 1 doppelt: Lukas, Mia" in warnings
    assert "braucht 8 Spieler, Startelf hat 5" in warnings
    assert "'AV' bei Mia ist mehrdeutig – LV oder RV" in warnings
    assert "Unbekannte Position 'Libero'" in warnings
    assert "Notiz für Fremd" in warnings


def test_validate_unreadable_system():
    warnings = aufstellung.validate(make_lineup(system="Raute"))
    assert warnings == ["System 'Raute' nicht lesbar (erwartet z.B. 3-2-1)."]


# --- placement -------------------------------------------------------------


def test_place_players_uses_position_spots():
    placed = {p.name: p for p in aufstellung.place_players(make_lineup())}
    assert (placed["Lukas"].x, placed["Lukas"].y) == aufstellung.POSITIONS["TOR"]
    assert placed["Paul"].x < placed["Leon"].x < placed["Felix"].x
    assert placed["Mia"].y < placed["Hannah"].y < placed["Emma"].y
    assert placed["Emma"].number == 4


def test_place_players_spreads_shared_codes_and_unknown():
    lineup = make_lineup(
        startelf=[
            {"name": "A", "pos": "IV"},
            {"name": "B", "pos": "iv"},
            {"name": "C", "pos": "IV"},
            {"name": "D", "pos": "?"},
            {"name": "E", "pos": "xx"},
        ]
    )
    placed = {p.name: p for p in aufstellung.place_players(lineup)}
    assert placed["A"].x < placed["B"].x < placed["C"].x
    assert placed["B"].x == pytest.approx(0.5)
    assert placed["A"].y == placed["C"].y == aufstellung.POSITIONS["IV"][1]
    assert placed["D"].y == placed["E"].y == aufstellung.UNKNOWN_ROW_Y
    assert placed["D"].x < placed["E"].x
    assert placed["A"].number is None


def test_place_players_clamps_to_pitch():
    lineup = make_lineup(startelf=[{"name": n, "pos": "LV"} for n in "ABC"])
    xs = [p.x for p in aufstellung.place_players(lineup)]
    assert min(xs) == pytest.approx(0.08)


# --- logo ------------------------------------------------------------------


def test_get_logo_downloads_and_caches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(aufstellung, "_download", lambda url: calls.append(url) or PNG)
    cache = tmp_path / "c" / "logo.png"
    assert aufstellung.get_logo("u", cache) == cache
    assert cache.read_bytes() == PNG
    assert aufstellung.get_logo("u", cache) == cache
    assert calls == ["u"]


def test_get_logo_failure_falls_back(tmp_path, monkeypatch, capsys):
    def boom(url):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(aufstellung, "_download", boom)
    cache = tmp_path / "logo.png"
    assert aufstellung.get_logo("u", cache) is None
    assert "Vereinslogo nicht geladen" in capsys.readouterr().err
    cache.write_bytes(PNG)
    old = time.time() - 2 * aufstellung.LOGO_CACHE_TTL
    os.utime(cache, (old, old))
    assert aufstellung.get_logo("u", cache) == cache


def test_get_logo_rejects_non_png(tmp_path, monkeypatch):
    monkeypatch.setattr(aufstellung, "_download", lambda url: b"<html>")
    cache = tmp_path / "logo.png"
    assert aufstellung.get_logo("u", cache) is None
    assert not cache.exists()


def test_download(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return PNG

    seen = {}

    def fake_urlopen(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return Resp()

    monkeypatch.setattr(aufstellung.urllib.request, "urlopen", fake_urlopen)
    assert aufstellung._download("https://x") == PNG
    assert seen["ua"] == aufstellung.USER_AGENT


# --- PDF -------------------------------------------------------------------


def real_logo(tmp_path):
    from PIL import Image as PILImage

    path = tmp_path / "logo.png"
    PILImage.new("RGB", (20, 20), "red").save(path)
    return path


def test_build_lineup_pdf_full(tmp_path):
    out = tmp_path / "a.pdf"
    game = aufstellung.GameInfo(
        opponent="FC Gegner", kickoff="10:00", competition="U8 Kreis", is_home=True
    )
    aufstellung.build_lineup_pdf(
        make_lineup(), out, game, "Mia", logo=real_logo(tmp_path)
    )
    text = extract_text(str(out))
    assert "Spieltag — gegen FC Gegner" in text
    assert "Anpfiff 10:00 Uhr" in text
    assert "Heimspiel" in text
    assert "09:00 Uhr" in text  # Treffpunkt
    assert "Kapitän der Woche" in text and "Mia" in text
    assert "3-2-1" in text
    assert "Bank (1)" in text and "#8 Tim" in text
    assert "Bälle nicht vergessen!" in text
    assert "#1 Lukas:" in text and "Nagelschuhe mitbringen" in text
    assert "Hannah" in text and "8er" in text
    assert "Kader" not in text


def test_build_lineup_pdf_without_game(tmp_path, capsys):
    out = tmp_path / "b.pdf"
    broken_logo = tmp_path / "broken.png"
    broken_logo.write_bytes(b"nope")
    lineup = make_lineup(bank=[], notizen_team=[], notizen_spieler={}, system="")
    aufstellung.build_lineup_pdf(lineup, out, None, "", logo=broken_logo)
    text = extract_text(str(out))
    assert "Gegner unbekannt" in text
    assert "Auswärtsspiel" not in text
    assert "Bank (0)" in text
    assert "Vereinslogo nicht lesbar" in capsys.readouterr().err


def test_build_lineup_pdf_away_single_page(tmp_path):
    out = tmp_path / "c.pdf"
    game = aufstellung.GameInfo(opponent="FC Heim")
    aufstellung.build_lineup_pdf(make_lineup(), out, game)
    text = extract_text(str(out))
    assert "Auswärtsspiel" in text
    assert "Anpfiff" not in text
    assert text.count("\f") == 1  # one page


# --- CLI -------------------------------------------------------------------


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(aufstellung, "_download", lambda url: PNG)
    monkeypatch.setattr(aufstellung, "get_logo", lambda **kw: None)
    return tmp_path


def write_lineups(path, *games):
    (path / "aufstellungen.json").write_text(
        json.dumps({"spiele": list(games)}, ensure_ascii=False), encoding="utf-8"
    )


def test_main_aufstellung_with_game_and_captain(cli_env, capsys):
    day = date.today() + timedelta(days=3)
    write_csv(
        cli_env / "u8_spiele_web.csv",
        [
            csv_row(day, "FC Gegner", TEAM, "11:30"),
            csv_row(day + timedelta(days=7), TEAM, "FC Später"),
        ],
    )
    week = f"{day.isocalendar()[0]}-{day.isocalendar()[1]:02d}"
    (cli_env / "kapitane.json").write_text(
        json.dumps({"assignments": {TEAM: {week: "Hannah"}}}), encoding="utf-8"
    )
    write_lineups(
        cli_env,
        raw_game(day=(day - timedelta(days=7)).isoformat()),
        raw_game(day=day.isoformat(), bank=["Tim", "Jonas"]),
    )
    vis.main(["--aufstellung", "--team", TEAM.lower()])
    captured = capsys.readouterr()
    assert "gegen FC Gegner" in captured.out
    assert "Jonas (Bank) hat keine Rückennummer" in captured.err
    out = cli_env / f"tsv-gilching-argelsried-u8_aufstellung_{day.isoformat()}.pdf"
    text = extract_text(str(out))
    assert "10:30 Uhr" in text
    assert "Hannah" in text
    assert "Auswärtsspiel" in text


def test_main_aufstellung_date_out_and_no_game(cli_env, capsys):
    write_lineups(cli_env, raw_game(day="2026-05-02"))
    out = cli_env / "x.pdf"
    vis.main(
        ["--aufstellung", "--team", TEAM, "--date", "2026-05-02", "--out", str(out)]
    )
    captured = capsys.readouterr()
    assert "Kein Spiel von" in captured.err
    assert out.exists()
    text = extract_text(str(out))
    assert "Gegner unbekannt" in text


def test_main_aufstellung_original_name(cli_env, capsys):
    day = date(2026, 5, 2)
    alias = "U8 Alias"
    write_csv(cli_env / "u8_spiele_web.csv", [csv_row(day, TEAM, "FC Gast")])
    (cli_env / "teams.json").write_text(
        json.dumps([{"url": "https://bfv/u8", "alias": alias}]), encoding="utf-8"
    )
    write_lineups(cli_env, raw_game(day="2026-05-02", team=alias))
    vis.main(["--aufstellung", "--team", TEAM, "--date", "2026-05-02"])
    assert "gegen FC Gast" in capsys.readouterr().out
    assert (cli_env / "u8-alias_aufstellung_2026-05-02.pdf").exists()


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--aufstellung"], "benötigt --team"),
        (["--aufstellung", "--team", TEAM, "--date", "morgen"], "Ungültiges Datum"),
        (["--aufstellung", "--team", "Unbekannt"], "Teams mit Aufstellung: " + TEAM),
        (
            ["--aufstellung", "--team", TEAM, "--date", "2026-05-03"],
            "Keine Aufstellung am 2026-05-03",
        ),
        (["--aufstellung", "--team", TEAM], "Keine kommende Aufstellung"),
    ],
)
def test_main_aufstellung_errors(cli_env, argv, message):
    write_lineups(cli_env, raw_game(day="2020-05-02"))
    with pytest.raises(SystemExit) as exc:
        vis.main(argv)
    assert message in str(exc.value)


def test_main_aufstellung_missing_file(cli_env, capsys):
    with pytest.raises(SystemExit) as exc:
        vis.main(["--aufstellung", "--team", TEAM])
    assert "Teams mit Aufstellung: keine" in str(exc.value)
    assert "aufstellungen.json nicht gefunden" in capsys.readouterr().err


def test_find_team_game_prefers_earliest():
    from datetime import datetime

    d = datetime(2026, 5, 2)
    games = [
        {"heim": TEAM, "gast": "B", "date": d, "time": "14:00"},
        {"heim": "A", "gast": TEAM, "date": d, "time": ""},
        {"heim": "A", "gast": TEAM, "date": d, "time": "09:00"},
        {"heim": "X", "gast": "Y", "date": d, "time": "08:00"},
    ]
    assert vis.find_team_game(games, TEAM, d)["time"] == "09:00"
    assert vis.find_team_game(games, "Z", d) is None
