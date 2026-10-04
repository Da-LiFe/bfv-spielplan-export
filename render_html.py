"""HTML rendering for the Spielplan overview page.

Takes games grouped by day and produces a self-contained HTML file with
embedded JavaScript for filtering and sorting.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from string import Template

from config import CLUB_NAME
from games import Game
from pdf_common import german_now
from util import esc, maps_url


def render_games_js(days: OrderedDict[str, list[Game]]) -> str:
    """Serialize games to JSON for embedding in the HTML."""
    # Escape </ to prevent premature closing of <script> tags.
    return json.dumps(
        [
            {
                "d": g["datum"],
                "t": g["time"],
                "h": g["heim"],
                "a": g["gast"],
                "w": g["wettbewerb"],
                "p": g["spielort"],
                "l": g["link"],
            }
            for day in days.values()
            for g in day
        ],
        ensure_ascii=False,
    ).replace("</", "\\u003c/")


def render_aliases_js(sources: list) -> str:
    """Serialize team aliases to JSON for embedding in the HTML."""
    return json.dumps(
        [[s["team"], s.get("original", s["team"])] for s in sources],
        ensure_ascii=False,
    ).replace("</", "\\u003c/")


def render_game_row(g: Game, is_hot: bool) -> str:
    """Render a single game table row."""
    home_tag = (
        '<span class="tag home" title="Heimspiel">H</span>'
        if g["is_home"]
        else '<span class="tag away" title="Auswärtsspiel">A</span>'
    )
    link_html = (
        f'<a class="link" href="{esc(g["link"])}" target="_blank">Link zum Spiel &nearr;</a>'
        if g["link"]
        else ""
    )
    place = g["spielort"].strip()
    map_html = (
        f'<a class="map" href="{maps_url(place)}" target="_blank">Karte &nearr;</a>'
        if place
        else ""
    )
    return (
        f'<tr class="{"hot" if is_hot else ""}" data-heim="{esc(g["heim"])}" data-gast="{esc(g["gast"])}">'
        f'<td class="time" data-label="Zeit"><span class="cell">{esc(g["time"] or "\u2013")}</span></td>'
        f'<td class="team" data-label="Heim" style="--c:{g["home_color"]}"><span class="cell">{esc(g["heim"])}</span></td>'
        f'<td class="vs" data-label=""><span class="cell">vs</span></td>'
        f'<td class="team" data-label="Gast" style="--c:{g["away_color"]}"><span class="cell">{esc(g["gast"])}</span></td>'
        f'<td class="comp" data-label="Wettbewerb"><span class="cell">{esc(g["wettbewerb"])}</span></td>'
        f'<td class="place" data-label="Spielort"><span class="cell"><span class="addr">{esc(place)}</span>{map_html}</span></td>'
        f'<td class="home" data-label=""><span class="cell">{home_tag}</span></td>'
        f'<td data-label="Spiel"><span class="cell">{link_html}</span></td>'
        f"</tr>"
    )


def render_day_section(datum: str, games: list[Game]) -> str:
    """Render a full day section with header, table, and game rows."""
    is_hot = len(games) >= 2
    badge_style = "" if is_hot else ' style="display:none"'
    badge = f'<span class="badge"{badge_style}>\u26a0 {len(games)} Spiele</span>'
    header_cls = "day-header hot" if is_hot else "day-header"
    hidden_cls = ' class="hidden-teams" style="display:none"'
    unfold_btn = ""
    if is_hot:
        unfold_btn = f'<button type="button" class="unfold-btn" data-datum="{esc(datum)}">Alle Spiele</button>'
    rows_html = "".join(render_game_row(g, is_hot) for g in games)
    return (
        f'<section class="day" data-datum="{esc(datum)}">'
        f'<div class="{header_cls}"><span class="when">{esc(games[0]["wd"])}, {esc(datum)}</span><span>{badge}{unfold_btn}<span{hidden_cls}></span></span></div>'
        f'<div class="table-wrap"><table><colgroup>'
        f'<col style="width:4%"><col style="width:23%"><col style="width:3%"><col style="width:23%">'
        f'<col style="width:12%"><col style="width:24%"><col style="width:3%"><col style="width:8%">'
        f"</colgroup><thead><tr>"
        f"<th>Zeit</th><th>Heim</th><th></th><th>Gast</th><th>Wettbewerb</th><th>Spielort</th><th></th><th></th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table></div>"
        f"</section>"
    )


def render_team_checks(club_teams: list[str]) -> str:
    """Render team filter checkboxes."""
    return "".join(
        f'<label class="chk"><input type="checkbox" value="{esc(t)}" data-team="{esc(t)}"> {esc(t)}</label>'
        for t in club_teams
    )


def render_footer(sources: list) -> str:
    """Render the page footer with source links."""
    src_links: list[str] = []
    for s in sources:
        if s["url"]:
            src_links.append(
                f'<a href="{esc(s["url"])}" target="_blank">{esc(s["team"])}</a>'
            )
        else:
            src_links.append(esc(s["team"]))
    return f"Erstellt am {esc(german_now())}. Datenquelle: {', '.join(src_links)}"


def build_html(
    days: OrderedDict[str, list[Game]],
    club_teams: list[str],
    sources: list,
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
    aliases_js = render_aliases_js(sources)

    footer_html = render_footer(sources)

    template_path = Path(__file__).parent / "templates" / "spielplan.html"
    template = Template(template_path.read_text(encoding="utf-8"))
    html = template.safe_substitute(
        club_name=esc(CLUB_NAME),
        total=str(total),
        num_days=str(len(days)),
        num_hot_days=str(len(hot_days)),
        team_checks=team_checks_html,
        sections="".join(sections),
        footer=footer_html,
        games_js=games_js,
        aliases_js=aliases_js,
    )
    out_path.write_text(html, encoding="utf-8")
