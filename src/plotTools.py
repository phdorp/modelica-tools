from typing import List, Sequence

import dash
import pandas as pd
import plotly.express as px
from dash import ALL, Input, Output, State, dcc, html
from dash.html.Base import ComponentSingleType


class GraphGridBuilder:
    """Builds a grid of graph controls for Dash layouts.

    Attributes:
        _grid: Cached grid layout built by build_grid.
        _variable_columns: Column names available for selection.
    """

    def __init__(self, variable_columns: Sequence[str]):
        """Initialize the grid builder.

        Args:
            variable_columns: Sequence of column names available for graph selection.
        """

        self._grid: List[html.Div] | None = None
        self._variable_columns = variable_columns

    def build_grid(self, _, rows: int, cols: int):
        """Build and cache the grid layout.

        Args:
            _: Unused callback input from Dash.
            rows: Number of grid rows.
            cols: Number of grid columns.

        Returns:
            None.
        """

        self._grid = [self._build_row(row, cols) for row in range(rows)]

    def get_grid(self):
        """Return the cached grid layout.

        Returns:
            The list of row containers, or None if the grid has not been built.
        """

        return self._grid

    def _build_row(self, row: int, cols: int):
        """Build a row container for the grid.

        Args:
            row: Row index.
            cols: Number of columns in the row.

        Returns:
            A Dash HTML Div representing the row.
        """

        return html.Div(
            children=[self._build_cell(row, col) for col in range(cols)],
            style={
                "display": "grid",
                "gridTemplateColumns": f"repeat({cols}, minmax(0, 1fr))",
                "gap": "12px",
                "width": "100%",
            },
        )

    def _build_cell(self, row: int, col: int):
        """Build a grid cell with a dropdown and graph.

        Args:
            row: Row index.
            col: Column index.

        Returns:
            A Dash HTML Div containing the controls for the cell.
        """

        return html.Div(
            children=[
                dcc.Dropdown(
                    [{"label": column, "value": column} for column in self._variable_columns],
                    id={"type": "variable-dropdown", "row": row, "col": col},
                    value=self._variable_columns[:1],
                    multi=True,
                ),
                dcc.Graph(id={"type": "graph", "row": row, "col": col}, style={"width": "100%"}),
            ],
            style={"border": "1px solid #ccc", "padding": "8px", "minWidth": 0, "width": "100%"},
        )


class GridControlBuilder:
    """Builds grid size controls for the Dash layout.

    Attributes:
        _controls: Cached controls container built by build_controls.
    """

    def __init__(self):
        """Initialize the control builder."""

        self._controls: html.Div | None = None

    def build_controls(self):
        """Build and cache the grid controls.

        Returns:
            None.
        """

        self._controls = html.Div(
            children=[
                html.Div(
                    children=[html.Label("Rows"), dcc.Input(id="rows-input", type="number", min=1, step=1, value=1)]
                ),
                html.Div(
                    children=[html.Label("Columns"), dcc.Input(id="cols-input", type="number", min=1, step=1, value=1)]
                ),
                html.Button("Apply Grid", id="apply-grid", n_clicks=0),
            ],
            style={"display": "flex", "gap": "16px", "alignItems": "end"},
        )

    def get_controls(self):
        """Return the cached grid controls.

        Returns:
            The controls container, or None if controls have not been built.
        """

        return self._controls


class DashBuilder:
    """Builds a Dash app that renders a grid of time-series graphs.

    Attributes:
        _app: The Dash application instance.
        _layout: Layout components to render in the app.
        _data: Data source for plots; expects a "time" column.
        _variable_columns: Data columns available for selection, excluding "time".
    """

    def __init__(self, name: str, data: pd.DataFrame):
        """Initialize the Dash app builder.

        Args:
            name: App name passed to Dash.
            data: DataFrame containing a "time" column and value columns to plot.
        """

        self._app = dash.Dash(name)
        self._layout: List[ComponentSingleType] = []
        self._data: pd.DataFrame = data
        self._variable_columns = [column for column in data.columns if column != "time"]

    def build_grid_controls(self):
        """Add grid control inputs and a grid container to the layout.

        Returns:
            None.
        """

        self._layout.append(self._build_grid_controls())
        self._layout.append(html.Div(id="graphs-grid"))

    def build_graph_grid(self):
        """Register callbacks for building the grid and updating graphs.

        Returns:
            None.
        """

        self._app.callback(
            Output("graphs-grid", "children"),
            Input("apply-grid", "n_clicks"),
            State("rows-input", "value"),
            State("cols-input", "value"),
        )(self._build_graph_grid)
        self._app.callback(
            Output({"type": "graph", "row": ALL, "col": ALL}, "figure"),
            Input({"type": "variable-dropdown", "row": ALL, "col": ALL}, "value"),
        )(self._update_graph_callback)

    def build_title(self, title: str):
        """Add a title heading to the layout.

        Args:
            title: Text to display as the page title.

        Returns:
            None.
        """

        self._layout.append(html.H1(title))

    def get_app(self):
        """Finalize the layout and return the Dash app.

        Returns:
            The configured Dash application.
        """

        self._app.layout = html.Div(children=self._layout)
        return self._app

    def _update_graph_callback(self, selected_variables):
        """Build figures for each graph based on selected variables.

        Args:
            selected_variables: List of selections per graph cell.

        Returns:
            A list of Plotly figures aligned with the grid inputs.
        """

        figures = []
        for selected_variable in selected_variables:
            if isinstance(selected_variable, str):
                selected_variable = [selected_variable]
            figures.append(
                px.line(self._data, x="time")
                if not selected_variable
                else px.line(self._data, x="time", y=selected_variable)
            )
        return figures

    def _build_graph_grid(self, _, rows: int, cols: int):
        """Create a grid of graph containers.

        Args:
            _: Unused callback input from Dash.
            rows: Number of grid rows.
            cols: Number of grid columns.

        Returns:
            A list of row containers for the grid.
        """

        graph_grid = GraphGridBuilder(self._variable_columns)
        graph_grid.build_grid(_, rows, cols)
        return graph_grid.get_grid()

    @staticmethod
    def _build_grid_controls():
        """Build the grid controls container.

        Returns:
            The Dash controls container.
        """

        grid_controls = GridControlBuilder()
        grid_controls.build_controls()
        return grid_controls.get_controls()
