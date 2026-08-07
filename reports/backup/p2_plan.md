# P2 Improvement Plan

## Overview

Seven P2 improvements identified from codebase analysis. Ordered by risk (lowest to medium).

---

## Item 4: Add `pyproject.toml` *(Negligible Risk)*

**Objective:** Centralize project metadata, dependencies, and tool configuration.

**Files:** New `pyproject.toml`

**Steps:**
1. Create `pyproject.toml` with:
   - `[project]`: name, version, description, requires-python, dependencies (`reportlab`, `pytest`)
   - `[tool.pytest.ini_options]`: testpaths, pythonpath
   - `[project.optional-dependencies]`: dev = ["pytest"]
2. Add `[tool.mypy]` stub section (Item 3 will expand this)
3. No code changes required

**Tests:** None needed (purely declarative)

**Risk:** Negligible — additive only, no behavioral changes

**Rollback:** Delete `pyproject.toml`

---

## Item 7: Add `pytest-cov` coverage reporting *(Negligible Risk)*

**Objective:** Enable coverage metrics alongside existing tests.

**Files:** `pyproject.toml` (expand `[tool.pytest]` section)

**Steps:**
1. Add `pytest-cov` to `[project.optional-dependencies]` dev
2. Add `[tool.coverage.run]` config: source = `["."]`, omit = `["test/*", "*/__pycache__/*"]`
3. Add `[tool.coverage.report]` config: `fail_under = 0` (start permissive, raise gradually)
4. Document `pytest --cov` in existing test instructions

**Tests:** None needed

**Risk:** Negligible — additive only, coverage is opt-in

**Rollback:** Remove coverage config from `pyproject.toml`

---

## Item 6: Add rate limiting between paginated requests *(Low Risk)*

**Objective:** Add configurable delay between paginated BFV requests.

**Files:** `fetch_bfv_spielplan.py`

**Steps:**
1. Add `BFV_RATE_LIMIT` env var check in `fetch_all_matches()`
2. Insert `time.sleep(float(os.environ.get("BFV_RATE_LIMIT", "0.0")))` between pagination loops
3. Default = `0.0` (preserve existing behavior)
4. Add test `test_fetch_all_matches_rate_limit()` that mocks `time.sleep` and verifies it's called

**Tests:**
- `test_fetch_all_matches_rate_limit()` — verifies `time.sleep` is called with correct interval
- `test_fetch_all_matches_no_rate_limit()` — verifies default behavior (no sleep)

**Risk:** Low — backward compatible, configurable, no logic changes

**Rollback:** Revert single function modification

---

## Item 5: Make club name configurable *(Low Risk)*

**Objective:** Replace hardcoded "TSV Gilching/Argelsried" with configurable value.

**Files:** `config.py`, `visualize_spiele.py`, `teams.json` (optional)

**Steps:**
1. Add `CLUB_NAME: str = "TSV Gilching/Argelsried"` to `config.py`
2. In `visualize_spiele.py`:
   - Replace `'Spielplan – TSV Gilching/Argelsried'` in HTML title with `f"Spielplan – {CLUB_NAME}"`
   - Replace `'Spielplan – TSV Gilching/Argelsried'` in PDF title with `f"Spielplan – {CLUB_NAME}"`
   - Replace `'Spielplan TSV Gilching/Argelsried'` in `.ics` PRODID with `f"Spielplan {CLUB_NAME}"`
3. No changes to data logic, only string literals

**Tests:**
- `test_build_html_uses_configurable_club_name()` — verify HTML title contains `CLUB_NAME`
- `test_build_pdf_uses_configurable_club_name()` — verify PDF title contains `CLUB_NAME`
- `test_ics_uses_configurable_club_name()` — verify `.ics` PRODID contains `CLUB_NAME`

**Risk:** Low — default preserves existing behavior, only string substitutions

**Rollback:** Revert 3 string replacements + 1 config addition

---

## Item 2: Add CI pipeline (GitHub Actions) *(Low Risk)*

**Objective:** Automate test execution on every push/PR.

**Files:** New `.github/workflows/ci.yml`

**Steps:**
1. Create `.github/workflows/ci.yml` with:
   - Trigger: `push`, `pull_request` on `main`
   - Jobs: `test-python` (Python 3.12+) and `test-js` (Node.js 20+)
   - Python job: `pip install reportlab pytest`, `pytest test/`
   - JS job: `npm install`, `npm test` (or existing JS harness)
2. Add `pytest-cov` to Python dependencies in CI
3. Optionally add `pytest --cov-fail-under=90` once coverage baseline is established

**Tests:** None needed (CI is self-validating via test results)

**Risk:** Low — purely additive, can be disabled without impact

**Rollback:** Delete `.github/workflows/ci.yml`

---

## Item 3: Add static type checking with mypy *(Low Risk)*

**Objective:** Catch latent type bugs via static analysis.

**Files:** `pyproject.toml` (expand `[tool.mypy]`), `fetch_bfv_spielplan.py` (minor fixes)

**Steps:**
1. Add `[tool.mypy]` to `pyproject.toml`:
   - `python_version = "3.12"`
   - `strict = false` (start relaxed)
   - `warn_untyped_defs = true`
   - `disallow_any_generics = false`
   - `follow_imports = "skip"` (start isolated)
2. Run `mypy fetch_bfv_spielplan.py visualize_spiele.py` to identify issues
3. Fix any `TypedDict` dynamic key access warnings (e.g., `_clean_entry()` uses `entry[key]` where `key` is a string variable)
4. Add `# type: ignore[typeddict-item]` where needed for legitimate dynamic access
5. Document `mypy` in existing test instructions

**Tests:** None needed (mypy is self-validating)

**Risk:** Low — can be run incrementally, false positives suppressed with `# type: ignore`

**Rollback:** Remove `[tool.mypy]` section + revert any `# type: ignore` additions

---

## Item 1: Extract HTML/CSS/JS template to external file *(Medium Risk)*

**Objective:** Move ~288-line HTML string from `visualize_spiele.py` to `templates/spielplan.html`.

**Files:** New `templates/spielplan.html`, modified `visualize_spiele.py`

**Steps:**
1. Create `templates/` directory in project root
2. Extract the HTML string from `build_html()` to `templates/spielplan.html`
3. Replace Python f-string placeholders with `{placeholder}` markers:
   - `{total}` → `{total}`
   - `{days}` → `{sections}`
   - `{team_checks_html}` → `{team_checks}`
   - `{games_js}` → `{spiele_js}`
   - `{aliases_js}` → `{aliases_js}`
   - `{footer_html}` → `{footer_html}`
   - `{CLUB_NAME}` → `{club_name}` (links to Item 5)
4. In `visualize_spiele.py`:
   - Add `_load_template()` function: reads `templates/spielplan.html`, returns string
   - Replace inline HTML in `build_html()` with `template.format(...)` call
5. Update tests:
   - `test_build_html_uses_template()` — verify template is loaded and rendered correctly
   - Snapshot test: compare rendered HTML output before/after extraction

**Tests:**
- `test_template_loads_successfully()` — verify `templates/spielplan.html` exists and is readable
- `test_build_html_output_unchanged()` — snapshot test comparing old vs new output
- All existing `test_build_html*` tests must still pass

**Risk:** Medium — template loading adds a new dependency path (file missing, encoding); must preserve exact output to not break tests; JS logic is tightly coupled to Python-generated data structures

**Mitigation:**
- Use plain `{placeholder}` markers (no Jinja dependency)
- Snapshot-test the rendered output to catch regressions
- Keep template as UTF-8 with explicit encoding in `read_text()`

**Rollback:** Revert template extraction + restore inline HTML string

---

## Execution Order & Dependencies

```
Phase 1 (Foundation, no code changes):
  4. pyproject.toml → 7. coverage reporting → 2. CI pipeline

Phase 2 (Low-risk code changes):
  6. rate limiting → 5. configurable club name → 3. mypy

Phase 3 (Medium-risk refactoring):
  1. extract HTML template (depends on 5 being complete for club_name variable)
```

**Total estimated effort:** ~2-3 hours for all 7 items

**Key dependency:** Item 1 (template extraction) should be done last because it touches the most code and requires the most test validation.
