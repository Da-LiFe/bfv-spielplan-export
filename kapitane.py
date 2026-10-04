"""Kapitän (team lead) assignments.

One kid per team acts as "Kapitän" for the whole calendar week
(Monday–Sunday) in which the game takes place. The team rosters live in
``roster.json``, the week→kid assignments in ``kapitane.json``. Weeks without
an explicit captain are filled round-robin so the duty is distributed fairly
across the team's roster.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from config import SCRIPT_DIR, WD
from util import load_json_lenient, match_team

CONFIG_NAME = "kapitane.json"
DEFAULT_CONFIG_PATH = SCRIPT_DIR / CONFIG_NAME
ROSTER_NAME = "roster.json"
DEFAULT_ROSTER_PATH = SCRIPT_DIR / ROSTER_NAME


@dataclass
class Kid:
    """A roster entry with an optional shirt number."""

    name: str
    number: int | None = None


def empty_config() -> dict[str, Any]:
    """Return an empty, valid merged teams/assignments structure."""
    return {"teams": {}, "assignments": {}}


def duty_week(game_date: date) -> str:
    """Return the ISO week key (YYYY-WW) the game takes place in."""
    year, week, _ = game_date.isocalendar()
    return f"{year}-{week:02d}"


def week_range(week_key: str) -> str:
    """Render a week key as 'Mo 21.09. – So 27.09.' ('' when malformed)."""
    parts = week_key.split("-")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return ""
    try:
        year, week = int(parts[0]), int(parts[1])
        monday = date.fromisocalendar(year, week, 1)
        sunday = monday + timedelta(days=6)
    except ValueError:
        return ""
    return (
        f"{WD[monday.weekday()]} {monday.strftime('%d.%m.')} – "
        f"{WD[sunday.weekday()]} {sunday.strftime('%d.%m.')}"
    )


def captains_for(cfg: dict[str, Any], names: set[str]) -> dict[str, str]:
    """Return week -> kid mapping merging all name variants of a team.

    *names* should include every alias / original BFV name / lineup name that
    refers to the same team.  Lookups are case-insensitive via ``match_team``.
    """
    merged: dict[str, str] = {}
    assignments = cfg.get("assignments", {})
    for name in names:
        canonical = match_team(assignments.keys(), name)
        if canonical:
            week_assignments = assignments.get(canonical, {})
            merged.update(week_assignments)
    return merged


def _parse_teams(raw_teams: dict) -> dict[str, list[Kid]]:
    """Normalise raw teams dict into team -> [Kid] (both old and new format)."""
    result: dict[str, list[Kid]] = {}
    for team, kids in raw_teams.items():
        if isinstance(kids, list):
            # Old flat format: ["Lena", "Max"]
            result[str(team)] = [Kid(name=str(k), number=None) for k in kids if k]
        elif isinstance(kids, dict):
            # New format: {"kids": [{"name": "Lena", "number": 1}]}
            kid_list = kids.get("kids", [])
            if isinstance(kid_list, list):
                result[str(team)] = [
                    Kid(name=str(k["name"]), number=k.get("number"))
                    for k in kid_list
                    if isinstance(k, dict) and k.get("name")
                ]
    return result


def load_roster_entries(path: Path | None = None) -> dict[str, list[Kid]]:
    """Load ``roster.json`` and return team -> [Kid] entries.

    Supports both the old flat format (``["Lena", "Max"]``) and the new
    structured format (``{"kids": [{"name": "Lena", "number": 1}]}``).
    """
    roster_path = path or DEFAULT_ROSTER_PATH
    data = load_json_lenient(roster_path, {})
    raw_teams = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(raw_teams, dict):
        return {}
    return _parse_teams(raw_teams)


def load_roster(path: Path | None = None) -> dict[str, list[str]]:
    """Load ``roster.json`` as a mapping of team -> kid names.

    Convenience wrapper around ``load_roster_entries`` that returns only names.
    """
    return {
        team: [k.name for k in kids] for team, kids in load_roster_entries(path).items()
    }


def load_roster_with_numbers(
    path: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load roster entries with optional shirt numbers.

    Returns ``{"Team": [{"name": "Lena", "number": 1}, ...]}``.
    For the old flat format entries without numbers are returned as
    ``{"name": "Lena", "number": None}``.
    """
    return {
        team: [{"name": k.name, "number": k.number} for k in kids]
        for team, kids in load_roster_entries(path).items()
    }


def save_roster(roster: dict[str, list[str]], path: Path | None = None) -> None:
    """Write the team rosters to ``roster.json`` (new structured format)."""
    roster_path = path or DEFAULT_ROSTER_PATH
    teams: dict[str, Any] = {}
    for team, kids in roster.items():
        teams[str(team)] = {"kids": [{"name": str(k)} for k in kids if k]}
    roster_path.write_text(
        json.dumps({"teams": teams}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and normalize ``kapitane.json`` (the assignments only)."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return {"assignments": {}}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(
            f"{cfg_path.name}: ungültiges JSON – keine Zuteilungen geladen.",
            file=sys.stderr,
        )
        return {"assignments": {}}
    return normalize_config(data)


def normalize_config(data: Any) -> dict[str, Any]:
    """Coerce arbitrary JSON into the expected assignments structure."""
    assignments: dict[str, Any] = {}
    if isinstance(data, dict):
        raw_assignments = data.get("assignments")
        if isinstance(raw_assignments, dict):
            for team, weeks in raw_assignments.items():
                if isinstance(weeks, dict):
                    assignments[str(team)] = {
                        str(w): str(k) for w, k in weeks.items() if k
                    }
    return {"assignments": assignments}


def load_all(
    assign_path: Path | None = None, roster_path: Path | None = None
) -> dict[str, Any]:
    """Merge ``roster.json`` (``teams``) and ``kapitane.json`` (``assignments``)."""
    return {
        "teams": load_roster(roster_path),
        "assignments": load_config(assign_path)["assignments"],
    }


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    """Write the assignments from ``cfg`` to ``kapitane.json``."""
    cfg_path = path or DEFAULT_CONFIG_PATH
    cfg_path.write_text(
        json.dumps(
            {"assignments": cfg.get("assignments", {})}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )


def assign_round_robin(
    weeks: list[str], roster: list[str], existing: dict[str, str]
) -> dict[str, str]:
    """Fill the weeks missing from ``existing`` with the roster's fairest kid.

    Each missing week goes to the kid with the fewest assignments so far
    (ties broken by roster order), so the result is balanced by construction.
    Only counts assignments for the weeks being processed.
    """
    counts = {kid: 0 for kid in roster}
    week_set = set(weeks)
    for wk, kid in existing.items():
        if wk in week_set and kid in counts:
            counts[kid] += 1
    result = dict(existing)
    for week in sorted(set(weeks)):
        if week in result:
            continue
        kid = min(roster, key=lambda k: counts[k])
        result[week] = kid
        counts[kid] += 1
    return result


def ensure_assignments(
    cfg: dict[str, Any], teams_weeks: dict[str, list[str]]
) -> list[str]:
    """Fill every team's missing duty weeks; return warnings as strings.

    ``teams_weeks`` maps a team name to the sorted week keys that need a
    captain (one week per upcoming game week).
    """
    warnings: list[str] = []
    for team, weeks in teams_weeks.items():
        weeks = sorted(set(weeks))
        if not weeks:
            continue
        roster = cfg["teams"].get(team, [])
        existing = cfg["assignments"].get(team, {})
        if not roster:
            warnings.append(
                f"Kein Kader für '{team}' in {ROSTER_NAME} – keine Auto-Zuteilung."
            )
            continue
        cfg["assignments"][team] = assign_round_robin(weeks, roster, existing)
    return warnings


@dataclass
class CheckResult:
    """Human-readable result of a fairness check."""

    lines: list[str] = field(default_factory=list)
    problems: int = 0

    @property
    def balanced(self) -> bool:
        return self.problems == 0


def check_distribution(
    cfg: dict[str, Any], teams_weeks: dict[str, list[str]]
) -> CheckResult:
    """Count each kid's duty weeks and judge whether the load is balanced.

    Only weeks that actually have an upcoming game count toward the totals.
    """
    result = CheckResult()
    lines = result.lines
    lines.append("Kapitän-Verteilung")
    lines.append("===================")
    reported = 0
    teams = sorted(set(teams_weeks) | set(cfg["assignments"]))
    for team in teams:
        weeks = sorted(set(teams_weeks.get(team, [])))
        if not weeks and not cfg["assignments"].get(team):
            continue
        reported += 1
        roster = cfg["teams"].get(team, [])
        assignments = cfg["assignments"].get(team, {})
        counts: Counter[str] = Counter()
        for kid in roster:
            counts[kid] = 0
        missing: list[str] = []
        unknown: list[str] = []
        for wk in weeks:
            kid = assignments.get(wk, "")
            if not kid:
                missing.append(wk)
                continue
            if kid in counts:
                counts[kid] += 1
            else:
                unknown.append(kid)

        span = ""
        if weeks:
            span_range = f"{weeks[0]}–{weeks[-1]}" if len(weeks) > 1 else weeks[0]
            span = f" – Woche {span_range}"
        lines.append(f"{team} ({len(weeks)} Woche(n){span})")
        for kid, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {kid:<20} {count}")
        if not roster:
            lines.append("  PROBLEM: kein Kader hinterlegt")
            result.problems += 1
        if missing:
            lines.append(f"  PROBLEM: keine Zuteilung für {', '.join(missing)}")
            result.problems += 1
        if unknown:
            lines.append(f"  PROBLEM: nicht im Kader ({', '.join(unknown)})")
            result.problems += 1
        delta = max(counts.values()) - min(counts.values()) if counts else 0
        if counts and not missing and not unknown and roster and delta <= 1:
            lines.append(f"  Verteilung: gleichmäßig (Δ = {delta})")
        elif counts:
            lines.append(f"  Verteilung: ungleichmäßig (Δ = {delta})")
            result.problems += 1
        lines.append("")

    if not reported:
        lines.append("Keine Kapitän-Daten vorhanden.")
        if any(teams_weeks.values()):
            result.problems += 1
    return result


def teams_duty_weeks(
    games: list[Any], sources: list[Any], today: date | None = None
) -> dict[str, list[str]]:
    """Map each club team to the sorted duty-week keys of its upcoming games."""
    today = today or datetime.now().date()
    result: dict[str, list[str]] = {}
    for src in sources:
        team = src["team"]
        weeks: set[str] = set()
        for g in games:
            d = g["date"]
            if hasattr(d, "date"):
                d = d.date()
            if (g["heim"] == team or g["gast"] == team) and d >= today:
                weeks.add(duty_week(d))
        if weeks:
            result[team] = sorted(weeks)
    return result


def run_check(result: CheckResult, path: Path | None = None) -> None:
    """Print a check report and exit non-zero when the distribution is off."""
    for line in result.lines:
        print(line)
    if not result.balanced:
        cfg_path = path or DEFAULT_CONFIG_PATH
        print(f"\nNicht gleichmäßig – bitte {cfg_path} korrigieren.")
        sys.exit(1)
