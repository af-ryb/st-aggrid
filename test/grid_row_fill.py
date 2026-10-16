"""Streamlit app: the built-in group-row fill (`stRowFill`).

One small table: two regions, three countries each, and a numeric `bucket`.

  0  row-grouped `region` -> `bucket`, built through `GridOptionsBuilder`:
     `EU` filled from a CSS variable, bucket `2` from a literal (a numeric
     column's group key is the string "2"), a `value` column under
     `scheme: "fill"` that must win inside its own cells, and an unstyled
     `plain` column the row shows through. Subtotal footers and a grand total
     are on, because neither may be filled.
  1  the same rows in pivot mode (pivot on `bucket`) — the consumer's mode.
  2  grid 0's rules, changed by the two checkboxes: "drop rule" empties the
     list, "recolour" moves `EU` to another colour. Both reach the grid
     through a rerun, i.e. the live `updateGridOptions` path.

Grids keep their indices; a new grid is always appended.

Run standalone with:  streamlit run test/grid_row_fill.py
"""

import pandas as pd
import streamlit as st

from st_aggrid import AgGrid, GridOptionsBuilder

st.session_state.runs = st.session_state.get("runs", 0) + 1
st.text(f"runs={st.session_state.runs}")

# Set on `:root` the way Streamlit sets `--secondary-background-color`.
st.markdown(
    "<style>:root { --st-aggrid-test-row: rgb(11, 12, 13); }</style>",
    unsafe_allow_html=True,
)

df = pd.DataFrame(
    {
        "region": ["EU", "EU", "EU", "US", "US", "US"],
        "country": ["DE", "FR", "IT", "CA", "NY", "TX"],
        "bucket": [1, 2, 1, 1, 2, 2],
        "value": [10, 20, 30, 40, 50, 60],
        "plain": [1, 2, 3, 4, 5, 6],
    }
)

EU_COLOR = "var(--st-aggrid-test-row)"
BUCKET_COLOR = "rgb(21, 22, 23)"
CELL_FILL = "rgb(31, 32, 33)"
RECOLOUR = "rgb(41, 42, 43)"

COMMON_OPTIONS = {
    "suppressColumnVirtualisation": True,
    "suppressRowVirtualisation": True,
    "animateRows": False,
    "groupDefaultExpanded": -1,
    "groupTotalRow": "bottom",
    "grandTotalRow": "bottom",
    "autoGroupColumnDef": {"cellRendererParams": {"suppressCount": True}},
}


def grouped_columns():
    return [
        {"field": "region", "rowGroup": True, "rowGroupIndex": 0, "hide": True},
        {"field": "bucket", "rowGroup": True, "rowGroupIndex": 1, "hide": True},
        {"field": "country"},
        {
            "field": "value",
            "aggFunc": "sum",
            "context": {"stColorScale": {"scheme": "fill", "color": CELL_FILL}},
        },
        {"field": "plain", "aggFunc": "sum"},
    ]


st.subheader("0 — grouped, built through GridOptionsBuilder")
gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_column("region", rowGroup=True, rowGroupIndex=0, hide=True)
gb.configure_column("bucket", rowGroup=True, rowGroupIndex=1, hide=True)
gb.configure_column(
    "value", aggFunc="sum", color_scale={"scheme": "fill", "color": CELL_FILL}
)
gb.configure_column("plain", aggFunc="sum")
gb.configure_grid_options(**COMMON_OPTIONS)
gb.configure_row_fill(key="EU", color=EU_COLOR)
gb.configure_row_fill(key="2", color=BUCKET_COLOR)
AgGrid(df, grid_options=gb.build(), enable_enterprise_modules=True, key="grouped")

st.subheader("1 — pivot")
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "pivotMode": True,
        "pivotDefaultExpanded": -1,
        "columnDefs": [
            {"field": "region", "rowGroup": True},
            {"field": "bucket", "pivot": True},
            {"field": "value", "aggFunc": "sum"},
        ],
        "context": {"stRowFill": [{"key": "EU", "color": EU_COLOR}]},
    },
    enable_enterprise_modules=True,
    key="pivot",
)

st.subheader("2 — rules changed by a rerun")
drop = st.checkbox("drop rule", key="drop")
recolour = st.checkbox("recolour", key="recolour")
rules = [] if drop else [{"key": "EU", "color": RECOLOUR if recolour else EU_COLOR}]
AgGrid(
    df,
    grid_options={
        **COMMON_OPTIONS,
        "columnDefs": grouped_columns(),
        "context": {"stRowFill": rules},
    },
    enable_enterprise_modules=True,
    key="live",
)
