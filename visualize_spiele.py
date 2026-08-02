from __future__ import annotations

import csv
import html as htmllib
import json
import re
import sys
import urllib.parse
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from config import (
    CLUB_MARKERS,
    CSV_DATE_FORMAT,
    PALETTE,
    SCRIPT_DIR,
    WEEKDAYS_DE,
    WD,
    MONTHS_DE,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet


class Source(TypedDict):
    """A source file entry with team name and BFV URL."""

    file: str
    team: str
    url: str


class Game(TypedDict):
    """A parsed game record."""

    date: datetime
    datum: str
    wd: str
    time: str
    heim: str
    gast: str
    wettbewerb: str
    spielort: str
    link: str
    quelle: str
    source: str
    is_home: bool
    home_color: str
    away_color: str


def parse_datum(s: str) -> datetime | None:
    """Parse a DD.MM.YYYY date string, or return None."""
    try:
        return datetime.strptime(s.strip(), CSV_DATE_FORMAT)
    except ValueError:
        return None


def team_color(name: str) -> str:
    """Return a deterministic color for a team name."""
    if not name:
        return "#888888"
    return PALETTE[sum(ord(c) for c in name) % len(PALETTE)]


def infer_team(
    file_games: list[Game], source_file: str, first_quelle: str
) -> tuple[str, Source]:
    """Infer the club team name from game appearances and return source info."""
    counts = Counter()
    for g in file_games:
        counts[g["heim"]] += 1
        counts[g["gast"]] += 1
    team = max(counts, key=lambda t: counts[t])
    full = next((t for t, c in counts.items() if c == len(file_games)), team)
    return full, Source(file=source_file, team=full, url=first_quelle)


def load_games() -> tuple[list[Game], list[str], list[Source]]:
    """Load all games from *_spiele_web.csv files."""
    games: list[Game] = []
    club_teams: list[str] = []
    sources: list[Source] = []
    for path in sorted(SCRIPT_DIR.glob("*_spiele_web.csv")):
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception as exc:
            print(f"Warnung: {path.name} nicht lesbar ({exc})", file=sys.stderr)
            continue
        file_games: list[Game] = []
        for r in rows:
            d = parse_datum(r.get("Datum", ""))
            if d is None:
                continue
            heim = (r.get("Heim") or "").strip()
            gast = (r.get("Gast") or "").strip()
            home_l = heim.lower()
            file_games.append(
                Game(
                    date=d,
                    datum=d.strftime("%d.%m.%Y"),
                    wd=WD[d.weekday()],
                    time=(r.get("Uhrzeit") or "").strip(),
                    heim=heim,
                    gast=gast,
                    wettbewerb=(r.get("Wettbewerb") or "").strip(),
                    spielort=(r.get("Spielort") or "").strip(),
                    link=(r.get("Link") or "").strip(),
                    quelle=(r.get("Quelle") or "").strip(),
                    source=path.name,
                    is_home=any(m in home_l for m in CLUB_MARKERS),
                    home_color=team_color(heim),
                    away_color=team_color(gast),
                )
            )
        games.extend(file_games)
        if file_games:
            team, source = infer_team(file_games, path.name, file_games[0].get("quelle", ""))
            club_teams.append(team)
            sources.append(source)
    return games, club_teams, sources


def group_by_day(games: list[Game]) -> OrderedDict[str, list[Game]]:
    """Group games by date, sorted by date then time."""
    games.sort(key=lambda g: (g["date"], g["time"] or "99:99"))
    days: OrderedDict[str, list[Game]] = OrderedDict()
    for g in games:
        days.setdefault(g["datum"], []).append(g)
    return days


def short_place(spielort: str, limit: int = 45) -> str:
    """Shorten a location string, replacing pipes with commas."""
    s = re.sub(r"\s*\|\s*", ", ", spielort)
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


def maps_url(spielort: str) -> str:
    """Build a Google Maps search URL for a location."""
    q = re.sub(r"\s*\|\s*", ", ", spielort).strip()
    if not q:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


def esc(t: str) -> str:
    """HTML-escape a string."""
    return htmllib.escape(t, quote=True)


def german_now() -> str:
    """Return the current date/time in German format."""
    now = datetime.now()
    return f"{WEEKDAYS_DE[now.weekday()]}, {now.day}. {MONTHS_DE[now.month - 1]} {now.year}, {now:%H:%M} Uhr"


def render_games_js(days: OrderedDict[str, list[Game]]) -> str:
    """Serialize games to JSON for embedding in the HTML."""
    return json.dumps(
        [
            {"d": g["datum"], "t": g["time"], "h": g["heim"], "a": g["gast"], "w": g["wettbewerb"], "p": g["spielort"], "l": g["link"]}
            for day in days.values()
            for g in day
        ],
        ensure_ascii=False,
    )


def render_game_row(g: Game, is_hot: bool) -> str:
    """Render a single game table row."""
    home_tag = (
        '<span class="tag home" title="Heimspiel">H</span>'
        if g["is_home"]
        else '<span class="tag away" title="Auswärtsspiel">A</span>'
    )
    link_html = (
        f'<a class="link" href="{esc(g["link"])}" target="_blank">Link zum Spiel ↗</a>'
        if g["link"]
        else ""
    )
    place = g["spielort"].strip()
    map_html = (
        f'<a class="map" href="{maps_url(place)}" target="_blank">Karte ↗</a>'
        if place
        else ""
    )
    return (
        f'<tr class="{"hot" if is_hot else ""}" data-heim="{esc(g["heim"])}" data-gast="{esc(g["gast"])}">'
        f'<td class="time" data-label="Zeit"><span class="cell">{esc(g["time"] or "–")}</span></td>'
        f'<td class="team" data-label="Heim" style="--c:{g["home_color"]}"><span class="cell">{esc(g["heim"])}</span></td>'
        f'<td class="vs" data-label=""><span class="cell">vs</span></td>'
        f'<td class="team" data-label="Gast" style="--c:{g["away_color"]}"><span class="cell">{esc(g["gast"])}</span></td>'
        f'<td class="comp" data-label="Wettbewerb"><span class="cell">{esc(g["wettbewerb"])}</span></td>'
        f'<td class="place" data-label="Spielort"><span class="cell"><span class="addr">{esc(place)}</span>{map_html}</span></td>'
        f'<td class="home" data-label=""><span class="cell">{home_tag}</span></td>'
        f'<td data-label="Spiel"><span class="cell">{link_html}</span></td>'
        f'</tr>'
    )


def render_day_section(datum: str, games: list[Game]) -> str:
    """Render a full day section with header, table, and game rows."""
    is_hot = len(games) >= 2
    badge_style = "" if is_hot else ' style="display:none"'
    badge = f'<span class="badge"{badge_style}>⚠ {len(games)} Spiele</span>'
    header_cls = "day-header hot" if is_hot else "day-header"
    rows_html = "".join(render_game_row(g, is_hot) for g in games)
    return (
        f'<section class="day" data-datum="{esc(datum)}">'
        f'<div class="{header_cls}"><span class="when">{esc(games[0]["wd"])}, {esc(datum)}</span>{badge}</div>'
        f'<div class="table-wrap"><table><colgroup>'
        f'<col style="width:4%"><col style="width:23%"><col style="width:3%"><col style="width:23%">'
        f'<col style="width:12%"><col style="width:24%"><col style="width:3%"><col style="width:8%">'
        f'</colgroup><thead><tr>'
        f'<th>Zeit</th><th>Heim</th><th></th><th>Gast</th><th>Wettbewerb</th><th>Spielort</th><th></th><th></th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
        f'</section>'
    )


def render_team_checks(club_teams: list[str]) -> str:
    """Render team filter checkboxes."""
    return "".join(
        f'<label class="chk"><input type="checkbox" value="{esc(t)}" data-team="{esc(t)}"> {esc(t)}</label>'
        for t in club_teams
    )


def render_footer(sources: list[Source]) -> str:
    """Render the page footer with source links."""
    src_links: list[str] = []
    for s in sources:
        if s["url"]:
            src_links.append(f'<a href="{esc(s["url"])}" target="_blank">{esc(s["team"])}</a>')
        else:
            src_links.append(esc(s["team"]))
    return f"Erstellt am {esc(german_now())}. Datenquelle: {', '.join(src_links)}"


def build_html(
    days: OrderedDict[str, list[Game]],
    club_teams: list[str],
    sources: list[Source],
    out_path: Path,
) -> None:
    """Build the full HTML overview page."""
    total = sum(len(v) for v in days.values())
    hot_days = {d: len(v) for d, v in days.items() if len(v) >= 2}

    team_checks_html = render_team_checks(club_teams)

    sections: list[str] = []
    for datum, games in days.items():
        sections.append(render_day_section(datum, games))

    games_js = render_games_js(days)

    footer_html = render_footer(sources)

    html = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spielplan – Übersicht</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; background:#f4f5f7; color:#222; margin:0; padding:24px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color:#666; margin-bottom:16px; }}
  .filter {{ margin-bottom:20px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
  .filter label {{ font-size:14px; color:#444; font-weight:600; }}
  .filter .chk {{ display:inline-flex; align-items:center; gap:6px; font-weight:500; padding:4px 8px; border:1px solid #e0e0e0; border-radius:6px; background:#fff; font-size:13px; cursor:pointer; color:#333; }}
  .filter .chk input {{ margin:0; }}
  .filter .chk:hover {{ border-color:#0d6efd; }}
  .filter .chk.past {{ border-style:dashed; }}
  .filter .chk.past input {{ accent-color:#b8860b; }}
  .legend {{ display:flex; gap:16px; margin-bottom:20px; color:#555; font-size:13px; flex-wrap:wrap; }}
  .legend span {{ display:inline-flex; align-items:center; gap:4px; }}
  .day {{ background:#fff; border:1px solid #e0e0e0; border-radius:8px; margin-bottom:18px; overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,.05); }}
  .day-header {{ padding:10px 14px; font-weight:600; background:#eef2f7; border-bottom:1px solid #e0e0e0; display:flex; align-items:center; justify-content:space-between; }}
  .day-header.hot {{ background:#fff3cd; border-bottom:1px solid #ffc107; }}
  .badge {{ background:#dc3545; color:#fff; font-size:12px; padding:2px 10px; border-radius:12px; font-weight:600; }}
  table {{ border-collapse:collapse; width:100%; table-layout:fixed; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; color:#888; padding:6px 10px; border-bottom:1px solid #eee; }}
  td {{ padding:8px 10px; border-bottom:1px solid #f0f0f0; font-size:14px; vertical-align:middle; }}
  tr.hot td {{ background:#fffaf0; }}
  tr:last-child td {{ border-bottom:none; }}
  .time {{ white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .vs {{ color:#bbb; }}
  .comp {{ color:#555; font-size:12px; }}
  .place {{ color:#777; font-size:12px; }}
  .addr {{ display:block; word-break:break-word; }}
  .map {{ color:#0d6efd; text-decoration:none; font-size:12px; white-space:nowrap; }}
  .map:hover {{ text-decoration:underline; }}
  .home {{ text-align:center; }}
  .team .cell {{ color:var(--c, #222); font-weight:600; }}
  .tag {{ display:inline-block; width:18px; height:18px; line-height:18px; border-radius:50%; font-size:11px; color:#fff; text-align:center; }}
  .tag.home {{ background:#198754; }}
  .tag.away {{ background:#6c757d; }}
  .link {{ color:#0d6efd; text-decoration:none; font-size:13px; }}
  .link:hover {{ text-decoration:underline; }}
  .export-btn {{ background:#0d6efd; color:#fff; border:none; border-radius:6px; padding:7px 14px; font-size:14px; cursor:pointer; font-weight:600; }}
  .export-btn:hover {{ background:#0b5ed7; }}
  .table-wrap {{ overflow-x:auto; }}
  .foot {{ color:#999; font-size:12px; margin-top:8px; }}
  @media (max-width: 640px) {{
    body {{ padding:10px; }}
    h1 {{ font-size:18px; }}
    .sub {{ font-size:13px; margin-bottom:12px; }}
    .filter {{ gap:8px; }}
    .filter > label {{ font-size:13px; }}
    .filter .chk {{ padding:6px 10px; font-size:13px; min-height:38px; }}
    .export-btn {{ width:100%; padding:10px 14px; }}
    .legend {{ gap:10px; font-size:12px; margin-bottom:14px; }}
    .day {{ margin-bottom:14px; }}
    .day-header {{ padding:8px 12px; }}
    .table-wrap {{ overflow-x:visible; }}
    thead {{ display:none; }}
    colgroup {{ display:none; }}
    table {{ display:block; width:100%; }}
    tbody {{ display:block; width:100%; }}
    tbody tr {{ display:grid; grid-template-columns:1fr auto; gap:2px 8px; padding:10px 12px; border-bottom:1px solid #f0f0f0; }}
    tr.hot {{ background:#fffaf0; }}
    tr.hot td {{ background:transparent; }}
    td {{ display:flex; flex-direction:column; gap:1px; padding:4px 0; border-bottom:none; font-size:14px; color:#111; min-width:0; }}
    td::before {{ content:attr(data-label); color:#666; font-size:10px; text-transform:uppercase; font-weight:700; letter-spacing:.05em; }}
    td[data-label=""]::before {{ content:none; }}
    td .cell {{ width:100%; min-width:0; }}
    td.vs {{ display:none; }}
    td:nth-child(1) {{ grid-column:1; grid-row:1; }}
    td:nth-child(7) {{ grid-column:2; grid-row:1; align-items:flex-end; }}
    td:nth-child(2) {{ grid-column:1 / 3; grid-row:2; }}
    td:nth-child(4) {{ grid-column:1 / 3; grid-row:3; }}
    td:nth-child(5) {{ grid-column:1 / 3; grid-row:4; }}
    td:nth-child(6) {{ grid-column:1 / 3; grid-row:5; }}
    td:nth-child(8) {{ grid-column:1 / 3; grid-row:6; }}
    td.team .cell {{ font-size:15px; font-weight:700; color:#111; }}
    td.team .cell::before {{ content:""; display:inline-block; width:10px; height:10px; border-radius:50%; background:var(--c); margin-right:7px; vertical-align:1px; }}
    td.comp .cell, td.place .cell {{ font-size:13px; }}
    td.comp .cell {{ color:#333; }}
    td.place .cell {{ color:#444; }}
    td .cell .link {{ font-size:14px; }}
    td:has(.cell:empty) {{ display:none; }}
    .addr {{ word-break:break-word; }}
    .foot {{ font-size:11px; }}
  }}
</style>
</head>
<body>
<h1>Spielplan – TSV Gilching/Argelsried</h1>
<div class="sub" id="summary">{total} Spiele · {len(days)} Spieltage · <span style="color:#b8860b;font-weight:600">{len(hot_days)} Tage mit mehreren Spielen</span></div>
<div class="filter">
  <label>Teams:</label>
  <label class="chk"><input type="checkbox" id="allTeams" checked> Alle Teams</label>
  {team_checks_html}
  <label class="chk past" title="Spiele an vergangenen Tagen ausblenden"><input type="checkbox" id="hidePast" checked> Vergangene Spiele ausblenden</label>
  <button type="button" id="icsExport" class="export-btn">Kalender-Export (.ics)</button>
</div>
<div class="legend">
  <span><span class="tag home">H</span> Heimspiel</span>
  <span><span class="tag away">A</span> Auswärtsspiel</span>
  <span>Hinterlegte Zeilen = mehrere Spiele am selben Tag</span>
</div>
{''.join(sections)}
<div class="foot">{footer_html}</div>
<script>
  const SPIELE = {games_js};
  const summaryAll = document.getElementById('summary').innerHTML;
  const allCheck = document.getElementById('allTeams');
  const teamChecks = Array.from(document.querySelectorAll('input[data-team]'));
  const sections = Array.from(document.querySelectorAll('.day'));

  function selectedTeams() {{
    if (allCheck.checked) return null;
    const sel = teamChecks.filter(c => c.checked).map(c => c.value);
    return sel.length ? sel : null;
  }}

  const today = new Date();
  const todayKey = String(today.getFullYear()) + String(today.getMonth() + 1).padStart(2, '0') + String(today.getDate()).padStart(2, '0');
  const dayKey = (d) => d.split('.').reverse().join('');
  const hidePastCheck = document.getElementById('hidePast');

  function applyFilter() {{
    const sel = selectedTeams();
    const hidePast = hidePastCheck.checked;
    let daysShown = 0, gamesShown = 0, hotShown = 0;
    sections.forEach(section => {{
      if (hidePast && dayKey(section.dataset.datum) < todayKey) {{
        section.style.display = 'none';
        return;
      }}
      const trs = Array.from(section.querySelectorAll('tbody tr'));
      let visible = 0;
      trs.forEach(tr => {{
        const show = sel === null || sel.includes(tr.dataset.heim) || sel.includes(tr.dataset.gast);
        tr.style.display = show ? '' : 'none';
        if (show) visible++;
      }});
      const header = section.querySelector('.day-header');
      const badge = section.querySelector('.badge');
      if (visible === 0) {{
        section.style.display = 'none';
      }} else {{
        section.style.display = '';
        daysShown++;
        gamesShown += visible;
        if (visible >= 2) {{
          hotShown++;
          header.classList.add('hot');
          badge.textContent = '⚠ ' + visible + ' Spiele';
          badge.style.display = '';
        }} else {{
          header.classList.remove('hot');
          badge.style.display = 'none';
        }}
      }}
    }});
    const summary = document.getElementById('summary');
    const pastNote = hidePast ? ' · vergangene Spiele ausgeblendet' : '';
    if (sel === null && !hidePast) {{
      summary.innerHTML = summaryAll;
    }} else {{
      const label = sel === null ? 'Alle Teams' : sel.join(', ');
      summary.textContent = label + ': ' + gamesShown + ' Spiele · ' + daysShown + ' Spieltage · ' + hotShown + ' Tage mit mehreren Spielen' + pastNote;
    }}
  }}

  hidePastCheck.addEventListener('change', applyFilter);

  teamChecks.forEach(c => c.addEventListener('change', () => {{
    allCheck.checked = !teamChecks.some(x => x.checked);
    applyFilter();
  }}));
  allCheck.addEventListener('change', () => {{
    teamChecks.forEach(c => c.checked = allCheck.checked);
    applyFilter();
  }});

  const params = new URLSearchParams(window.location.search);
  const teamParams = params.getAll('team');
  if (teamParams.length) {{
    const found = teamChecks.filter(c => teamParams.includes(c.value));
    if (found.length) {{
      teamChecks.forEach(c => c.checked = false);
      found.forEach(c => c.checked = true);
      allCheck.checked = false;
    }}
  }}
  applyFilter();

  function icsDate(d) {{ return d.split('.').reverse().join(''); }}
  function icsEscape(t) {{ return t.replace(/\\\\/g, '\\\\\\\\').replace(/;/g, '\\\\;').replace(/,/g, '\\\\,').replace(/\\n/g, '\\\\n'); }}
  function icsFold(s) {{
    const out = [];
    for (let i = 0; i < s.length; i += 73) out.push(s.slice(i, i + 73));
    return out.join('\\r\\n ');
  }}
  function icsEnd(d, t) {{
    const [hh, mm] = t.split(':').map(Number);
    let total = hh * 60 + mm + 120;
    const extra = Math.floor(total / 1440);
    total %= 1440;
    const [dd, mo, yy] = d.split('.').map(Number);
    const dt = new Date(Date.UTC(yy, mo - 1, dd + extra));
    return dt.toISOString().slice(0, 10).replace(/-/g, '') + 'T' + String(Math.floor(total / 60)).padStart(2, '0') + String(total % 60).padStart(2, '0') + '00';
  }}

  document.getElementById('icsExport').addEventListener('click', function () {{
    const sel = selectedTeams();
    let games = sel === null ? SPIELE : SPIELE.filter(g => sel.includes(g.h) || sel.includes(g.a));
    if (hidePastCheck.checked) {{
      games = games.filter(g => dayKey(g.d) >= todayKey);
    }}
    if (!games.length) {{ alert('Keine Spiele für die Auswahl.'); return; }}
    const calName = sel === null ? 'Spielplan TSV Gilching/Argelsried' : sel.join(', ');
    const lines = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//Spielplan//TSV Gilching Argelsried//DE',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH',
      'X-WR-CALNAME:' + calName,
      'BEGIN:VTIMEZONE',
      'TZID:Europe/Berlin',
      'BEGIN:DAYLIGHT',
      'TZOFFSETFROM:+0100', 'TZOFFSETTO:+0200', 'TZNAME:CEST',
      'DTSTART:19700329T020000', 'RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU',
      'END:DAYLIGHT',
      'BEGIN:STANDARD',
      'TZOFFSETFROM:+0200', 'TZOFFSETTO:+0100', 'TZNAME:CET',
      'DTSTART:19701025T030000', 'RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU',
      'END:STANDARD',
      'END:VTIMEZONE'
    ];
    games.forEach(g => {{
      lines.push('BEGIN:VEVENT');
      lines.push('UID:' + (g.l ? g.l.split('/').pop() : (g.d + g.t)) + '@bfv-spielplan');
      lines.push('DTSTAMP:' + new Date().toISOString().replace(/[-:]/g, '').replace(/\\.[0-9]+Z/, 'Z'));
      if (g.t) {{
        lines.push('DTSTART;TZID=Europe/Berlin:' + icsDate(g.d) + 'T' + g.t.replace(':', '') + '00');
        lines.push('DTEND;TZID=Europe/Berlin:' + icsEnd(g.d, g.t));
      }} else {{
        lines.push('DTSTART;VALUE=DATE:' + icsDate(g.d));
      }}
      lines.push('SUMMARY:' + icsEscape(g.h + ' - ' + g.a));
      if (g.w) lines.push('DESCRIPTION:' + icsEscape(g.w));
      if (g.p) lines.push('LOCATION:' + icsEscape(g.p));
      if (g.l) lines.push('URL:' + g.l);
      lines.push('END:VEVENT');
    }});
    lines.push('END:VCALENDAR');
    const blob = new Blob([lines.map(icsFold).join('\\r\\n')], {{ type: 'text/calendar;charset=utf-8' }});
    const slug = sel === null ? 'alle' : sel.length === 1 ? sel[0].toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') : 'auswahl';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'spielplan_' + slug + '.ics';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }});
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def build_pdf(days: OrderedDict[str, list[Game]], out_path: Path) -> None:
    """Build a multi-page PDF overview of all games."""
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=18, spaceAfter=2)
    subtitle = ParagraphStyle(
        "st", parent=styles["Normal"], textColor=colors.grey, fontSize=10, spaceAfter=14
    )
    day_head = ParagraphStyle(
        "dh", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#1a1a1a"), spaceAfter=0
    )
    day_head_hot = ParagraphStyle("dhh", parent=day_head, textColor=colors.HexColor("#8a6d1a"))
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=8, leading=10, spaceAfter=0)
    cell_white = ParagraphStyle("cw", parent=cell, textColor=colors.white, fontSize=9)

    LEFT_MARGIN = 14 * mm
    RIGHT_MARGIN = 14 * mm
    HEADER_COL = 16 * mm
    VS_COL = 46 * mm
    COMP_COL = 40 * mm
    HOME_COL = 20 * mm
    CONTENT_WIDTH = A4[0] - LEFT_MARGIN - RIGHT_MARGIN
    DYNAMIC_COL = CONTENT_WIDTH - HEADER_COL - VS_COL - COMP_COL - HOME_COL
    col_w = [HEADER_COL, DYNAMIC_COL, VS_COL, COMP_COL, HOME_COL]

    total = sum(len(v) for v in days.values())
    hot = sum(1 for v in days.values() if len(v) >= 2)

    story = [
        Paragraph("Spielplan – TSV Gilching/Argelsried", title),
        Paragraph(
            f"{total} Spiele · {len(days)} Spieltage · {hot} Tage mit mehreren Spielen", subtitle
        ),
    ]

    for datum, games in days.items():
        is_hot = len(games) >= 2
        header_text = (
            f"{games[0]['wd']}, {datum}" + (f" &nbsp;·&nbsp; {len(games)} Spiele" if is_hot else "")
        )
        story.append(Spacer(1, 6))
        story.append(Paragraph(header_text, day_head_hot if is_hot else day_head))

        data = [
            [
                Paragraph("Zeit", cell),
                Paragraph("Begegnung", cell),
                Paragraph("Wettbewerb", cell),
                Paragraph("Spielort", cell),
                Paragraph("", cell),
            ]
        ]
        for g in games:
            home_l, away_l = g["heim"], g["gast"]
            if not g["is_home"]:
                home_l, away_l = away_l, home_l
            match = (
                f'<font color="{g["home_color"]}"><b>{esc(home_l)}</b></font> '
                f'<font color="#999">–</font> '
                f'<font color="{g["away_color"]}">{esc(away_l)}</font>'
            )
            link = (
                f'<link href="{esc(g["link"])}"><font color="#0d6efd">Spiel ↗</font></link>'
                if g["link"]
                else ""
            )
            data.append(
                [
                    Paragraph(esc(g["time"] or "–"), cell),
                    Paragraph(match, cell),
                    Paragraph(esc(g["wettbewerb"]), cell),
                    Paragraph(esc(short_place(g["spielort"], 45)), cell),
                    Paragraph(link, cell),
                ]
            )
        t = Table(data, colWidths=col_w, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#666666")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e0e0e0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        if is_hot:
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fff8e1")),
                        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#f0ad4e")),
                    ]
                )
            )
        story.append(t)

    SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Spielplan – TSV Gilching/Argelsried",
    ).build(story)


def main() -> None:
    """Load games, generate HTML and PDF overviews."""
    games, club_teams, sources = load_games()
    if not games:
        sys.exit("Keine *_spiele_web.csv Dateien gefunden.")
    days = group_by_day(games)
    html_path = SCRIPT_DIR / "spielplan.html"
    pdf_path = SCRIPT_DIR / "spielplan.pdf"
    build_html(days, club_teams, sources, html_path)
    build_pdf(days, pdf_path)
    print(f"{len(games)} Spiele aus {len({g['source'] for g in games})} Dateien")
    print(f"HTML: {html_path}")
    print(f"PDF:  {pdf_path}")


if __name__ == "__main__":
    main()
