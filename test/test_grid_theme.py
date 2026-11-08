"""The ``streamlit`` theme must follow st.dataframe in both colour schemes."""

from pathlib import Path

import pytest
from playwright.sync_api import Locator, Page, expect

from e2e_utils import StreamlitRunner

ROOT_DIRECTORY = Path(__file__).parent.parent.absolute()
THEME_FILE = ROOT_DIRECTORY / "test" / "grid_theme.py"

RESOLVE_VAR = """(element, name) => {
    const probe = document.createElement("div");
    probe.style.backgroundColor = `var(${name})`;
    element.appendChild(probe);
    const resolved = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return resolved;
}"""


@pytest.fixture(autouse=True, scope="module")
def streamlit_app():
    with StreamlitRunner(THEME_FILE) as runner:
        yield runner


@pytest.fixture(params=["dark", "light"])
def grid(request: pytest.FixtureRequest, page: Page, streamlit_app) -> Locator:
    page.emulate_media(color_scheme=request.param)
    page.goto(streamlit_app.server_url)
    root = page.locator(".st-key-grid_theme .ag-root-wrapper")
    expect(root.locator(".ag-row").first).to_be_visible()
    return root


def _background(locator: Locator) -> str:
    return locator.evaluate("element => getComputedStyle(element).backgroundColor")


def test_rows_take_the_page_background_without_stripes(grid: Locator):
    expected = grid.evaluate(RESOLVE_VAR, "--st-background-color")

    assert _background(grid.locator(".ag-row-even").first) == expected
    assert _background(grid.locator(".ag-row-odd").first) == expected


def test_header_and_borders_take_the_dataframe_colours(grid: Locator):
    pairs = {
        "--ag-header-background-color": "--st-dataframe-header-background-color",
        "--ag-border-color": "--st-dataframe-border-color",
    }

    for grid_param, streamlit_var in pairs.items():
        assert grid.evaluate(RESOLVE_VAR, grid_param) == grid.evaluate(
            RESOLVE_VAR, streamlit_var
        )


def test_cells_use_the_streamlit_font(grid: Locator):
    font = grid.locator(".ag-cell").first.evaluate(
        "element => getComputedStyle(element).fontFamily"
    )

    assert "Source Sans" in font
