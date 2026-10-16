# Declarative group-row fill, and honest `ColumnState` types — Design

**Status:** designed against the code and a throwaway `ty` spike, not yet implemented
**Branch:** `feature/row-fill-column-state-types` (off `main` at `dc75a7a`)
**Date:** 2026-10-16
**Release:** 2.7.0 (additive public API; one annotation tightened; `requires-python` raised to 3.13)
**Consumer tasks:** stream 9, slices **9.4** (`getRowStyle` from a declaration)
and **9.5 (ty)** (`columns_state` / `ColumnState` types) — the backlog entries
of 2026-09-01 and 2026-10-16. Not the stRollup slice that also carried the
number 9.5.

All `path:line` references are to this repository at `dc75a7a` unless the path
starts with `web_app/`, which is the consumer (`hitapps_analytics` at
`87e0bda87`).

The two slices are independent — B is Python-only, A is Python + frontend —
but ship in one PR and one tag so the consumer takes a single pin bump that
closes both. They land as separate commits, **B first** (no rebuild, unit
tests only), then A, with a full e2e run after A.

---

# Part A — 9.4: group-row fill from a declaration

## Problem

The consumer's last hand-written colouring blob is `js_cohort_row_style`
(`web_app/web/dashboards/cohort/js_funcs.py:3`), set as the grid-level
`getRowStyle` on two grids
(`web_app/web/dashboards/cohort/grid_builder.py:215`,
`web_app/web/dashboards/cohort_comparison/grid_builder.py:177`):

```js
if (params.node.group && params.node.key === 'cohort_1')
  return { background: getComputedStyle(document.documentElement)
                         .getPropertyValue('--secondary-background-color') }
return null
```

The fork has expressed the same theme-dependent constant since 2.4.1 as a
column declaration (`scheme: "fill"`, `color: "var(--…)"`,
`colorScales/index.ts:182`, `:262`). What is missing is the **address**: a
row picked by a predicate, not a column. This is not a mechanism gap — it is
moving the last blob onto a form that already exists.

The fork's own cohort fixture carries a copy of the blob
(`test/grid_cohort_pivot.py:176`, used at `:375`), so the fork migrates first
and the consumer copies the result.

## Shape

Grid-level only, in `gridOptions["context"]["stRowFill"]`: a list of rules.

```python
gb.configure_row_fill(key="cohort_1", color="var(--secondary-background-color)")
# → gridOptions["context"]["stRowFill"] == [
#       {"key": "cohort_1", "color": "var(--secondary-background-color)"}]
```

A rule matches a row iff **`node.group` is true, `node.footer` is not, and
`node.key === rule.key`** — the blob's predicate minus subtotal footers
(decided 2026-10-16: the stripe marks the group row only). `node.key` is the key at the
row's own level; ancestors are not consulted. A list (not a `{key: color}`
map) so a later narrowing key (e.g. the level's `field`) can be added to a rule
without a format change; adding one is out of scope today.

Painted as `{ backgroundColor: rule.color }`. The colour string is passed
through untouched, so `var(--…)` resolves in the browser against the row
element's cascade. This is a deliberate change from the blob: the blob read the
variable once per row render through `getComputedStyle`; `var()` follows a
Streamlit theme switch with no rerun, which is the behaviour `scheme: "fill"`
already has on cells.

### What a rule covers, stated rather than left to discovery

| Row | Painted when key matches | Why |
| --- | --- | --- |
| group row | yes | the predicate |
| group footer (`groupTotalRow`) of that group | **no** | AG-Grid gives the footer node `group: true` and the group's `key`, so the blob painted it; excluded on purpose by `!node.footer` |
| grand total row | no | its `key` is `null`; cannot equal a string |
| leaf row | no | `node.group` is false |
| pinned row | only if it is a group node with that key | no special case — parity |

The footer row is the one line in this table that rests on AG-Grid internals
(that a footer node carries the group's key, so only `footer` tells it apart);
the e2e suite asserts the footer stays unpainted (see Tests).

### Interaction with cell colour

The row style is set on the row element; cells paint over it. A cell under an
active colour scale gets its own `backgroundColor` (a translucent `rgba` ramp,
a `rank` or a `fill`) and wins over the row inside that cell. An unpainted cell
gets `backgroundColor: ""` (`colorScales/index.ts:91`) or nothing, so the
row's fill shows through. That is the blob's behaviour today — no change.

### Precedence: a caller's `getRowStyle`

`getRowStyle` is one grid-level slot. With both a caller's `getRowStyle` and a
non-empty `stRowFill`, the declaration could only be dropped silently, so:

- **Python raises** `ValueError` in `validate_row_fill` naming both keys. Same
  author, same level — this is always a mistake, unlike a `defaultColDef.cellStyle`
  shadowing a column declaration, which the colour scales only warn about.
- **The frontend keeps the caller's function** and `console.warn`s once per
  parse — the guard for grid options that never went through `AgGrid()`'s
  validator. It never chains the two: a composed function would have to decide
  whose `background` wins, and that is the decision the caller should make in
  their own function.

`getRowClass` / `rowClassRules` are not touched and need no rule: they set
classes, not inline style, and inline style wins over them by the cascade.

## Python

New module `st_aggrid/row_fill.py`, modelled on `color_scale.py` (validation
only; the painting is frontend):

```python
ROW_FILL_CONTEXT_KEY = "stRowFill"
ROW_FILL_RULE_KEYS = ("key", "color")

def validate_row_fill(grid_options: Optional[dict]) -> None: ...
```

Rejects, each with a message naming the rule's index:
- `context["stRowFill"]` not a `list`;
- a rule not a `dict`, or with a key outside `ROW_FILL_RULE_KEYS`, or missing
  either key (narrow on purpose: an unknown key is a typo, not a future option);
- `key` not a `str` (`""` is allowed — it is the empty-group key AG-Grid builds
  for NULL/`""`, see `aggFuncs/rollupKey.ts`; a number is rejected because
  `node.key` is always a string and `5 !== "5"` would never match);
- `color` not a `str`, or blank after `strip()` (same rule as `fill`,
  `colorScales/index.ts:183`);
- two rules with the same `key` (the second could never match);
- `getRowStyle` present in `grid_options` while the list is non-empty.

An empty list is valid and means "off". Called from `AgGrid()` next to
`validate_color_scale_columns` (`st_aggrid/aggrid.py:467`). Runs for every
grid, `rowData`-only grids included — it names no data fields.

`GridOptionsBuilder.configure_row_fill(key: str, color: str)` — appends a rule
to `context["stRowFill"]`, copying `context` the way `configure_color_scale`
does (`grid_options_builder.py:232`); a second call with the same `key`
**replaces** that rule in place (idempotent builder; the duplicate check is for
hand-written options). It does not validate — `AgGrid()` does, once.

Exports: `ROW_FILL_CONTEXT_KEY` and `validate_row_fill` from `st_aggrid`
(mirrors the `COLOR_SCALE_*` exports in `__init__.py:37`).

## Frontend

- **`colorScales/rowFill.ts`** — pure, imports nothing (joins the pure-module
  list in CLAUDE.md):
  - `readRowFillRules(context: unknown): RowFillRule[]` — sanitise: keep only
    `{key: string, color: non-blank string}`, first rule for a key wins;
    anything else dropped (the Python copy is the one that talks).
  - `rowFillFor(rules, node: {group?: boolean; footer?: boolean; key?: string | null}): string | null`
    — the predicate above.
  - `colorScales/__checks__/rowFill.check.ts` — group/leaf/footer/grand-total
    shapes, `""` key, duplicate rules, junk entries; run with
    `node st_aggrid/frontend/src/colorScales/__checks__/rowFill.check.ts`.
- **`colorScales/index.ts`** — `stRowFillStyle(params: RowClassParams)` reads
  the rules from `params.context` on every call (so a live config update is
  just a new `context`) and returns `{ backgroundColor }` or `undefined`;
  `registerRowFill(gridOptions, debug)` installs it as `getRowStyle` when the
  rules are non-empty and the caller set none, warns otherwise (above).
- **`utils/parsers.ts`** — call `registerRowFill` next to `registerColorScales`
  (`parsers.ts:67`), so the mount path and the live-update path both get it,
  for the same reason as the aggregators (`parsers.ts:46-50`).

Live updates need no new code: after `updateGridOptions` the component already
calls `redrawRows()` (`AgGridComponent.tsx:734`), which re-evaluates
`getRowStyle`. A rule added, removed or recoloured on a rerun therefore reaches
painted rows; the e2e suite asserts all three directions, including removal
(the stale-style class of bug `UNPAINTED` exists for on cells).

Not done: no picker, no `interactive`, no `color_scale_state` analogue — the
consumer has one fixed stripe and the reader has no reason to move it.

## Tests

- `test/unit/test_row_fill_validation.py` — every rejection above, the empty
  list, `""` key, builder append/replace, `getRowStyle` conflict; plus
  `test_public_exports.py` for the two new names.
- `rowFill.check.ts` (above).
- `test/grid_row_fill.py` + `test/test_grid_row_fill.py` (new e2e): a row-grouped
  grid with `groupTotalRow` and `grandTotalRow`, one rule on one group key.
  Read rows by `row-index`, not DOM order (memory: AG-Grid positions rows
  absolutely). Asserts: the matching group row carries the
  resolved `--secondary-background-color`; its footer, sibling groups, leaves
  and the grand total do not; a column under `scheme: "fill"` still wins inside its cells;
  changing `--secondary-background-color` on `documentElement` from the test
  repaints the row with no rerun (the `var()` behaviour); a rerun that removes
  the rule clears the row; a rerun that recolours it repaints.
- `test/grid_cohort_pivot.py` — replace `js_cohort_row_style` with the
  declaration (it is the fork's copy of the consumer's config, so the whole
  cohort pivot suite becomes the regression guard for the migration).
  `js_hide_columns` stays — it is not about colour.

## Docs

- README: a short "Group-row fill" subsection under "Declarative colour scales
  without JavaScript" (after "Interaction with `cellStyle`", `README.md:620`):
  the predicate, the coverage table, the `getRowStyle` conflict.
- CLAUDE.md: `row_fill.py` and `colorScales/rowFill.ts` in the architecture
  tree; one line in Key Design Decisions.

---

# Part B — 9.5 (ty): `columns_state` and `ColumnState` types

## Problem

Of web_app's `ty` diagnostics, three are the fork's, all in
`web_app/src/bi_core/charts/grid_state.py` (floor `3` in `web_app/ty_floor.json`).
Reproduced 2026-10-16 with web_app's `ty 0.0.85`:

```
grid_state.py:856  AgGrid(columns_state=delta): expected `dict | None`, found `list[dict[str, object]] | Any`
grid_state.py:917  sorted(): `object` does not satisfy SupportsRichComparison
grid_state.py:925  sorted(): same
```

Roots: `st_aggrid/aggrid.py:183` annotates `columns_state: Optional[Dict]`
against its own docstring (`ColumnState[]`) and against `visibility_state()`
(returns `List[ColumnState]`); and `st_aggrid/column_state.py:50` defines
`ColumnState = Dict[str, object]`, so `e.get("colId")` is `object`.

## The backlog's form is not enough — the spike

The backlog proposed `columns_state: Optional[List[ColumnState]]` with
`ColumnState` a `TypedDict(total=False)`. A copy of the package patched exactly
that way and put first on `ty`'s search path (`--extra-search-path`) still gave
**3** diagnostics:

```
grid_state.py:883  derive_overlay(captured, ...): expected `Sequence[ColumnState] | None`, found `list[dict[Unknown, Unknown]]`
grid_state.py:917  sorted(): `str | None | Any` does not satisfy SupportsRichComparison
grid_state.py:925  sorted(): same
```

- `:883` is new: `AgGridResult.column_state` (`st_aggrid/result.py:56`) still
  returns `Optional[List[Dict]]`, and a `dict` is not assignable to a
  `TypedDict`. Once `ColumnState` is a real type, the result property must
  return it too.
- `:917`/`:925` persist: with `total=False` every key is optional, so
  `.get("colId")` is `str | None`, and `None` does not sort. `colId` is in
  every entry `getColumnState()` produces and every entry the helpers build —
  it is the one **required** key.

With both fixes the spike gave **`All checks passed!`** on `grid_state.py`,
and the whole-app count went 1763 → 1760 — exactly three fewer, nothing new
elsewhere. The fork's own `column_state.py` / `result.py` / `aggrid.py` gained
no diagnostic (the one pre-existing, `aggrid.py:175` `data: … = None`, is
untouched and out of scope).

## Change

`st_aggrid/column_state.py:50` — replace the alias:

```python
class ColumnState(TypedDict, total=False):
    """One entry of AG-Grid's ``getColumnState()`` / ``applyColumnState()``."""
    colId: Required[str]
    hide: Optional[bool]
    width: float
    flex: Optional[float]
    pinned: Optional[Literal["left", "right"]]
    sort: Optional[Literal["asc", "desc"]]
    sortIndex: Optional[int]
    aggFunc: Optional[str]
    rowGroup: Optional[bool]
    rowGroupIndex: Optional[int]
    pivot: Optional[bool]
    pivotIndex: Optional[int]
```

`typing.Required` (3.11+) is used directly: `requires-python` moves from
`>=3.10` to `>=3.13` in this release (decided 2026-10-16 — the consumer runs
3.13 and nothing older is supported). Both forms — `Required[str]` and a
required-`colId` base class — were checked in the spike and clear the same
diagnostics; `Required` is the one that reads as what it means. `aggFunc` is `str`, not AG-Grid's
`string | IAggFunc`: a function cannot cross the component boundary as JSON.
The field list is AG-Grid 36.1's `ColumnState` interface; it is re-checked on
AG-Grid bumps (add a line to CLAUDE.md's update checklist).

`st_aggrid/aggrid.py:183` — `columns_state: Optional[List[ColumnState]] = None`;
docstring `:248` says "list of ``ColumnState``" instead of "dict".

`st_aggrid/result.py:56` — `column_state -> Optional[List[ColumnState]]`.

Export `ColumnState` from `st_aggrid` and add it to `column_state.__all__`, so a
consumer can annotate its own `list[ColumnState]` without importing a private
path.

No runtime change: a `TypedDict` is a plain `dict` at runtime, and nothing
validates `columns_state`'s shape today. No frontend rebuild for this part.

`pyproject.toml:6` — `requires-python = ">=3.13"`; `uv lock` refreshed so
`uv.lock:3` follows. Nothing else in the repo names a Python version
(checked: no `.python-version`, no CI workflow).

## Compatibility note (README, release notes)

Python 3.10–3.12 are no longer supported; `pip` on those refuses 2.7.0 and
keeps 2.6.0.

A typed caller that passes a hand-built `list[dict]` to `columns_state` or to
the `column_state` helpers now gets a type-checker error it did not get before
(`dict` is not assignable to a `TypedDict`, and `list` is invariant). The fix
on their side is `list[ColumnState]`. Runtime behaviour is unchanged. The
consumer is not affected (spike above: `reconcile_grid_state`'s `list[dict]`
reaches `AgGrid` through `st.session_state`, which is `Any`).

## Tests

- `test/unit/test_column_state.py` — unchanged behaviour; add one test that
  `ColumnState.__required_keys__ == {"colId"}` and that the optional keys
  match the list above (pins the shape the spike validated).
- `test/unit/test_public_exports.py` — `ColumnState`.
- No `ty` run is added to the fork's own suite; the gate lives in web_app.

---

# Release and consumer

1. Fork PR (both parts) → full suites: `pytest -m "not e2e"`, `pytest`, the
   `.check.ts` files. Version 2.7.0 in **both** `pyproject.toml` and
   `st_aggrid/pyproject.toml`; README install line and release hint to
   `@v2.7.0`. Rebuilt `frontend/build/*` committed (delete + add).
2. Merge, tag via `scripts/release.sh` (annotated `v2.7.0` on `main`).
3. Consumer, one PR:
   - pin `web_app/pyproject.toml` → `@v2.7.0`; refresh the root `.venv` (the
     `ty-floor` hook counts against the locally installed fork);
   - `cohort_comparison/grid_builder.py:177`: replace
     `getRowStyle=js_cohort_row_style` with
     `gb.configure_row_fill(key="cohort_1", color="var(--secondary-background-color)")`;
   - `cohort/grid_builder.py:215`: drop `getRowStyle=js_cohort_row_style` with
     no replacement — a single-cohort grid never has a `cohort_1` group, so the
     rule was dead there (confirmed 2026-10-16);
   - delete `js_cohort_row_style` (`js_funcs.py:3`) and its import in
     `cohort_comparison`;
   - first commit: the hook lowers `grid_state.py`'s floor and fails once —
     commit `ty_floor.json` (no `--rebaseline`);
   - rebuild the web_app container (the fork installs from the pyproject pin,
     not `uv.lock`).
4. Done when: the comparison grid paints the `cohort_1` group row (not its
   footer) from the declaration and the single-cohort grid carries no row
   style; `js_cohort_row_style` is gone and `web_app/web/dashboards` holds
   no colour-related `JsCode` (`js_hide_columns` and the payers formatters are
   not colour); `grid_state.py` is out of `ty_floor.json`; the consumer pin is
   `v2.7.0`; the fork's suites are green.

Not in scope (the consumer's own, per the backlog): `grid_options.py:40`
(`_per_metric`) and the 27 diagnostics in
`tests/src/bi_core/charts/test_grid_options.py`. They can ride the pin PR but
are not fork work.

## Decided 2026-10-16

- Subtotal footers are not painted (`!node.footer` in the predicate).
- `cohort_1` cannot occur on the single-cohort grid; its `getRowStyle` is
  removed, not migrated.
- `requires-python = ">=3.13"`; `ColumnState` uses `typing.Required`.
