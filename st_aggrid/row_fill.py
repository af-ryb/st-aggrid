"""Validation for the built-in group-row fill (``stRowFill``).

The painting lives in the frontend (``frontend/src/colorScales/rowFill.ts``):
a grid-level list of rules, each painting the group row whose own key equals
``key`` with ``color``. Subtotal footers, the grand total and leaves are never
painted. Python's only job here is to reject a rule that could never match —
a row that is not painted looks exactly like the feature being off.

Like ``color_scale.py`` this names no data fields, so it runs for every grid,
including one fed entirely through ``grid_options["rowData"]``. The frontend
sanitises the list again as a guard for grid options that never went through
``AgGrid()``, but drops what it cannot use silently; this copy is the one
that talks to the developer.
"""

from __future__ import annotations

from typing import Optional

#: Where the rules live inside the grid ``context``. Matches
#: ``colorScales/rowFill.ts``'s ``ST_ROW_FILL``.
ROW_FILL_CONTEXT_KEY = "stRowFill"

#: The only keys a rule may carry. Narrow on purpose: an unknown key is a
#: typo, not a future option.
ROW_FILL_RULE_KEYS = ("key", "color")


def validate_row_fill(grid_options: Optional[dict]) -> None:
    """Raise ``ValueError`` for a ``stRowFill`` declaration that cannot paint.

    An absent or empty list is valid and means "off".
    """
    if not isinstance(grid_options, dict):
        return
    context = grid_options.get("context")
    if not isinstance(context, dict) or ROW_FILL_CONTEXT_KEY not in context:
        return

    where = f"gridOptions context['{ROW_FILL_CONTEXT_KEY}']"
    rules = context[ROW_FILL_CONTEXT_KEY]
    if not isinstance(rules, list):
        raise ValueError(
            f"{where} must be a list of {{'key', 'color'}} rules, "
            f"got {type(rules).__name__}."
        )

    seen: set[str] = set()
    for index, rule in enumerate(rules):
        at = f"{where}[{index}]"
        if not isinstance(rule, dict):
            raise ValueError(f"{at} must be a dict, got {type(rule).__name__}.")
        unknown = sorted(set(rule) - set(ROW_FILL_RULE_KEYS))
        if unknown:
            raise ValueError(
                f"{at} has unknown keys {unknown}; a rule takes only "
                f"{list(ROW_FILL_RULE_KEYS)}."
            )
        missing = [k for k in ROW_FILL_RULE_KEYS if k not in rule]
        if missing:
            raise ValueError(f"{at} is missing {missing}.")

        key = rule["key"]
        # A group's key is always a string in the browser, so a number here
        # would compare `5 !== "5"` and never match.
        if not isinstance(key, str):
            raise ValueError(
                f"{at}: 'key' must be a str (a group key is always a string "
                f"in the grid), got {key!r}."
            )
        color = rule["color"]
        if not isinstance(color, str) or color.strip() == "":
            raise ValueError(f"{at}: 'color' must be a non-blank str, got {color!r}.")
        if key in seen:
            raise ValueError(
                f"{at}: a rule for key {key!r} already exists; the second "
                f"could never match."
            )
        seen.add(key)

    if rules and "getRowStyle" in grid_options:
        raise ValueError(
            f"gridOptions sets both getRowStyle and {where}. They fill the same "
            f"slot and getRowStyle would win, so the declaration would be "
            f"ignored. Drop one of them."
        )
