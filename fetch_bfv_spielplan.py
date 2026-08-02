from __future__ import annotations

import argparse
import csv
import html as htmllib
import re
import sys
import urllib.request
from pathlib import Path
from typing import TypedDict

from config import SCRIPT_DIR

BASE = "https://www.bfv.de/partial/mannschaftsprofil/spielplan/{}/alle"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
SIZE = 100
MAX_ITER = 10
ENTRY_RE = re.compile(
    r'<div class="bfv-spieltag-eintrag">(.*?)(?=<div class="bfv-spieltag-matchups__separator|$)',
    re.S,
)


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


def fetch(url: str) -> str:
    """Fetch a URL and return its text content."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_entries(html_text: str) -> list[Entry]:
    """Parse match entries from BFV HTML markup."""
    rows: list[Entry] = []
    for e in ENTRY_RE.findall(html_text):
        region = re.search(r'bfv-spieltag-eintrag__region">(.*?)</div>', e, re.S)
        link = re.search(r'bfv-spieltag-eintrag__match-link"\s+href="([^"]+)"', e)
        dtime = re.search(
            r"bfv-matchday-date-time\">.*?<span>\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})\s*/([0-9:.]+)\s*Uhr\s*</span>",
            e,
            re.S,
        )
        t0 = re.search(r"bfv-matchdata-result__team-name--team0[^>]*>(.*?)</div>", e, re.S)
        t1 = re.search(r"bfv-matchdata-result__team-name--team1[^>]*>(.*?)</div>", e, re.S)
        loc = re.search(r'bfv-spieltag-eintrag__location">(.*?)</div>', e, re.S)
        rows.append(
            Entry(
                Wettbewerb=clean(region.group(1)) if region else "",
                Datum=dtime.group(1) if dtime else "",
                Uhrzeit=dtime.group(2) if dtime else "",
                Heim=clean(t0.group(1)) if t0 else "",
                Gast=clean(t1.group(1)) if t1 else "",
                Spielort=clean(loc.group(1)) if loc else "",
                Link=link.group(1).strip() if link else "",
                Quelle="",
            )
        )
    return rows


def fetch_all_matches(team_id: str) -> list[Entry]:
    """Fetch all match entries for a team, handling pagination."""
    all_rows: list[Entry] = []
    from_ = 0
    for _ in range(MAX_ITER):
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


def fetch_one(url):
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
        w = csv.DictWriter(f, fieldnames=["Wettbewerb", "Datum", "Uhrzeit", "Heim", "Gast", "Spielort", "Link", "Quelle"])
        w.writeheader()
        w.writerows(rows)
    return out_path, len(rows)


def refresh(teams_path):
    if not teams_path.exists():
        sys.exit(f"Error: {teams_path} not found.")
    urls = []
    for line in teams_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    if not urls:
        sys.exit(f"Error: no team URLs found in {teams_path}.")
    return urls


def fetch_all(urls: list[str]) -> int:
    """Fetch every team's schedule, print progress, return total match count."""
    total = 0
    for url in urls:
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

        subprocess.run([sys.executable, str(visualize)], check=True)


def refresh(teams_path: Path) -> None:
    """Re-fetch all teams from a teams file and regenerate the overview."""
    urls = load_teams(teams_path)
    total = fetch_all(urls)
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
    ap.add_argument("output", nargs="?", help="Output CSV path (default: <slug>_spiele_web.csv)")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch all teams listed in teams.txt and regenerate the overview",
    )
    ap.add_argument(
        "--teams",
        default=None,
        help="Path to teams file (default: teams.txt next to this script)",
    )
    args = ap.parse_args()

    if args.refresh:
        refresh(Path(args.teams) if args.teams else SCRIPT_DIR / "teams.txt")
        return
    if not args.url:
        ap.error("URL or --refresh is required")

    try:
        out_path, n = fetch_one(args.url)
    except Exception as exc:
        sys.exit(f"Error fetching data: {exc}")
    if args.output:
        fetched = out_path
        out_path = Path(args.output)
        out_path.write_bytes(fetched.read_bytes())

    print(f"Wrote {n} matches to {out_path}")


if __name__ == "__main__":
    main()
