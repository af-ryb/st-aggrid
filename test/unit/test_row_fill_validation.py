"""Validation rules for the built-in `stRowFill` declaration.

A rule that cannot match paints nothing, and a row that is not painted looks
exactly like the feature being off. Every rule here turns that silence into a
loud error at `AgGrid()` time, before anything reaches the browser.
"""

import pandas as pd
import pytest

from st_aggrid import AgGrid
from st_aggrid.row_fill import ROW_FILL_CONTEXT_KEY, ROW_FILL_RULE_KEYS, validate_row_fill


def opts(rules, **extra):
    return {"columnDefs": [], "context": {ROW_FILL_CONTEXT_KEY: rules}, **extra}


def test_constants():
    assert ROW_FILL_CONTEXT_KEY == "stRowFill"
    assert ROW_FILL_RULE_KEYS == ("key", "color")


@pytest.mark.parametrize(
    "grid_options",
    [None, {}, {"context": {}}, opts([]), opts([], getRowStyle="f")],
)
def test_absent_and_empty_are_valid(grid_options):
    validate_row_fill(grid_options)


def test_valid_rule():
    validate_row_fill(opts([{"key": "cohort_1", "color": "var(--x)"}]))


def test_empty_string_key_is_valid():
    validate_row_fill(opts([{"key": "", "color": "red"}]))


def test_not_a_list():
    with pytest.raises(ValueError, match="stRowFill"):
        validate_row_fill(opts({"key": "a", "color": "red"}))


def test_rule_not_a_dict():
    with pytest.raises(ValueError, match=r"\[0\]"):
        validate_row_fill(opts(["a"]))


def test_unknown_rule_key():
    with pytest.raises(ValueError, match="field"):
        validate_row_fill(opts([{"key": "a", "color": "red", "field": "x"}]))


@pytest.mark.parametrize("rule", [{"color": "red"}, {"key": "a"}])
def test_missing_key_or_color(rule):
    with pytest.raises(ValueError):
        validate_row_fill(opts([rule]))


@pytest.mark.parametrize("key", [1, None, 1.5, True])
def test_non_string_key(key):
    with pytest.raises(ValueError, match="key"):
        validate_row_fill(opts([{"key": key, "color": "red"}]))


@pytest.mark.parametrize("color", ["", "  ", None, 7])
def test_blank_color(color):
    with pytest.raises(ValueError, match="color"):
        validate_row_fill(opts([{"key": "a", "color": color}]))


def test_duplicate_key():
    rules = [{"key": "a", "color": "red"}, {"key": "a", "color": "blue"}]
    with pytest.raises(ValueError, match=r"\[1\]"):
        validate_row_fill(opts(rules))


def test_get_row_style_none_is_not_a_conflict():
    # The frontend only yields to a truthy getRowStyle; None must not raise.
    validate_row_fill(opts([{"key": "a", "color": "red"}], getRowStyle=None))


def test_conflict_with_get_row_style():
    with pytest.raises(ValueError, match="getRowStyle"):
        validate_row_fill(opts([{"key": "a", "color": "red"}], getRowStyle="f"))


def test_aggrid_runs_the_validator(monkeypatch):
    monkeypatch.setattr(
        "st_aggrid.aggrid.get_aggrid_component", lambda: lambda **kwargs: None
    )
    grid_options = opts([{"key": 1, "color": "red"}])
    with pytest.raises(ValueError, match="stRowFill"):
        AgGrid(pd.DataFrame({"a": [1]}), grid_options=grid_options)
