from __future__ import annotations

import argparse
import csv
import hashlib
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import TypedDict

from config import SCRIPT_DIR

CACHE_DIR = SCRIPT_DIR / ".bfv_cache"
CACHE_TTL = 3600  # 1 hour

BASE = "https://www.bfv.de/partial/mannschaftsprofil/spielplan/{}/alle"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
SIZE = 100
MAX_ITER = 10


class Entry(TypedDict):
    """A single parsed BFV match entry."""

    Wettbewerb: str
    Datum: str
    Uhrzeit: str
    Heim: str
    Gast: str
    Spielort: str
    Link: str
    Quelle: str


def _remove_wbr(text: str) -> str:
    """Remove &lt;wbr&gt; tags from text."""
    return re.sub(r"<wbr>", "", text)


def _strip_tags(text: str) -> str:
    """Remove all HTML tags from text."""
    return re.sub(r"<[^>]+>", " ", text)


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace into a single space and strip."""
    return re.sub(r"\s+", " ", text).strip()


def clean(x: str) -> str:
    """Strip HTML tags, wbr, entities, and collapse whitespace."""
    x = _remove_wbr(x)
    x = _strip_tags(x)
    x = htmllib.unescape(x)
    return _collapse_whitespace(x)


def _cache_key(url: str) -> str:
    """Return a safe filename for caching a URL response."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _cache_get(url: str) -> str | None:
    """Return cached content if fresh, else None."""
    key = _cache_key(url)
    cache_file = CACHE_DIR / f"{key}.html"
    if not cache_file.exists():
        return None
    age = time.time() - cache_file.stat().st_mtime
    if age > CACHE_TTL:
        cache_file.unlink(missing_ok=True)
        return None
    return cache_file.read_text(encoding="utf-8")


def _cache_put(url: str, content: str) -> None:
    """Save content to cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(url)
    (CACHE_DIR / f"{key}.html").write_text(content, encoding="utf-8")


def fetch(url: str) -> str:
    """Fetch a URL and return its text content, using local cache."""
    cached = _cache_get(url)
    if cached is not None:
        return cached
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ConnectionError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Network error for {url}: {exc.reason}") from exc
    _cache_put(url, content)
    return content


class _BFVParser(HTMLParser):
    """Parse bfv-spieltag-eintrag blocks from BFV HTML markup."""

    _FIELD_CLASSES = {
        "bfv-spieltag-eintrag__region": "Wettbewerb",
        "bfv-matchday-date-time": "_datetime",
        "bfv-matchdata-result__team-name--team0": "Heim",
        "bfv-matchdata-result__team-name--team1": "Gast",
        "bfv-spieltag-eintrag__location": "Spielort",
    }

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[Entry] = []
        self._current: Entry | None = None
        self._div_depth = 0
        self._active_field: str | None = None
        self._field_enter_depth: dict[str, int] = {}
        self._datetime_raw: str = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "div" and cls == "bfv-spieltag-eintrag":
            if self._current is not None:
                self._entries.append(self._current)
            self._current = {
                "Wettbewerb": "",
                "Datum": "",
                "Uhrzeit": "",
                "Heim": "",
                "Gast": "",
                "Spielort": "",
                "Link": "",
                "Quelle": "",
            }
            self._div_depth = 0
            self._active_field = None
            self._field_enter_depth = {}
            self._datetime_raw = ""
            return

        if self._current is None:
            return

        if tag == "div":
            self._div_depth += 1

        if cls == "bfv-spieltag-eintrag__match-link":
            href = attrs_dict.get("href")
            if href:
                self._current["Link"] = href.strip()

        if tag == "div" and cls:
            classes = cls.split()
            for c in classes:
                if c in self._FIELD_CLASSES:
                    field = self._FIELD_CLASSES[c]
                    self._active_field = field
                    self._field_enter_depth[field] = self._div_depth
                    if field == "_datetime":
                        self._datetime_raw = ""
                    break

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag != "div":
            return

        self._div_depth -= 1

        for field in list(self._field_enter_depth.keys()):
            if self._field_enter_depth[field] == self._div_depth + 1:
                del self._field_enter_depth[field]
                if self._active_field == field:
                    self._active_field = None
                if field == "_datetime":
                    m = re.search(
                        r"(\d{2}\.\d{2}\.\d{4})\s*/\s*(\d+:\d+)",
                        self._datetime_raw,
                    )
                    if m:
                        self._current["Datum"] = m.group(1)
                        self._current["Uhrzeit"] = m.group(2)
                break

    def handle_data(self, data: str) -> None:
        if self._current is None or not self._active_field:
            return
        if not data.strip():
            return
        if self._active_field == "_datetime":
            self._datetime_raw += data
        else:
            self._current[self._active_field] += data  # type: ignore[literal-required]

    def close(self) -> None:
        super().close()
        if self._current is not None:
            self._entries.append(self._current)


def _clean_entry(entry: Entry) -> Entry:
    """Apply clean() to text fields of a parsed entry."""
    for key in ("Wettbewerb", "Datum", "Uhrzeit", "Heim", "Gast", "Spielort", "Link"):
        entry[key] = clean(entry[key]) if entry[key] else ""
    return entry


def parse_entries(html_text: str) -> list[Entry]:
    """Parse match entries from BFV HTML markup using html.parser."""
    parser = _BFVParser()
    parser.feed(html_text)
    parser.close()
    return [_clean_entry(e) for e in parser._entries]


def fetch_all_matches(team_id: str) -> list[Entry]:
    """Fetch all match entries for a team, handling pagination."""
    all_rows: list[Entry] = []
    from_ = 0
    rate_limit = float(os.environ.get("BFV_RATE_LIMIT", "0.0"))
    for i in range(MAX_ITER):
        if i > 0 and rate_limit > 0:
            time.sleep(rate_limit)
        url = f"{BASE.format(team_id)}?from={from_}&size={SIZE}"
        html_text = fetch(url)
        rows = parse_entries(html_text)
        if not rows:
            break
        all_rows.extend(rows)
        if "js-lazyload-filter-showmore" not in html_text:
            break
        from_ += SIZE
    return all_rows


def _resolve_team_name(html: str, url: str) -> str:
    """Extract a display name for a team from its BFV profile page HTML."""
    title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
        for suffix in ["– bfv.de", " - bfv.de", " | bfv.de", "– bfv", " | bfv"]:
            if suffix in title:
                title = title.split(suffix)[0].strip()
                break
        if title:
            return title
    parts = [p for p in url.rstrip("/").split("/") if p]
    if len(parts) >= 2:
        slug = parts[-2]
        return slug.replace("-", " ").title()
    return url


def _ensure_team_in_teams_json(url: str, alias: str, teams_path: Path) -> None:
    """Add url to teams.json if not already present."""
    if teams_path.exists():
        try:
            data = json.loads(teams_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data: list[dict] = []
    else:
        data = []
    for entry in data:
        if isinstance(entry, dict) and entry.get("url") == url:
            return
    data.append({"url": url, "alias": alias})
    teams_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f'Added "{alias}" ({url}) to teams.json')


def fetch_one(url: str, teams_path: Path | None = None) -> tuple[Path, int]:
    """Fetch a single team's schedule and write it to a CSV file."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    if not parts:
        raise ValueError(f"could not parse team ID from URL: {url}")
    team_id = parts[-1]
    if not re.fullmatch(r"[0-9A-Za-z]{8,40}", team_id):
        raise ValueError(f"'{team_id}' does not look like a valid team ID (from {url})")
    slug = parts[-2] if len(parts) >= 2 else team_id
    quelle = f"https://www.bfv.de/mannschaften/{slug}/{team_id}"
    out_path = Path(f"{slug}_spiele_web.csv")
    rows = fetch_all_matches(team_id)
    for r in rows:
        r["Quelle"] = quelle
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "Wettbewerb",
                "Datum",
                "Uhrzeit",
                "Heim",
                "Gast",
                "Spielort",
                "Link",
                "Quelle",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    if teams_path is not None:
        profile_html = fetch(quelle)
        alias = _resolve_team_name(profile_html, url)
        _ensure_team_in_teams_json(url, alias, teams_path)
    return out_path, len(rows)


def load_teams(teams_path: Path) -> list[dict]:
    """Load team entries (url + optional alias) from a JSON file."""
    if not teams_path.exists():
        sys.exit(f"Error: {teams_path} not found.")
    try:
        data = json.loads(teams_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"Error: {teams_path} is not valid JSON: {exc}")
    teams: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("url"):
            sys.exit(f"Error: each entry in {teams_path} needs a 'url' field.")
        teams.append({"url": entry["url"], "alias": entry.get("alias")})
    if not teams:
        sys.exit(f"Error: no team URLs found in {teams_path}.")
    return teams


def fetch_all(teams: list[dict]) -> int:
    """Fetch every team's schedule, print progress, return total match count."""
    total = 0
    for team in teams:
        url = team["url"]
        try:
            out_path, n = fetch_one(url)
        except Exception as exc:
            print(f"FEHLER: {url} -> {exc}", flush=True)
            continue
        total += n
        print(f"Wrote {n} matches to {out_path}", flush=True)
    print(f"Total: {total} matches", flush=True)
    return total


def regenerate_html(script_dir: Path) -> None:
    """Run visualize_spiele.py if any CSV files exist."""
    visualize = script_dir / "visualize_spiele.py"
    if visualize.exists():
        import subprocess

        subprocess.run([sys.executable, str(visualize)], check=True, timeout=120)


def refresh(teams_path: Path) -> None:
    """Re-fetch all teams from a teams JSON file and regenerate the overview."""
    teams = load_teams(teams_path)
    total = fetch_all(teams)
    if total:
        regenerate_html(SCRIPT_DIR)


def main() -> None:
    """CLI entry point: fetch a single team or refresh all teams."""
    ap = argparse.ArgumentParser(
        description="Fetch a BFV team's full match schedule and write a CSV."
    )
    ap.add_argument(
        "url",
        nargs="?",
        help="BFV team page URL, e.g. https://www.bfv.de/mannschaften/...",
    )
    ap.add_argument(
        "output", nargs="?", help="Output CSV path (default: <slug>_spiele_web.csv)"
    )
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch all teams listed in teams.json and regenerate the overview",
    )
    ap.add_argument(
        "--teams",
        default=None,
        help="Path to teams JSON file (default: teams.json next to this script)",
    )
    args = ap.parse_args()

    if args.refresh:
        refresh(Path(args.teams) if args.teams else SCRIPT_DIR / "teams.json")
        return
    if not args.url:
        ap.error("URL or --refresh is required")

    teams_path = Path(args.teams) if args.teams else SCRIPT_DIR / "teams.json"

    try:
        out_path, n = fetch_one(args.url, teams_path)
    except Exception as exc:
        sys.exit(f"Error fetching data: {exc}")
    if args.output:
        fetched = out_path
        out_path = Path(args.output)
        out_path.write_bytes(fetched.read_bytes())

    print(f"Wrote {n} matches to {out_path}")


if __name__ == "__main__":
    main()
