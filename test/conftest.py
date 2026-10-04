import importlib

import pytest

# Modules that resolve data/output files relative to their ``SCRIPT_DIR``.
# ``pdf_common`` is left out on purpose: it loads the bundled fonts.
DATA_MODULES = (
    "anwesenheit",
    "aufstellung",
    "fetch_bfv_spielplan",
    "games",
    "kapitane",
    "pdf_overview",
    "pdf_team",
)


@pytest.fixture
def script_dir(tmp_path, monkeypatch):
    """Point every module's ``SCRIPT_DIR`` at ``tmp_path`` and return it."""
    for name in DATA_MODULES:
        monkeypatch.setattr(importlib.import_module(name), "SCRIPT_DIR", tmp_path)
    return tmp_path
