from pathlib import Path
from typing import List, Sequence

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, dcc, html
from dash.html.Base import ComponentSingleType


def find_results(directory: str | Path) -> List[str]:
    """Find .csv result files under a directory.

    Args:
        directory: Root directory to search recursively.

    Returns:
        List[str]: Sorted list of CSV file paths.

    Raises:
        FileNotFoundError: If the directory does not exist.
        NotADirectoryError: If the path is not a directory.
    """

    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"Results directory not found: {directory_path}")
    if not directory_path.is_dir():
        raise NotADirectoryError(f"Results path is not a directory: {directory_path}")
    return sorted(str(path) for path in directory_path.rglob("*.csv") if path.is_file())


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


class ResultSelectBuilder:
    """Builds a result file dropdown control for Dash layouts.

    Attributes:
        _select: Cached dropdown container built by build_select.
        _result_files: File paths available for selection.
        _selected_result: Default selected file path.
        _results_root: Root directory used to shorten display labels.
    """

    def __init__(
        self,
        result_files: Sequence[str],
        selected_result: str | None = None,
        results_root: str | Path | None = None,
    ):
        """Initialize the result select builder.

        Args:
            result_files: Sequence of result file paths to list.
            selected_result: Default selected file path.
            results_root: Root directory to remove from display labels.
        """

        self._result_files = result_files
        self._selected_result = selected_result or (result_files[0] if result_files else None)
        self._results_root = Path(results_root) if results_root is not None else None
        self._select: html.Div | None = None

    def build_select(self):
        """Build and cache the result select dropdown.

        Returns:
            None.
        """

        options = [
            {"label": self._format_label(result_file), "value": result_file} for result_file in self._result_files
        ]
        self._select = html.Div(
            children=[
                html.Label("Result File"),
                dcc.Dropdown(options, id="result-select", value=self._selected_result, clearable=False),
            ],
            style={"display": "flex", "flexDirection": "column", "gap": "4px"},
        )

    def get_select(self):
        """Return the cached result select control.

        Returns:
            The result dropdown container, or None if it has not been built.
        """

        return self._select

    def _format_label(self, result_file: str) -> str:
        if not self._results_root:
            return result_file
        try:
            return str(Path(result_file).relative_to(self._results_root))
        except ValueError:
            return result_file


class DashBuilder:
    """Builds a Dash app that renders a grid of time-series graphs.

    Attributes:
        _app: The Dash application instance.
        _layout: Layout components to render in the app.
        _data: Data source for plots; expects a "time" column.
        _variable_columns: Data columns available for selection, excluding "time".
    """

    def __init__(self, name: str):
        """Initialize the Dash app builder.

        Args:
            name: App name passed to Dash.
        """

        self._app = dash.Dash(name)
        self._layout: List[ComponentSingleType] = []
        self._data = pd.DataFrame()
        self._variable_columns: List[str] = []

    def build_result_select(
        self,
        result_files: Sequence[str],
        selected_result: str | None = None,
        results_root: str | Path | None = None,
    ):
        """Add the result file dropdown to the layout.

        Args:
            result_files: Sequence of result file paths available for selection.
            selected_result: Default selected result file path.
            results_root: Root directory to remove from display labels.

        Returns:
            None.
        """

        result_select = ResultSelectBuilder(
            result_files,
            selected_result,
            results_root,
        )
        result_select.build_select()
        self._layout.append(result_select.get_select())

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
            Input("result-select", "value"),
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

    def _set_data(self, data: pd.DataFrame):
        """Store the data and update available variable columns.

        Args:
            data: DataFrame containing a "time" column and value columns to plot.
        """

        self._data = data
        self._variable_columns = [column for column in data.columns if column != "time"]

    def _load_results(self, result_file: str | None):
        """Load result data from a CSV file and update internal state.

        Args:
            result_file: CSV file path to load.
        """

        if not result_file:
            return
        self._set_data(pd.read_csv(result_file))

    def _update_graph_callback(
        self,
        selected_variables: Sequence[str | Sequence[str] | None],
    ) -> List[go.Figure]:
        """Build figures for each graph based on selected variables.

        Args:
            selected_variables: List of selections per graph cell.

        Returns:
            A list of Plotly figures aligned with the grid inputs.
        """

        figures = []
        for selected_variable in selected_variables:
            if isinstance(selected_variable, str):
                # Dash may pass a single string when only one variable is chosen.
                selected_variable = [selected_variable] if selected_variable else []
            elif selected_variable is None:
                # No selection made for this graph cell.
                selected_variable = []
            else:
                # Multi-select list; filter out empty values from cleared items.
                selected_variable = [variable for variable in selected_variable if variable]

            if not selected_variable:
                figures.append(go.Figure())
            else:
                figures.append(px.line(self._data, x="time", y=selected_variable))
        return figures

    def _build_graph_grid(self, _, selected_result: str, rows: int, cols: int):
        """Create a grid of graph containers.

        Args:
            _: Unused callback input from Dash.
            selected_result: Selected result file path.
            rows: Number of grid rows.
            cols: Number of grid columns.

        Returns:
            A list of row containers for the grid.
        """

        self._load_results(selected_result)
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
