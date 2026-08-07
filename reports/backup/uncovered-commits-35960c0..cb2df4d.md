# Uncovered Commits Report

**As of:** 2026-08-07  
**Commit range:** `35960c0..cb2df4d`  
**Total commits:** 14

## Summary by Type

| Type | Count | Commits |
|------|-------|---------|
| feat | 4 | 35960c0, 7eab232, 256d656, c52830e |
| refactor | 2 | 3700af8, f738743 |
| test | 1 | b426d00 |
| chore | 7 | 90752fb, 436431c, b2abcdf, 5249bbb, da5c55d, 79ef324, cb2df4d |

## Detailed Commit Log

### `35960c0` feat: show hidden team names on hot days when teams are filtered
- `test/test_visualize_spiele.py` — added tests for hot-day team name display
- `visualize_spiele.py` — render helpers now show team names on hot days when teams are filtered

### `90752fb` chore: add reports/ to .gitignore
- `.gitignore` — added `reports/` directory

### `3700af8` refactor: replace regex HTML parser with html.parser
- `fetch_bfv_spielplan.py` — replaced regex-based HTML parsing with `html.parser.HTMLParser` subclass for more robust parsing

### `7eab232` feat: warn on missing team names and fix PDF font handling
- `visualize_spiele.py` — added warning when team names are missing from CSV; fixed PDF font handling

### `256d656` feat: bundle NotoSans-Regular.ttf for PDF umlaut support
- `fonts/NotoSans-Regular.ttf` — bundled font file for proper umlaut rendering in PDFs

### `b426d00` test: add tests for html.parser, caching, error handling, and warnings
- `test/test_fetch_bfv_spielplan.py` — added tests for HTML parser, cache, HTTP errors
- `test/test_visualize_spiele.py` — added tests for warnings on missing teams

### `b2abcdf` chore: update teams.json configuration
- `teams.json` — updated team configuration

### `436431c` chore: add .bfv_cache/ to .gitignore
- `.gitignore` — added `.bfv_cache/` directory

### `5249bbb` chore: add pyproject.toml, coverage config, and CI workflow
- `.github/workflows/ci.yml` — added CI pipeline with Python and JS test jobs
- `pyproject.toml` — added project metadata, pytest config, coverage config

### `c52830e` feat: add rate limiting, configurable club name, and mypy config
- `config.py` — added `CLUB_NAME` constant
- `fetch_bfv_spielplan.py` — added `BFV_RATE_LIMIT` env var for rate limiting
- `pyproject.toml` — added mypy configuration
- `test/test_fetch_bfv_spielplan.py` — added rate limit test
- `visualize_spiele.py` — club name now configurable, mypy fixes applied

### `f738743` refactor: extract HTML template to external file
- `templates/spielplan.html` — new external HTML template with `$variable` placeholders
- `visualize_spiele.py` — `build_html()` refactored to use `string.Template`

### `da5c55d` chore: add ruff linting and formatting
- `.gitignore` — updated patterns to be directory-scoped (`./spielplan.html`)
- `config.py` — fixed unused import
- `fetch_bfv_spielplan.py` — fixed unused import
- `pyproject.toml` — added ruff dependency and configuration
- `test/test_fetch_bfv_spielplan.py` — fixed unused import
- `test/test_visualize_spiele.py` — fixed unused import, renamed `cell_white` to `_cell_white`
- `visualize_spiele.py` — fixed unused import, formatted with ruff

### `79ef324` ci: use virtual environment and remove test-js job
- `.github/workflows/ci.yml` — create venv, use `.venv/bin/` prefix, removed `test-js` job, fixed `--cov=.`

### `cb2df4d` chore: add build system, consolidate config, and use venv
- `.gitignore` — added `.venv/`
- `pyproject.toml` — added `[build-system]` with setuptools, added `mypy` to dev deps
- `pytest.ini` — deleted (config consolidated in `pyproject.toml`)

## Files Affected

| File | Commit Count |
|------|-------------|
| `.gitignore` | 4 |
| `pyproject.toml` | 4 |
| `visualize_spiele.py` | 4 |
| `fetch_bfv_spielplan.py` | 2 |
| `config.py` | 2 |
| `test/test_fetch_bfv_spielplan.py` | 2 |
| `test/test_visualize_spiele.py` | 2 |
| `.github/workflows/ci.yml` | 2 |
| `teams.json` | 1 |
| `templates/spielplan.html` | 1 |
| `pytest.ini` | 1 |
| `fonts/NotoSans-Regular.ttf` | 1 |

## Coverage Gap

Existing reports cover commits up to `a0a9863` (README update for teams.json).  
**14 commits remain uncovered** from `35960c0` to `cb2df4d`.

Recommended next report range: `35960c0..cb2df4d`
