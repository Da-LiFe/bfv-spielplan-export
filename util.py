"""Shared helpers for the spielplan project.

Small pure functions used by more than one module; constants live in
``config.py``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import TypeVar

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
