"""Shared helpers for the spielplan project.

Small pure functions used by more than one module; constants live in
``config.py``.
"""

from __future__ import annotations

import html as htmllib
import json
import os
import sys
import tempfile
import urllib.parse
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

from config import CSV_DATE_FORMAT, MONTHS_DE, WEEKDAYS_DE

T = TypeVar("T")


def place_text(spielort: str) -> str:
    """Join the pipe-separated parts of a location into one readable line."""
    return ", ".join(part for part in (p.strip() for p in spielort.split("|")) if part)


def maps_url(spielort: str) -> str:
    """Build a Google Maps search URL for a location."""
    q = place_text(spielort)
    if not q:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)


def esc(text: Any) -> str:
    """HTML-escape a string for reportlab paragraphs."""
    return htmllib.escape(str(text), quote=True)


def german_now() -> str:
    """Return the current date/time in German format."""
    now = datetime.now()
    return (
        f"{WEEKDAYS_DE[now.weekday()]}, {now.day}. "
        f"{MONTHS_DE[now.month - 1]} {now.year}, {now:%H:%M} Uhr"
    )


def parse_date(value: Any) -> date | None:
    """Parse an ISO (2026-05-02) or German (02.05.2026) date string.

    Also accepts ``datetime`` and ``date`` objects directly.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    for fmt in ("%Y-%m-%d", CSV_DATE_FORMAT):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_time(value: Any) -> str:
    """Return a zero-padded time string for sorting (e.g. '09:00').

    Accepts ``'9:00'``, ``'09:00'``, ``None`` and other types.
    ``None`` returns ``'99:99'`` so missing times sort last.
    """
    if not value:
        return "99:99"
    s = str(value).strip()
    # Handle 'H:MM' or 'HH:MM' → zero-pad the hour.
    if ":" in s:
        h, m = s.split(":", 1)
        return f"{int(h):02d}:{m}"
    return s


def game_sort_key(game: dict[str, Any] | Any) -> Any:
    """Sort key for a game dict: by date, then time (missing → last)."""
    raw_date = game.get("date")
    if isinstance(raw_date, datetime):
        raw_date = raw_date.date()
    return (raw_date or date.max, parse_time(game.get("time")))


def match_team(candidates: Iterable[str], query: str) -> str | None:
    """Return the first candidate matching *query* (case-insensitive).

    Returns ``None`` when no match is found.
    """
    lowered = query.lower()
    for name in candidates:
        if name.lower() == lowered:
            return name
    return None


def load_json_lenient(
    path: str | os.PathLike[str], default: dict | None = None
) -> dict:
    """Load a JSON file, silently falling back to *default* on any error."""
    if default is None:
        default = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return default


def load_json_strict(path: str | os.PathLike[str], default: dict | None = None) -> dict:
    """Load a JSON file, aborting on invalid content.

    Missing file → ``default`` (or ``{}``). Invalid JSON → ``SystemExit`` with
    a clear message.
    """
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path}: ungültiges JSON – {exc}")


def load_json_list_strict(
    path: str | os.PathLike[str], default: list | None = None
) -> list:
    """Load a JSON file containing an array, aborting on invalid content.

    Missing file → ``default`` (or ``[]``). Invalid JSON → ``SystemExit``.
    """
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path}: ungültiges JSON – {exc}")


def write_json(path: str | os.PathLike[str], data: dict) -> None:
    """Write *data* to *path* atomically (temp file + ``os.replace``)."""
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        os.write(fd, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        os.write(fd, b"\n")
        os.close(fd)
        os.replace(tmp_path, path)
    except BaseException:
        os.close(fd)
        os.unlink(tmp_path)
        raise


def write_json_list(path: str | os.PathLike[str], data: list) -> None:
    """Write a JSON list to *path* atomically (temp file + ``os.replace``)."""
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        os.write(fd, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        os.write(fd, b"\n")
        os.close(fd)
        os.replace(tmp_path, path)
    except BaseException:
        os.close(fd)
        os.unlink(tmp_path)
        raise
