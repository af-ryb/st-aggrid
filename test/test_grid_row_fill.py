"""The built-in group-row fill, painted by a real grid.

Rows are located by their auto-group label and addressed by `row-index`,
never by document order: AG-Grid positions rows absolutely, and a probe
written against DOM order produced a false result in this repo once already.
The colour read is the row element's computed background — what the
declaration sets — not a cell's.
"""

import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page

from e2e_utils import StreamlitRunner
from grid_dom import cell_backgrounds, parse_rgba

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
APP_FILE = ROOT_DIRECTORY / "test" / "grid_row_fill.py"

GROUPED_GRID = 0
PIVOT_GRID = 1
LIVE_GRID = 2

EU_RGB = (11, 12, 13, 1.0)
BUCKET_RGB = (21, 22, 23, 1.0)
CELL_FILL_RGB = (31, 32, 33, 1.0)
RECOLOUR_RGB = (41, 42, 43, 1.0)
RULE_COLOURS = {EU_RGB[:3], BUCKET_RGB[:3], RECOLOUR_RGB[:3]}


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(APP_FILE) as runner:
        yield runner


@pytest.fixture(autouse=True, scope="function")
def go_to_app(page: Page, streamlit_app: StreamlitRunner):
    page.goto(streamlit_app.server_url)
    page.get_by_role("img", name="Running...").is_hidden()
    page.wait_for_function(
        "() => document.querySelectorAll('.ag-root-wrapper').length >= 3",
        timeout=60000,
    )
    # Every grid has its grand total rendered once the model is built.
    page.wait_for_function(
        """() => [...document.querySelectorAll('.ag-root-wrapper')].slice(0, 3)
             .every(g => [...g.querySelectorAll('.ag-row')]
               .some(r => r.textContent.trim().startsWith('Total')))""",
        timeout=60000,
    )


_READ_ROWS = """
(gridIndex) => {
  const grid = document.querySelectorAll('.ag-root-wrapper')[gridIndex];
  const out = [];
  for (const row of grid.querySelectorAll('.ag-row')) {
    const auto = row.querySelector('[col-id^="ag-Grid-AutoColumn"]');
    if (!auto) continue;
    const level = /(?:^| )ag-row-level-(\\d+)(?: |$)/.exec(row.className);
    out.push({
      rowIndex: row.getAttribute('row-index'),
      label: auto.textContent.trim(),
      level: level ? Number(level[1]) : null,
      footer: row.classList.contains('ag-row-footer'),
      background: getComputedStyle(row).backgroundColor,
    });
  }
  return out;
}
"""


def rows(page: Page, grid: int) -> list[dict]:
    """One entry per row that has an auto-group cell, i.e. every row (the
    auto column is the left-most), with its parsed row background."""
    found = page.evaluate(_READ_ROWS, grid)
    for row in found:
        row["rgba"] = parse_rgba(row["background"])
    return found


def find(page: Page, grid: int, label: str, level: int | None = None) -> list[dict]:
    hits = [
        r for r in rows(page, grid)
        if r["label"] == label and (level is None or r["level"] == level)
    ]
    assert hits, f"grid {grid}: no row labelled {label!r} (level {level})"
    return hits


def filled_with(row: dict, rgba: tuple) -> bool:
    return row["rgba"] is not None and row["rgba"][:3] == rgba[:3] and row["rgba"][3] > 0


def assert_not_rule_coloured(row: dict) -> None:
    rgba = row["rgba"]
    assert rgba is None or rgba[3] == 0 or rgba[:3] not in RULE_COLOURS, row


def eventually(check, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return check()
        except AssertionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def marker(page: Page, prefix: str) -> str:
    text = page.get_by_text(re.compile(rf"^{prefix}=")).first.inner_text()
    return text.split("=", 1)[1]


def toggle(page: Page, label: str) -> None:
    """Click a checkbox and wait until the rerun it triggers has landed."""
    runs = int(marker(page, "runs"))
    page.get_by_text(label).click()
    eventually(lambda: _assert_greater(int(marker(page, "runs")), runs))


def _assert_greater(a: int, b: int) -> None:
    assert a > b


def test_matching_group_row_is_filled_through_a_css_variable(page: Page):
    (eu,) = find(page, GROUPED_GRID, "EU", level=0)
    assert filled_with(eu, EU_RGB), eu


def test_footer_of_the_matching_group_is_not_filled(page: Page):
    (footer,) = find(page, GROUPED_GRID, "Total EU")
    assert_not_rule_coloured(footer)


def test_leaves_siblings_and_grand_total_are_not_filled(page: Page):
    (us,) = find(page, GROUPED_GRID, "US", level=0)
    assert_not_rule_coloured(us)
    leaves = [r for r in rows(page, GROUPED_GRID) if r["level"] == 2]
    assert len(leaves) == 6, leaves
    for leaf in leaves:
        assert_not_rule_coloured(leaf)
    (total,) = find(page, GROUPED_GRID, "Total")
    assert_not_rule_coloured(total)


def test_numeric_group_key_matches_its_string_rule(page: Page):
    twos = find(page, GROUPED_GRID, "2", level=1)
    assert len(twos) == 2, twos  # one under EU, one under US
    for row in twos:
        assert filled_with(row, BUCKET_RGB), row
    for row in find(page, GROUPED_GRID, "1", level=1):
        assert_not_rule_coloured(row)


def test_a_cell_colour_scale_wins_inside_its_cell(page: Page):
    (eu,) = find(page, GROUPED_GRID, "EU", level=0)
    cells = cell_backgrounds(page, GROUPED_GRID)[f"body:{eu['rowIndex']}"]
    assert cells["value"] is not None and cells["value"][:3] == CELL_FILL_RGB[:3]
    # The unstyled cell lets the row show through: transparent, never another colour.
    plain = cells["plain"]
    assert plain is None or plain[3] == 0, plain


def test_collapsed_group_stays_filled(page: Page):
    (eu,) = find(page, GROUPED_GRID, "EU", level=0)
    grid = page.locator(".ag-root-wrapper").nth(GROUPED_GRID)
    grid.locator(f'.ag-row[row-index="{eu["rowIndex"]}"] .ag-group-expanded').first.click()
    page.mouse.move(0, 0)
    eventually(lambda: _assert_no_row(page, GROUPED_GRID, "Total EU"))
    (eu,) = find(page, GROUPED_GRID, "EU", level=0)
    assert filled_with(eu, EU_RGB), eu


def _assert_no_row(page: Page, grid: int, label: str) -> None:
    assert not [r for r in rows(page, grid) if r["label"] == label]


def test_pivot_group_row_is_filled(page: Page):
    (eu,) = find(page, PIVOT_GRID, "EU", level=0)
    assert filled_with(eu, EU_RGB), eu
    (us,) = find(page, PIVOT_GRID, "US", level=0)
    assert_not_rule_coloured(us)


def test_theme_variable_change_repaints_without_rerun(page: Page):
    runs = marker(page, "runs")
    page.evaluate(
        "document.documentElement.style.setProperty("
        "'--st-aggrid-test-row', 'rgb(51, 52, 53)')"
    )
    eventually(
        lambda: _assert_filled(find(page, GROUPED_GRID, "EU", level=0)[0], (51, 52, 53, 1.0))
    )
    assert marker(page, "runs") == runs


def _assert_filled(row: dict, rgba: tuple) -> None:
    assert filled_with(row, rgba), row


def test_rerun_removing_the_rule_clears_the_row(page: Page):
    (eu,) = find(page, LIVE_GRID, "EU", level=0)
    assert filled_with(eu, EU_RGB), eu
    toggle(page, "drop rule")
    eventually(lambda: assert_not_rule_coloured(find(page, LIVE_GRID, "EU", level=0)[0]))


def test_rerun_recolouring_the_rule_repaints_the_row(page: Page):
    toggle(page, "recolour")
    eventually(lambda: _assert_filled(find(page, LIVE_GRID, "EU", level=0)[0], RECOLOUR_RGB))
