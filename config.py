"""Shared constants for the spielplan project."""

from pathlib import Path

SCRIPT_DIR: Path = Path(__file__).resolve().parent

WD: list[str] = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WEEKDAYS_DE: list[str] = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]
MONTHS_DE: list[str] = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]
PALETTE: list[str] = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#9edae5", "#c49c94", "#ff9896", "#ffbb78", "#aec7e8",
]
CSV_DATE_FORMAT: str = "%d.%m.%Y"

CLUB_MARKERS: set[str] = {
    "tsv gilching",
    "tsv gilching/argelsried",
    "tsv gilching-argelsried",
    "tsv gilching/a",
}
