import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

import visualize_spiele as vis

U15 = "TSV Gilching/Argelsried U15"
U17 = "TSV Gilching/Argelsried U17"

CSV_HEADER = ["Wettbewerb", "Datum", "Uhrzeit", "Heim", "Gast", "Spielort", "Link", "Quelle"]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)


def write_fixtures(tmp_path):
    write_csv(
        tmp_path / "tsv-a_spiele_web.csv",
        [
            {"Wettbewerb": "U15 Kreis", "Datum": "20.09.2026", "Uhrzeit": "09:00", "Heim": U15,
             "Gast": "FC Beispiel 1", "Spielort": "Sportpark Gilching", "Link": "https://x/1",
             "Quelle": "https://bfv/quelle-a"},
            {"Wettbewerb": "U15 Kreis", "Datum": "27.09.2026", "Uhrzeit": "09:30", "Heim": "FC Beispiel 1",
             "Gast": U15, "Spielort": "Auswärts", "Link": "https://x/2", "Quelle": "https://bfv/quelle-a"},
            {"Wettbewerb": "U15 Kreis", "Datum": "03.10.2026", "Uhrzeit": "14:00", "Heim": U15,
             "Gast": "FC Beispiel 2", "Spielort": "Sportpark Gilching", "Link": "https://x/3",
             "Quelle": "https://bfv/quelle-a"},
            {"Wettbewerb": "U15 Kreis", "Datum": "kaputt", "Uhrzeit": "10:00", "Heim": U15,
             "Gast": "FC Kaputt", "Spielort": "", "Link": "", "Quelle": "https://bfv/quelle-a"},
        ],
    )
    write_csv(
        tmp_path / "tsv-b_spiele_web.csv",
        [
            {"Wettbewerb": "U17 Kreis", "Datum": "10.10.2026", "Uhrzeit": "11:00", "Heim": U17,
             "Gast": "SV Anderer", "Spielort": "Beispielhalle", "Link": "https://x/4",
             "Quelle": "https://bfv/quelle-b"},
            {"Wettbewerb": "U17 Kreis", "Datum": "17.10.2026", "Uhrzeit": "13:00", "Heim": "SV Dritter",
             "Gast": U17, "Spielort": "Halle 2", "Link": "https://x/5", "Quelle": "https://bfv/quelle-b"},
        ],
    )


def make_game(datum, time, heim, gast, **kw):
    d = vis.parse_datum(datum)
    return {
        "date": d,
        "datum": d.strftime("%d.%m.%Y"),
        "wd": vis.WD[d.weekday()],
        "time": time,
        "heim": heim,
        "gast": gast,
        "wettbewerb": kw.get("wettbewerb", "Kreis"),
        "spielort": kw.get("spielort", "Sportanlage"),
        "link": kw.get("link", ""),
        "is_home": kw.get("is_home", False),
        "home_color": vis.team_color(heim),
        "away_color": vis.team_color(gast),
    }


# ------------------------------------------------------------ parse_datum()


def test_parse_datum_valid():
    assert vis.parse_datum("20.09.2026") == datetime(2026, 9, 20)


@pytest.mark.parametrize("value", ["", "abc", "2026-09-20"])
def test_parse_datum_invalid_returns_none(value):
    assert vis.parse_datum(value) is None


# ------------------------------------------------------------- team_color()


def test_team_color_empty_is_grey():
    assert vis.team_color("") == "#888888"


def test_team_color_deterministic():
    assert vis.team_color("TSV Gilching/Argelsried U15") == vis.team_color("TSV Gilching/Argelsried U15")


# ------------------------------------------------------------- short_place()


def test_short_place_pipe_to_comma():
    assert vis.short_place("A | B | C") == "A, B, C"


def test_short_place_short_stays():
    assert vis.short_place("Kurz") == "Kurz"


def test_short_place_truncates():
    out = vis.short_place("X" * 100)
    assert len(out) == 45
    assert out.endswith("…")


# --------------------------------------------------------------- maps_url()


def test_maps_url_empty():
    assert vis.maps_url("") == ""


def test_maps_url_quotes_and_joins():
    url = vis.maps_url("Sportpark | Gilching")
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=")
    assert "%2C" in url


# ------------------------------------------------------------------- esc()


def test_esc_quotes():
    assert vis.esc('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


# ------------------------------------------------------------- german_now()


def test_german_now_format():
    out = vis.german_now()
    assert re.match(r"^[A-Z][a-zäöü]+, \d{1,2}\. [A-Za-zäöü]+ \d{4}, \d{2}:\d{2} Uhr$", out)


# ----------------------------------------------------------- load_alias_map()


def test_load_alias_map(tmp_path):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(
        json.dumps(
            [
                {"url": "https://bfv/1", "alias": "Alias 1"},
                {"url": "https://bfv/2"},
                {"url": "https://bfv/3", "alias": ""},
            ]
        ),
        encoding="utf-8",
    )
    assert vis.load_alias_map(teams_file) == {"https://bfv/1": "Alias 1"}


def test_load_alias_map_missing(tmp_path):
    assert vis.load_alias_map(tmp_path / "nope.json") == {}


# ------------------------------------------------------------- load_games()


def test_load_games(monkeypatch, tmp_path, capsys):
    write_fixtures(tmp_path)
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    games, club_teams, sources = vis.load_games()
    assert len(games) == 5  # 4 rows in A (1 invalid) + 2 in B
    err = capsys.readouterr().err
    assert "1 Zeile(n) in tsv-a_spiele_web.csv wegen ungültigen Datums übersprungen" in err
    assert club_teams == [U15, U17]
    assert {s["file"] for s in sources} == {"tsv-a_spiele_web.csv", "tsv-b_spiele_web.csv"}
    by_file = {s["file"]: s for s in sources}
    assert by_file["tsv-a_spiele_web.csv"]["team"] == U15
    assert by_file["tsv-a_spiele_web.csv"]["url"] == "https://bfv/quelle-a"
    assert by_file["tsv-b_spiele_web.csv"]["team"] == U17

    home = [g for g in games if g["heim"] == U15]
    assert len(home) == 2
    assert all(g["is_home"] for g in home)
    away = next(g for g in games if g["gast"] == U15)
    assert away["is_home"] is False
    assert away["source"] == "tsv-a_spiele_web.csv"
    assert all(g["source"] for g in games)


def test_load_games_no_csvs(monkeypatch, tmp_path):
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    games, club_teams, sources = vis.load_games()
    assert games == []
    assert club_teams == []
    assert sources == []


def test_load_games_warns_on_missing_teams(monkeypatch, tmp_path, capsys):
    write_csv(
        tmp_path / "tsv-a_spiele_web.csv",
        [
            {"Wettbewerb": "U15 Kreis", "Datum": "20.09.2026", "Uhrzeit": "09:00", "Heim": U15,
             "Gast": "FC Beispiel 1", "Spielort": "Sportpark Gilching", "Link": "https://x/1",
             "Quelle": "https://bfv/quelle-a"},
            {"Wettbewerb": "U15 Kreis", "Datum": "27.09.2026", "Uhrzeit": "09:30", "Heim": U15,
             "Gast": "", "Spielort": "Auswärts", "Link": "https://x/2", "Quelle": "https://bfv/quelle-a"},
            {"Wettbewerb": "U15 Kreis", "Datum": "03.10.2026", "Uhrzeit": "14:00", "Heim": "",
             "Gast": "FC Beispiel 2", "Spielort": "Sportpark Gilching", "Link": "https://x/3",
             "Quelle": "https://bfv/quelle-a"},
        ],
    )
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    games, club_teams, sources = vis.load_games()
    assert len(games) == 1
    err = capsys.readouterr().err
    assert "2 Zeile(n) in tsv-a_spiele_web.csv ohne Heim/Gast-Team übersprungen" in err


def test_load_games_with_aliases(monkeypatch, tmp_path):
    write_fixtures(tmp_path)
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    alias_map = {"https://bfv/quelle-a": "TSV Gilching/Argelsried u15w"}
    games, club_teams, sources = vis.load_games(alias_map)
    assert club_teams == ["TSV Gilching/Argelsried u15w", U17]
    by_file = {s["file"]: s for s in sources}
    assert by_file["tsv-a_spiele_web.csv"]["team"] == "TSV Gilching/Argelsried u15w"
    assert by_file["tsv-a_spiele_web.csv"]["original"] == U15
    assert by_file["tsv-b_spiele_web.csv"]["team"] == U17

    home = [g for g in games if g["heim"] == "TSV Gilching/Argelsried u15w"]
    assert len(home) == 2
    assert all(g["is_home"] for g in home)
    away = next(g for g in games if g["gast"] == "TSV Gilching/Argelsried u15w")
    assert away["is_home"] is False
    assert all(U15 not in g.values() for g in home)


# ------------------------------------------------------------ group_by_day()


def test_group_by_day_sorts_and_groups():
    games = [
        {"date": vis.parse_datum("27.09.2026"), "datum": "27.09.2026", "time": "09:30"},
        {"date": vis.parse_datum("20.09.2026"), "datum": "20.09.2026", "time": "14:00"},
        {"date": vis.parse_datum("20.09.2026"), "datum": "20.09.2026", "time": "10:00"},
    ]
    days = vis.group_by_day(games)
    assert list(days.keys()) == ["20.09.2026", "27.09.2026"]
    assert [g["time"] for g in days["20.09.2026"]] == ["10:00", "14:00"]
    assert [g["time"] for g in days["27.09.2026"]] == ["09:30"]


def test_group_by_day_empty():
    assert vis.group_by_day([]) == {}


# ------------------------------------------------------- render_game_row()


def test_render_game_row_home():
    g = make_game("20.09.2026", "10:00", U15, "FC Gegner", is_home=True)
    row = vis.render_game_row(g, is_hot=False)
    assert 'class="tag home"' in row
    assert 'title="Heimspiel"' in row
    assert 'data-heim="TSV Gilching/Argelsried U15"' in row
    assert 'data-gast="FC Gegner"' in row
    assert "vs</span></td>" in row


def test_render_game_row_away():
    g = make_game("20.09.2026", "10:00", "FC Gegner", U15, is_home=False)
    row = vis.render_game_row(g, is_hot=False)
    assert 'class="tag away"' in row
    assert 'title="Auswärtsspiel"' in row


def test_render_game_row_no_link_no_place():
    g = make_game("20.09.2026", "10:00", U15, "FC Gegner", link="", spielort="")
    row = vis.render_game_row(g, is_hot=False)
    assert "Karte ↗" not in row
    assert "Link zum Spiel" not in row
    assert 'class="addr">' in row


# ------------------------------------------------------ render_day_section()


def test_render_day_section_hot():
    games = [
        make_game("20.09.2026", "10:00", U15, "FC Gegner 1"),
        make_game("20.09.2026", "14:00", U15, "FC Gegner 2"),
    ]
    section = vis.render_day_section("20.09.2026", games)
    assert 'class="day-header hot"' in section
    assert 'class="badge"' in section
    assert 'class="badge" style="display:none"' not in section
    assert "⚠ 2 Spiele" in section


def test_render_day_section_normal():
    games = [make_game("20.09.2026", "10:00", U15, "FC Gegner")]
    section = vis.render_day_section("20.09.2026", games)
    assert 'class="day-header"' in section
    assert 'class="day-header hot"' not in section
    assert 'style="display:none"' in section


# ------------------------------------------------------ render_team_checks()


def test_render_team_checks():
    html = vis.render_team_checks([U15, U17])
    assert 'value="TSV Gilching/Argelsried U15"' in html
    assert 'value="TSV Gilching/Argelsried U17"' in html
    assert 'data-team="TSV Gilching/Argelsried U15"' in html
    assert html.count('<input type="checkbox"') == 2


def test_render_team_checks_with_aliases():
    html = vis.render_team_checks(["TSV Gilching/Argelsried u15w", "TSV Gilching/Argelsried u17w"])
    assert 'value="TSV Gilching/Argelsried u15w"' in html
    assert 'value="TSV Gilching/Argelsried u17w"' in html


# --------------------------------------------------------- render_footer()


def test_render_footer():
    sources = [
        {"file": "a.csv", "team": U15, "url": "https://bfv/x"},
        {"file": "b.csv", "team": U17, "url": ""},
    ]
    footer = vis.render_footer(sources)
    assert '<a href="https://bfv/x"' in footer
    assert f'>{U15}</a>' in footer
    assert vis.esc(U17) in footer
    assert "Datenquelle:" in footer


# -------------------------------------------------------- render_games_js()


def test_render_games_js():
    days = {
        "20.09.2026": [make_game("20.09.2026", "10:00", U15, "FC Gegner")],
    }
    js = vis.render_games_js(days)
    import json

    data = json.loads(js)
    assert len(data) == 1
    assert data[0]["d"] == "20.09.2026"
    assert data[0]["h"] == U15
    assert data[0]["a"] == "FC Gegner"
    assert "t" in data[0]
    assert "w" in data[0]
    assert "p" in data[0]
    assert "l" in data[0]


# -------------------------------------------------------------- build_html()


def test_build_html(tmp_path):
    out = tmp_path / "spielplan.html"
    days = {
        "20.09.2026": [make_game("20.09.2026", "10:00", "TSV Gilching/Argelsried & Co", "FC <i>Gast</i>",
                                 spielort="Sportpark | Gilching")],
        "27.09.2026": [
            make_game("27.09.2026", "14:00", "TSV Gilching/Argelsried & Co", "FC Gast 2"),
            make_game("27.09.2026", "16:00", "FC Gast 3", "TSV Gilching/Argelsried & Co"),
        ],
    }
    clubs = ["TSV Gilching/Argelsried & Co"]
    sources = [{"file": "x.csv", "team": "TSV Gilching/Argelsried & Co", "url": "https://bfv/x"}]
    vis.build_html(days, clubs, sources, out)
    html = out.read_text(encoding="utf-8")
    assert "<script>" in html
    assert "const SPIELE = " in html
    assert 'data-datum="20.09.2026"' in html
    assert 'data-datum="27.09.2026"' in html
    assert 'data-heim="TSV Gilching/Argelsried &amp; Co"' in html
    assert 'data-gast="FC &lt;i&gt;Gast&lt;/i&gt;"' in html
    assert 'value="TSV Gilching/Argelsried &amp; Co"' in html
    assert 'class="day-header hot"' in html
    assert "⚠ 2 Spiele" in html
    assert "3 Spiele · 2 Spieltage ·" in html
    assert "1 Tage mit mehreren Spielen" in html
    assert "google.com/maps" in html
    assert "Datenquelle:" in html
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert 'class="table-wrap"' in html
    assert 'data-label="Heim"' in html
    assert 'data-label="Gast"' in html
    assert 'data-label="Spielort"' in html
    assert 'data-label="Zeit"' in html
    assert 'data-label="Wettbewerb"' in html
    assert 'data-label="Spiel"' in html
    assert '<span class="cell"' in html
    assert "@media (max-width: 640px)" in html
    assert "grid-template-columns:1fr auto" in html
    assert "thead" in html


def test_build_html_embeds_alias_map(tmp_path):
    out = tmp_path / "spielplan.html"
    days = {"20.09.2026": [make_game("20.09.2026", "10:00", "TSV Gilching/Argelsried 2 (7)", "FC Gegner")]}
    clubs = ["TSV Gilching/Argelsried u15w2"]
    sources = [
        {
            "file": "x.csv",
            "team": "TSV Gilching/Argelsried u15w2",
            "url": "https://bfv/x",
            "original": "TSV Gilching/Argelsried 2 (7)",
        }
    ]
    vis.build_html(days, clubs, sources, out)
    html = out.read_text(encoding="utf-8")
    assert 'const TEAM_ALIASES = [["TSV Gilching/Argelsried u15w2", "TSV Gilching/Argelsried 2 (7)"]]' in html
    assert 'value="TSV Gilching/Argelsried u15w2"' in html
    assert 'aliasToOriginal' in html


# --------------------------------------------------------------- build_pdf()


def test_build_pdf(tmp_path):
    out = tmp_path / "spielplan.pdf"
    days = {
        "20.09.2026": [make_game("20.09.2026", "10:00", "TSV Gilching/Argelsried U15", "FC Beispiel 1")],
        "27.09.2026": [
            make_game("27.09.2026", "14:00", "TSV Gilching/Argelsried U15", "FC Beispiel 2"),
            make_game("27.09.2026", "16:00", "FC Beispiel 3", "TSV Gilching/Argelsried U15"),
        ],
    }
    vis.build_pdf(days, out)
    assert out.exists()
    assert out.read_bytes()[:4] == b"%PDF"


# -------------------------------------------------------------------- main()


def test_main(monkeypatch, tmp_path, capsys):
    write_fixtures(tmp_path)
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    vis.main()
    assert (tmp_path / "spielplan.html").exists()
    assert (tmp_path / "spielplan.pdf").exists()
    out = capsys.readouterr().out
    assert "5 Spiele aus 2 Dateien" in out
    assert "spielplan.html" in out
    assert "spielplan.pdf" in out


def test_main_no_csvs(monkeypatch, tmp_path):
    monkeypatch.setattr(vis, "SCRIPT_DIR", tmp_path)
    with pytest.raises(SystemExit, match="Keine .*_spiele_web.csv Dateien gefunden"):
        vis.main()
