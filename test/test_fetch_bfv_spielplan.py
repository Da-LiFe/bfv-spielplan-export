import csv
import json
from pathlib import Path

import pytest

import fetch_bfv_spielplan as fetch

FIXTURES = Path(__file__).parent / "fixtures"

REAL_HTML = (FIXTURES / "bfv_sample.html").read_text(encoding="utf-8")

TEAM_ID = "02Q0KPORKS000000VS5489B2VTB2M2VN"
TEAM_URL = f"https://www.bfv.de/mannschaften/tsv-gilching-argelsried-2-7/{TEAM_ID}"


def entry(**kw):
    defaults = {
        "region": "U15 (C-Jun.) Norweger Modell 03",
        "link": "https://www.bfv.de/ergebnisse/spiel/-/03",
        "datum": "20.09.2026",
        "zeit": "09:00",
        "team0": "TSV Gilching/Argelsried 2 (7)",
        "team1": "TSV Herrsching (7)",
        "location": "Sportanlage Gilching, Waldplatz 2 | Talhofstraße 13 | 82205 Gilching",
    }
    defaults.update(kw)
    parts = ['<div class="bfv-spieltag-eintrag">']
    parts.append(f'<div class="bfv-spieltag-eintrag__region">{defaults["region"]}</div>')
    if defaults["link"] is not None:
        parts.append(f'<a class="bfv-spieltag-eintrag__match-link" href="{defaults["link"]}">')
    if defaults["datum"] is not None:
        parts.append(
            f'<div class="bfv-matchday-date-time">\n'
            f'<span class="bfv-matchday-date-time__day">So.</span>\n'
            f'<span>\n{defaults["datum"]}\n /{defaults["zeit"]} Uhr\n</span>\n'
            f'</div>'
        )
    parts.append(f'<div class="bfv-matchdata-result__team-name--team0">{defaults["team0"]}</div>')
    parts.append(f'<div class="bfv-matchdata-result__team-name--team1">{defaults["team1"]}</div>')
    if defaults["location"] is not None:
        parts.append(f'<div class="bfv-spieltag-eintrag__location">{defaults["location"]}</div>')
    parts.append("</div>")
    return "".join(parts)


SEPARATOR = '<div class="bfv-spieltag-matchups__separator"></div>'
SHOWMORE = '<div class="js-lazyload-filter-showmore"></div>'


# ---------------------------------------------------------------- clean()


def test_clean_strips_tags():
    assert fetch.clean("<div><b>TSV</b> Gilching</div>") == "TSV Gilching"


def test_clean_removes_wbr():
    assert fetch.clean("Gil<wbr>ching") == "Gilching"


def test_clean_unescapes_entities():
    assert fetch.clean("FC &amp; Co &lt;2&gt;") == "FC & Co <2>"


def test_clean_collapses_whitespace():
    assert fetch.clean("  A\n  B\t C  ") == "A B C"


# ------------------------------------------------------------ parse_entries()


def test_parse_entries_real_bfv_html():
    rows = fetch.parse_entries(REAL_HTML)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0["Wettbewerb"] == "U15 (C-Jun.) Norweger Modell 03"
    assert r0["Datum"] == "20.09.2026"
    assert r0["Uhrzeit"] == "09:00"
    assert r0["Heim"] == "TSV Gilching/Argelsried 2 (7)"
    assert r0["Gast"] == "TSV Herrsching (7)"
    assert r0["Spielort"].startswith("Sportanlage Gilching")
    assert r0["Link"].startswith("https://www.bfv.de/")


def test_parse_entries_multiple_separator():
    html = entry(link="https://x/1") + SEPARATOR + entry(datum="27.09.2026", link="https://x/2")
    rows = fetch.parse_entries(html)
    assert len(rows) == 2
    assert rows[1]["Datum"] == "27.09.2026"


def test_parse_entries_missing_fields_become_empty_string():
    html = entry(link=None, datum=None, location=None, region="")
    rows = fetch.parse_entries(html)
    assert len(rows) == 1
    r = rows[0]
    assert r["Link"] == ""
    assert r["Datum"] == ""
    assert r["Uhrzeit"] == ""
    assert r["Spielort"] == ""
    assert r["Wettbewerb"] == ""


def test_parse_entries_no_entries():
    assert fetch.parse_entries("<html><body>nichts</body></html>") == []


def test_parse_entries_escaped_entities_in_teams():
    html = entry(team0="FC Mustermann &amp; Söhne")
    rows = fetch.parse_entries(html)
    assert rows[0]["Heim"] == "FC Mustermann & Söhne"


# -------------------------------------------------------- fetch_all_matches()


def test_fetch_all_matches_paginates(monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if "from=0" in url:
            return entry(link="https://x/1") + SEPARATOR + entry(link="https://x/2") + SHOWMORE
        return entry(link="https://x/3")

    monkeypatch.setattr(fetch, "fetch", fake_fetch)
    rows = fetch.fetch_all_matches(TEAM_ID)
    assert len(rows) == 3
    assert len(calls) == 2
    assert calls[0] == fetch.BASE.format(TEAM_ID) + "?from=0&size=100"
    assert calls[1] == fetch.BASE.format(TEAM_ID) + "?from=100&size=100"


def test_fetch_all_matches_stops_on_empty_page(monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "<html>keine Einträge</html>"

    monkeypatch.setattr(fetch, "fetch", fake_fetch)
    rows = fetch.fetch_all_matches(TEAM_ID)
    assert rows == []
    assert len(calls) == 1


def test_fetch_all_matches_honours_max_iter(monkeypatch):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return entry(link=f"https://x/{len(calls)}") + SHOWMORE

    monkeypatch.setattr(fetch, "fetch", fake_fetch)
    rows = fetch.fetch_all_matches(TEAM_ID)
    assert len(rows) == fetch.MAX_ITER
    assert len(calls) == fetch.MAX_ITER


# ---------------------------------------------------------------- fetch_one()


FAKE_ROWS = [
    {
        "Wettbewerb": "U15 Kreis",
        "Datum": "20.09.2026",
        "Uhrzeit": "09:00",
        "Heim": "TSV Gilching/Argelsried 2 (7)",
        "Gast": "TSV Herrsching (7)",
        "Spielort": "Sportanlage Gilching",
        "Link": "https://www.bfv.de/ergebnisse/spiel/-/03",
    },
    {
        "Wettbewerb": "U15 Kreis",
        "Datum": "27.09.2026",
        "Uhrzeit": "09:30",
        "Heim": "(SG) FC Frauenwies LL (9)",
        "Gast": "TSV Gilching/Argelsried 2 (7)",
        "Spielort": "Sportplatz Stoffen",
        "Link": "https://www.bfv.de/ergebnisse/spiel/-/04",
    },
]


def test_fetch_one_writes_utf8_bom_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "fetch_all_matches", lambda team_id: FAKE_ROWS)
    monkeypatch.chdir(tmp_path)
    out_path, n = fetch.fetch_one(TEAM_URL)
    assert n == 2
    assert out_path.name == "tsv-gilching-argelsried-2-7_spiele_web.csv"
    raw = out_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with open(out_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == [
            "Wettbewerb",
            "Datum",
            "Uhrzeit",
            "Heim",
            "Gast",
            "Spielort",
            "Link",
            "Quelle",
        ]
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["Heim"] == "TSV Gilching/Argelsried 2 (7)"
    expected_source = f"https://www.bfv.de/mannschaften/tsv-gilching-argelsried-2-7/{TEAM_ID}"
    assert all(r["Quelle"] == expected_source for r in rows)


def test_fetch_one_invalid_team_id_rejected():
    with pytest.raises(ValueError, match="does not look like a valid team ID"):
        fetch.fetch_one("https://www.bfv.de/mannschaften/tsv-slug/ABC")


def test_fetch_one_unparseable_url_rejected():
    with pytest.raises(ValueError, match="could not parse team ID"):
        fetch.fetch_one("/")


# --------------------------------------------------------------- refresh()

TEAMS_JSON = [
    {"url": TEAM_URL},
    {
        "url": "https://www.bfv.de/mannschaften/tsv-slug/02R2MA58DK000000VS5489B2VS0BVSMI",
        "alias": "TSV Gilching/Argelsried u11w",
    },
]


def test_load_teams_json(tmp_path):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(json.dumps(TEAMS_JSON), encoding="utf-8")
    assert fetch.load_teams(teams_file) == [
        {"url": TEAM_URL, "alias": None},
        {
            "url": "https://www.bfv.de/mannschaften/tsv-slug/02R2MA58DK000000VS5489B2VS0BVSMI",
            "alias": "TSV Gilching/Argelsried u11w",
        },
    ]


def test_load_teams_missing_team_without_url(tmp_path):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(json.dumps([{"alias": "ohne url"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="needs a 'url' field"):
        fetch.load_teams(teams_file)


def test_load_teams_invalid_json(tmp_path):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text("{kein json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        fetch.load_teams(teams_file)


def test_refresh_all_teams(tmp_path, monkeypatch, capsys):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(json.dumps(TEAMS_JSON), encoding="utf-8")
    calls = []

    def fake_fetch_one(url):
        return Path(f"{url.split('/')[-2]}_spiele_web.csv"), 5

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(fetch, "fetch_one", fake_fetch_one)
    monkeypatch.setattr("subprocess.run", fake_run)
    fetch.refresh(teams_file)
    out = capsys.readouterr().out
    assert out.count("Wrote 5 matches to ") == 2
    assert "Total: 10 matches" in out
    assert len(calls) == 1
    assert calls[0][1]["check"] is True


def test_refresh_continues_on_error(tmp_path, monkeypatch, capsys):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(json.dumps(TEAMS_JSON), encoding="utf-8")
    monkeypatch.setattr(
        fetch,
        "fetch_one",
        lambda url: (_ for _ in ()).throw(RuntimeError("kaputt")) if "tsv-slug" in url else (Path("a.csv"), 5),
    )
    monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
    fetch.refresh(teams_file)
    out = capsys.readouterr().out
    assert "FEHLER:" in out
    assert "kaputt" in out
    assert "Total: 5 matches" in out


def test_refresh_missing_teams_file(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        fetch.refresh(tmp_path / "nope.json")


def test_refresh_no_urls(tmp_path):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="no team URLs"):
        fetch.refresh(teams_file)


def test_refresh_skips_visualize_if_missing(tmp_path, monkeypatch, capsys):
    teams_file = tmp_path / "teams.json"
    teams_file.write_text(json.dumps([{"url": TEAM_URL}]), encoding="utf-8")
    monkeypatch.setattr(fetch, "fetch_one", lambda url: (Path("a.csv"), 1))
    monkeypatch.setattr(fetch, "SCRIPT_DIR", tmp_path)
    fetch.refresh(teams_file)
    assert "Total: 1 matches" in capsys.readouterr().out


# ------------------------------------------------------------------- main()


def test_main_requires_url_or_refresh(monkeypatch):
    monkeypatch.setattr("sys.argv", ["fetch_bfv_spielplan.py"])
    with pytest.raises(SystemExit):
        fetch.main()


def test_main_single_url(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "fetch_all_matches", lambda team_id: FAKE_ROWS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["fetch_bfv_spielplan.py", TEAM_URL])
    fetch.main()
    out = capsys.readouterr().out
    assert "Wrote 2 matches to tsv-gilching-argelsried-2-7_spiele_web.csv" in out
    assert (tmp_path / "tsv-gilching-argelsried-2-7_spiele_web.csv").exists()
