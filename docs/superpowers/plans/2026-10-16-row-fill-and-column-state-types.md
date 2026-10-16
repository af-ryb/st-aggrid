# Group-row fill and ColumnState types (2.7.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship fork 2.7.0 with a declarative group-row fill (`context["stRowFill"]`, replacing the consumer's `js_cohort_row_style`) and honest `ColumnState` / `columns_state` types that clear web_app's three `ty` diagnostics in `grid_state.py`.

**Architecture:** Part B is Python-only: `ColumnState` becomes a `TypedDict` with a required `colId`, and `AgGrid(columns_state=…)` / `AgGridResult.column_state` use it. Part A adds a validator (`row_fill.py`) and a builder method on the Python side, a pure matcher (`colorScales/rowFill.ts`) and a `getRowStyle` installer wired into `parseGridOptions` on the frontend; the existing post-`updateGridOptions` `redrawRows()` carries live changes.

**Tech Stack:** Python 3.13, pytest + Playwright (e2e), TypeScript/React, AG-Grid 36.1.0, Vite, Yarn 4 via corepack, uv.

**Spec:** `docs/superpowers/specs/2026-10-16-row-fill-and-column-state-types-design.md`

## Global Constraints

- Work on branch `feature/row-fill-column-state-types`; never commit to `main`.
- Version `2.7.0` in **both** `pyproject.toml` and `st_aggrid/pyproject.toml`.
- `requires-python = ">=3.13"`; `ColumnState` uses `typing.Required`.
- Context key literal: `"stRowFill"`; rule keys exactly `("key", "color")`.
- Predicate: `node.group && !node.footer && node.key === rule.key`; paint `{ backgroundColor: rule.color }`, colour string untouched.
- Caller `getRowStyle` + non-empty `stRowFill`: Python `ValueError`; frontend keeps the caller's function and `console.warn`s; never chains.
- `colorScales/rowFill.ts` imports nothing (pure module rule, CLAUDE.md).
- Frontend: `corepack yarn …` only (bare `yarn` is not on PATH); a rebuild shows delete + add under `st_aggrid/frontend/build/`.
- E2E reads rows by `row-index` (`grid_dom.read_rows` / `cell_backgrounds`), never DOM order.
- Commit messages imperative; end with the session's Co-Authored-By / Claude-Session lines.

## Review Focus

- A grouped column holding numbers (`node.key` is the string `"1"`): a rule `key="1"` must match; Python must reject `key=1` → Task 2 unit test + Task 3 check case.
- Pivot mode (the consumer's real mode): group rows of a pivoting grid must paint the same → Task 4 e2e grid 1.
- A collapsed group: the group row is still the group row and stays painted → Task 4 e2e.
- Two rules on different levels with different colours: each row gets its own rule's colour, first-match order irrelevant because keys are unique → Task 3 check + Task 4 e2e.
- A rerun that removes or recolours the rule must leave no stale inline background on rows already painted → Task 4 e2e removal and recolour tests.

---

### Task 1: `ColumnState` TypedDict and Python 3.13 floor (spec Part B)

**Files:**
- Modify: `st_aggrid/column_state.py:41-50` (imports, alias → class, `__all__`)
- Modify: `st_aggrid/aggrid.py:183` (annotation), `:248-253` (docstring: "list of ``ColumnState``")
- Modify: `st_aggrid/result.py:56` (return type)
- Modify: `st_aggrid/__init__.py:31` (export `ColumnState`)
- Modify: `pyproject.toml:6`, then `uv lock`
- Test: `test/unit/test_column_state.py`, `test/unit/test_public_exports.py`

**Interfaces:**
- Produces: `st_aggrid.ColumnState` — `TypedDict(total=False)` with `colId: Required[str]`, `hide: Optional[bool]`, `width: float`, `flex: Optional[float]`, `pinned: Optional[Literal["left","right"]]`, `sort: Optional[Literal["asc","desc"]]`, `sortIndex: Optional[int]`, `aggFunc: Optional[str]`, `rowGroup: Optional[bool]`, `rowGroupIndex: Optional[int]`, `pivot: Optional[bool]`, `pivotIndex: Optional[int]`. `AgGrid(columns_state: Optional[List[ColumnState]])`, `AgGridResult.column_state -> Optional[List[ColumnState]]`.

- [ ] **Step 1: Write the failing tests**

In `test/unit/test_column_state.py`:
```python
from st_aggrid.column_state import ColumnState

def test_column_state_requires_only_col_id():
    assert ColumnState.__required_keys__ == frozenset({"colId"})
    assert ColumnState.__optional_keys__ == frozenset({
        "hide", "width", "flex", "pinned", "sort", "sortIndex", "aggFunc",
        "rowGroup", "rowGroupIndex", "pivot", "pivotIndex"})
```
In `test/unit/test_public_exports.py`:
```python
def test_column_state_type_is_exported():
    from st_aggrid import ColumnState
    from st_aggrid.column_state import ColumnState as Inner
    assert ColumnState is Inner
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest test/unit/test_column_state.py test/unit/test_public_exports.py -v` → `AttributeError: … __required_keys__` / `ImportError`.

- [ ] **Step 3: Implement** the class (docstring: "One entry of AG-Grid's ``getColumnState()`` / ``applyColumnState()``. ``aggFunc`` is a name: a function cannot cross the component boundary."), the three annotations, the export, `requires-python = ">=3.13"`, then `uv lock` (expect `uv.lock:3` to read `>=3.13`).

- [ ] **Step 4: Run unit suite** — `uv run pytest -m "not e2e"` → all pass.

- [ ] **Step 5: Verify against the consumer** (read-only on web_app):
```bash
S=$(mktemp -d) && cp -r st_aggrid "$S/" && rm -rf "$S/st_aggrid/frontend"
cd ~/repo/hitapps_analytics && .venv/bin/ty check --output-format concise --extra-search-path "$S" web_app/src/bi_core/charts/grid_state.py
```
Expected: `All checks passed!`. Then the same over `web_app` → total exactly 3 lower than without `--extra-search-path`.

- [ ] **Step 6: Commit** — `Type ColumnState as a TypedDict and require Python 3.13`.

---

### Task 2: `row_fill.py` validator, builder method, `AgGrid()` hook

**Files:**
- Create: `st_aggrid/row_fill.py`
- Modify: `st_aggrid/grid_options_builder.py` (new method after `configure_color_scale`, `:235`)
- Modify: `st_aggrid/aggrid.py:467` (call `validate_row_fill(grid_options)` after `validate_color_scale_columns`)
- Modify: `st_aggrid/__init__.py` (export `ROW_FILL_CONTEXT_KEY`, `validate_row_fill`)
- Test: create `test/unit/test_row_fill_validation.py`; extend `test/unit/test_grid_options_builder.py`, `test/unit/test_public_exports.py`

**Interfaces:**
- Produces: `ROW_FILL_CONTEXT_KEY = "stRowFill"`, `ROW_FILL_RULE_KEYS = ("key", "color")`, `validate_row_fill(grid_options: Optional[dict]) -> None` (raises `ValueError`); `GridOptionsBuilder.configure_row_fill(self, key: str, color: str) -> None`.

- [ ] **Step 1: Write the failing tests** in `test_row_fill_validation.py`, one test per row, helper `opts(rules, **extra) -> {"columnDefs": [], "context": {"stRowFill": rules}, **extra}`:

| test | input | expect |
| --- | --- | --- |
| `test_absent_and_empty_are_valid` | `None`, `{}`, `opts([])`, `opts([], getRowStyle="f")` | no raise |
| `test_valid_rule` | `opts([{"key": "cohort_1", "color": "var(--x)"}])` | no raise |
| `test_empty_string_key_is_valid` | key `""` | no raise |
| `test_not_a_list` | `opts({"key": "a", "color": "red"})` | `ValueError`, match `"stRowFill"` |
| `test_rule_not_a_dict` | `opts(["a"])` | match `r"\[0\]"` |
| `test_unknown_rule_key` | `{"key":"a","color":"red","field":"x"}` | match `"field"` |
| `test_missing_key_or_color` | each one missing | `ValueError` |
| `test_non_string_key` | `key=1`, `key=None` | match `"key"` |
| `test_blank_color` | `color=""`, `"  "`, `None` | match `"color"` |
| `test_duplicate_key` | two rules `key="a"` | match `r"\[1\]"` |
| `test_conflict_with_get_row_style` | valid rule + `getRowStyle="f"` | match `"getRowStyle"` |
| `test_aggrid_runs_the_validator` | stub the component with `monkeypatch.setattr("st_aggrid.aggrid.get_aggrid_component", …)` as `test_aggrid_rollup_payload.py:23` does; `AgGrid(grid_options=opts([{"key":1,"color":"red"}]))` | `ValueError` |

In `test_grid_options_builder.py`: `configure_row_fill("a","red")` twice with `"a"` then `("b","blue")` → `context["stRowFill"] == [{"key":"a","color":<second colour>}, {"key":"b","color":"blue"}]`, and an existing `context["stColorScale"]` survives. In `test_public_exports.py`: `ROW_FILL_CONTEXT_KEY == "stRowFill"`, `validate_row_fill` importable from root.

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest test/unit/test_row_fill_validation.py test/unit/test_grid_options_builder.py test/unit/test_public_exports.py -v` → `ModuleNotFoundError: st_aggrid.row_fill`.

- [ ] **Step 3: Implement.** `row_fill.py` module docstring in `color_scale.py`'s style (why it exists: a rule that silently paints nothing; frontend repeats the sanitise as a guard). Error messages name `gridOptions context['stRowFill'][i]`. Builder copies `context` (`dict(self._grid_options.get("context") or {})`) and the list, replaces a same-key rule in place, otherwise appends; no validation.

- [ ] **Step 4: Run** `uv run pytest -m "not e2e"` → all pass.

- [ ] **Step 5: Commit** — `Validate stRowFill declarations and add configure_row_fill`.

---

### Task 3: Pure matcher `colorScales/rowFill.ts`

**Files:**
- Create: `st_aggrid/frontend/src/colorScales/rowFill.ts`
- Create: `st_aggrid/frontend/src/colorScales/__checks__/rowFill.check.ts`

**Interfaces:**
- Produces: `export const ST_ROW_FILL = "stRowFill"`; `export type RowFillRule = { key: string; color: string }`; `export function readRowFillRules(context: unknown): RowFillRule[]` (non-array / junk → dropped, blank colour dropped, first rule per key wins, never throws); `export function rowFillFor(rules: RowFillRule[], node: { group?: boolean; footer?: boolean; key?: string | null } | null | undefined): string | null`.

- [ ] **Step 1: Write the check** (header comment as in `overrides.check.ts`, `node:assert/strict`, import from `"../rowFill.ts"`). Assertions:
  - `readRowFillRules` of `undefined`, `null`, `7`, `{}`, `{stRowFill: "x"}`, `{stRowFill: {}}` → `[]`.
  - `{stRowFill: [{key:"a",color:"red"}, {key:"a",color:"blue"}, {key:2,color:"x"}, {key:"b",color:"  "}, null, {key:"",color:"green"}]}` → `[{key:"a",color:"red"},{key:"",color:"green"}]`.
  - rules `[{key:"cohort_1",color:"C"},{key:"1",color:"N"},{key:"US",color:"U"}]`:
    `{group:true,key:"cohort_1"}` → `"C"`; `{group:true,footer:true,key:"cohort_1"}` → `null`; `{group:false,key:"cohort_1"}` → `null`; `{group:true,key:null}` (grand total) → `null`; `{group:true,key:"1"}` → `"N"`; `{group:true,key:"US"}` → `"U"`; `{group:true,key:"cohort_2"}` → `null`; `undefined` → `null`.

- [ ] **Step 2: Run, expect FAIL** — `node st_aggrid/frontend/src/colorScales/__checks__/rowFill.check.ts` → `ERR_MODULE_NOT_FOUND`.

- [ ] **Step 3: Implement** both functions; no imports.

- [ ] **Step 4: Run** the check → exits 0, no output; also run the three existing checks in that folder → exit 0.

- [ ] **Step 5: Commit** — `Add the pure group-row fill matcher`.

---

### Task 4: Install `getRowStyle`, rebuild, e2e

**Files:**
- Modify: `st_aggrid/frontend/src/colorScales/index.ts` (append `stRowFillStyle`, `registerRowFill`)
- Modify: `st_aggrid/frontend/src/utils/parsers.ts:67` (call `registerRowFill(gridOptions, data.debug === true)` right after `registerColorScales`)
- Rebuild: `st_aggrid/frontend/build/*`
- Create: `test/grid_row_fill.py`, `test/test_grid_row_fill.py`

**Interfaces:**
- Consumes: Task 3's `readRowFillRules`, `rowFillFor`.
- Produces: `stRowFillStyle(params: RowClassParams): RowStyle | undefined` (reads rules from `params.context` each call); `registerRowFill(gridOptions: GridOptions, debug?: boolean): GridOptions` — rules empty → untouched; caller `getRowStyle` present → keep it, `console.warn("[st_aggrid] getRowStyle was supplied, so the stRowFill declaration is ignored.")`; otherwise set `gridOptions.getRowStyle = stRowFillStyle`.

- [ ] **Step 1: Write the app** `test/grid_row_fill.py` (docstring lists grids; "grids keep their indices"). Data: 2 regions (`EU`, `US`) × 3 countries, a numeric `bucket` column (`1`/`2`), metric `value`. `st.markdown("<style>:root { --st-aggrid-test-row: rgb(11, 12, 13); }</style>")`. Common options as `grid_color_scale.py` (`suppressRowVirtualisation`, `suppressColumnVirtualisation`, `animateRows: False`), `groupDefaultExpanded: -1`, `groupTotalRow: "bottom"`, `grandTotalRow: "bottom"`, `enable_enterprise_modules=True`, `getRowId` set.
  - Grid 0 — row-grouped `region` → `bucket`; rules via `GridOptionsBuilder.configure_row_fill`: `("EU", "var(--st-aggrid-test-row)")`, `("2", "rgb(21, 22, 23)")`; column `value` with `color_scale={"scheme":"fill","color":"rgb(31, 32, 33)"}`; column `plain` unstyled.
  - Grid 1 — same rows, `pivotMode: True`, pivot on `bucket`, rule `("EU", "var(--st-aggrid-test-row)")`.
  - Grid 2 — grid 0's rules, toggled by checkboxes `"drop rule"` (empty rules) and `"recolour"` (`EU` → `"rgb(41, 42, 43)"`); a `runs` counter marker as in `grid_color_scale_picker.py`.

- [ ] **Step 2: Write the tests** in `test/test_grid_row_fill.py` (fixtures as `test_grid_color_scale.py:51-80`, waiting for 3 grids). Helper `row_background(page, grid, row_key) -> tuple|None` reading `getComputedStyle(row).backgroundColor` of the `.ag-row` at that `row-index`/section, parsed with `grid_dom.parse_rgba`; locate group/footer/total rows by their auto-column label, not by index.
  - `test_matching_group_row_is_filled_through_a_css_variable` — grid 0, `EU` group row → `(11,12,13,1.0)`.
  - `test_footer_of_the_matching_group_is_not_filled` — `Total EU` footer row → not `(11,12,13,…)`.
  - `test_leaves_siblings_and_grand_total_are_not_filled` — DE/FR/IT leaves, `US` group, grand `Total` → none carry either rule colour.
  - `test_numeric_group_key_matches_its_string_rule` — `bucket` `2` group rows (level 1) → `(21,22,23,1.0)`; `1` rows → unfilled.
  - `test_a_cell_colour_scale_wins_inside_its_cell` — `cell_backgrounds` on `EU` row: `value` → `(31,32,33,1.0)`, `plain` → transparent/unpainted (row shows through).
  - `test_collapsed_group_stays_filled` — click the `EU` group's expand chevron to collapse; `EU` row still `(11,12,13,1.0)`.
  - `test_pivot_group_row_is_filled` — grid 1, `EU` row → `(11,12,13,1.0)`.
  - `test_theme_variable_change_repaints_without_rerun` — `page.evaluate("document.documentElement.style.setProperty('--st-aggrid-test-row','rgb(51, 52, 53)')")`; `EU` row on grid 0 → `(51,52,53,1.0)`, `runs` marker unchanged.
  - `test_rerun_removing_the_rule_clears_the_row` — toggle `"drop rule"`; grid 2 `EU` row → not `(11,12,13,…)`.
  - `test_rerun_recolouring_the_rule_repaints_the_row` — toggle `"recolour"`; grid 2 `EU` → `(41,42,43,1.0)`.

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest test/test_grid_row_fill.py -v` → the fill assertions fail (rows unpainted; nothing installs `getRowStyle`).

- [ ] **Step 4: Implement** `stRowFillStyle` / `registerRowFill` and the `parsers.ts` call (comment: same site as the aggregators, so mount and live-update paths both install it).

- [ ] **Step 5: Rebuild** — `cd st_aggrid/frontend && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn build` → exits 0; `ls build` shows exactly one `index-*.js` and one `index-*.css`.

- [ ] **Step 6: Run** `uv run pytest test/test_grid_row_fill.py -v` → all pass. If `test_rerun_removing_the_rule_clears_the_row` fails, the `redrawRows()` at `AgGridComponent.tsx:734` did not recreate the row; stop and report rather than adding a second redraw.

- [ ] **Step 7: Commit** — `Paint group rows from the stRowFill declaration` (source, build delete + add, test app, tests).

---

### Task 5: Migrate the cohort pivot fixture; full suite

**Files:**
- Modify: `test/grid_cohort_pivot.py:176-186` (delete `js_cohort_row_style`), `:375` (replace `"getRowStyle": js_cohort_row_style` with `"context": {"stRowFill": [{"key": "cohort_1", "color": "var(--secondary-background-color)"}]}` — merge into an existing `context` key if `options` has one)

- [ ] **Step 1: Edit** as above; `grep -n "getRowStyle\|js_cohort_row_style" test/grid_cohort_pivot.py` → no output.
- [ ] **Step 2: Run** `uv run pytest test/test_grid_cohort_pivot.py -v` → all pass.
- [ ] **Step 3: Run everything** — `uv run pytest` (excludes slow) and all four `node …/__checks__/*.check.ts` → green. Record counts for the PR body.
- [ ] **Step 4: Commit** — `Declare the cohort fixture's row fill instead of scripting it`.

---

### Task 6: Docs and version 2.7.0

**Files:**
- Modify: `README.md` — install line + release pin hint → `@v2.7.0` (`:18` and the hint); new `#### Group-row fill` after "Interaction with `cellStyle`" (`:620`): the `configure_row_fill` example, the coverage table from the spec (footer **no**), the `getRowStyle` conflict; API Reference `columns_state` row → `list[ColumnState]`; a "2.7.0 compatibility" note: Python ≥ 3.13, typed `list[dict]` callers now need `list[ColumnState]`, runtime unchanged.
- Modify: `CLAUDE.md` — tree gains `row_fill.py` and `colorScales/rowFill.ts`; pure-module list gains `rowFill.ts`; Key Design Decisions gains one bullet ("`stRowFill`: group row by `node.key`, footers excluded, caller `getRowStyle` raises"); AG-Grid update checklist gains "8. re-check `ColumnState` fields against the new `ColumnState` interface and that group footer nodes still carry `footer: true`".
- Modify: `pyproject.toml:3`, `st_aggrid/pyproject.toml:13` → `2.7.0`; `uv lock`.

- [ ] **Step 1: Edit** all of the above.
- [ ] **Step 2: Verify** — `uv run pytest test/unit/test_component_manifest.py -v` → pass (versions in sync); `grep -rn "2\.6\.0" README.md pyproject.toml st_aggrid/pyproject.toml` → no output.
- [ ] **Step 3: Commit** — `Document group-row fill and release 2.7.0`.

---

### Task 7: PR, tag, consumer (each gated on the user's go-ahead)

- [ ] **Step 1:** Push the branch, open PR against `main` (body: both parts, spec link, test counts from Task 5, the compatibility note). **Ask before pushing.**
- [ ] **Step 2:** After merge: `scripts/release.sh` cuts annotated `v2.7.0` on `main`. **Ask before tagging** — a published tag never moves.
- [ ] **Step 3:** Consumer PR in `~/repo/hitapps_analytics` (separate repo, own branch), exactly the spec's "Release and consumer" step 3: pin `@v2.7.0`; `cohort_comparison/grid_builder.py:177` → `gb.configure_row_fill(key="cohort_1", color="var(--secondary-background-color)")`; `cohort/grid_builder.py:215` → drop `getRowStyle` without replacement; delete `js_cohort_row_style` and its imports; refresh root `.venv`; first commit lets the `ty-floor` hook lower the floor, then commit `ty_floor.json`. Verify: `grep -rn "getRowStyle\|js_cohort_row_style" web_app/web/dashboards` → no output; `grep -n grid_state web_app/ty_floor.json` → no output. Rebuild the web_app container last.
