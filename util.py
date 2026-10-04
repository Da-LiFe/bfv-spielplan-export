"""Shared helpers for the spielplan project.

Small pure functions used by more than one module; constants live in
``config.py``.
"""

import urllib.parse


def place_text(spielort: str) -> str:
    """Join the pipe-separated parts of a location into one readable line."""
    return ", ".join(part for part in (p.strip() for p in spielort.split("|")) if part)


def maps_url(spielort: str) -> str:
    """Build a Google Maps search URL for a location."""
    q = place_text(spielort)
    if not q:
        return ""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(q)
