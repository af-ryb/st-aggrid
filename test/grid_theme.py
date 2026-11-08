"""Streamlit app rendering one grid in the default ``streamlit`` theme."""

import pandas as pd
from st_aggrid import AgGrid

AgGrid(
    pd.DataFrame({"name": ["apple", "banana", "cherry"], "qty": [1, 2, 3]}),
    key="grid_theme",
)
