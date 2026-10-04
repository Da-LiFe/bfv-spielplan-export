"""T10: overview and Anwesenheit PDFs use the shared club header."""

from collections import OrderedDict
from datetime import date, datetime

import pytest
from pdfminer.high_level import extract_text

import anwesenheit
import aufstellung
import config
import pdf_overview


@pytest.fixture
def logo(tmp_path, monkeypatch):
    """Make ``get_logo`` return a real PNG; return a setter for None."""
    from PIL import Image

    path = tmp_path / "logo.png"
    Image.new("RGB", (20, 20), "red").save(path)
    monkeypatch.setattr(aufstellung, "get_logo", lambda **kw: path)
    return path


@pytest.fixture
def no_logo(monkeypatch):
    monkeypatch.setattr(aufstellung, "get_logo", lambda **kw: None)


def overview_days():
    d = datetime(2026, 5, 2)
    g = {
        "date": d,
        "datum": "02.05.2026",
        "wd": "Sa",
        "time": "10:00",
        "heim": "TSV Gilching/Argelsried U15",
        "gast": "FC A",
        "wettbewerb": "Kreis",
        "spielort": "Platz",
        "link": "",
        "is_home": True,
        "home_color": "#000",
        "away_color": "#000",
    }
    return OrderedDict([("02.05.2026", [g, {**g, "gast": "FC B"}])])


SESSIONS = [
    {"date": date(2026, 9, 7), "team": "Team A", "values": {"Lena": "P"}},
    {"date": date(2026, 9, 14), "team": "Team B", "values": {"Max": "S"}},
]


def first_lines(pdf):
    return [line for line in extract_text(str(pdf)).splitlines() if line][:6]


def test_overview_header(tmp_path, logo):
    out = tmp_path / "o.pdf"
    pdf_overview.build_pdf(overview_days(), out)
    head = first_lines(out)
    assert head[:2] == [config.CLUB_NAME, "Spielplan"]
    assert "2 Spiele · 1 Spieltage · 1 Tage mit mehreren Spielen" in head
    assert b"/Subtype /Image" in out.read_bytes()


def test_overview_header_without_logo(tmp_path, no_logo):
    out = tmp_path / "o.pdf"
    pdf_overview.build_pdf(overview_days(), out)
    assert first_lines(out)[:2] == [config.CLUB_NAME, "Spielplan"]
    assert b"/Subtype /Image" not in out.read_bytes()


def test_anwesenheit_header(tmp_path, logo):
    out = tmp_path / "a.pdf"
    anwesenheit.build_anwesenheit_pdf(SESSIONS, out)
    head = first_lines(out)
    assert head[:2] == [config.CLUB_NAME, "Anwesenheit – Auswertung"]
    assert head[2].startswith("Stand: ")
    assert b"/Subtype /Image" in out.read_bytes()


def test_anwesenheit_header_single_team(tmp_path, no_logo):
    out = tmp_path / "a.pdf"
    anwesenheit.build_anwesenheit_pdf(SESSIONS[:1], out)
    head = first_lines(out)
    assert head[:3] == [config.CLUB_NAME, "Anwesenheit – Auswertung", "Team A"]
    assert head[3].startswith("Stand: ")
    assert b"/Subtype /Image" not in out.read_bytes()
