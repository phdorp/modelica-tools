from itertools import zip_longest
from pathlib import Path
from typing import List, Sequence

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, dcc, html
from dash.development.base_component import Component


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


def resolve_path(value: str | Path) -> str | None:
    """Resolve a path to a comparable canonical string.

    Returns None when the value cannot be resolved.
    """

    try:
        return str(Path(value).resolve())
    except (OSError, ValueError):
        return None


def format_result_label(result_file: str, root: Path | None) -> str:
    """Shorten a result path relative to the results root."""

    if root is None:
        return result_file
    try:
        return str(Path(result_file).relative_to(root))
    except ValueError:
        return result_file


class ResultCatalog:
    """Owns result discovery and selection matching for one root."""

    def __init__(self, root: str | Path | None):
        self._root = Path(root) if root is not None else None

    @property
    def root(self) -> Path | None:
        return self._root

    def effective_root(self) -> Path:
        return self._root if self._root is not None else Path.cwd()

    def list_files(self) -> List[str]:
        return find_results(self.effective_root())

    def format_label(self, result_file: str) -> str:
        return format_result_label(result_file, self._root)

    def build_options(self, result_files: Sequence[str]) -> List[dict]:
        return [
            {"label": self.format_label(result_file), "value": result_file} for result_file in result_files
        ]

    def find_same_file(self, current_value: str | None, result_files: Sequence[str]) -> str | None:
        """Return the rescanned entry for the current selection, or None when gone."""

        if current_value is None:
            return None
        current_resolved = resolve_path(current_value)
        if current_resolved is None:
            return None
        for result_file in result_files:
            if resolve_path(result_file) == current_resolved:
                return result_file
        return None


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

    def build_grid(
        self,
        _,
        rows: int,
        cols: int,
        preserved_x_values=None,
        preserved_y_values=None,
    ):
        """Build and cache the grid layout.

        Args:
            _: Unused callback input from Dash.
            rows: Number of grid rows.
            cols: Number of grid columns.
            preserved_x_values: Prior x-dropdown selections in row-major order.
            preserved_y_values: Prior y-dropdown selections in row-major order.
                Entries still present in ``_variable_columns`` are kept;
                entries without overlap fall back to the default.
                None (or empty) means no prior state, so defaults apply.

        Returns:
            None.
        """

        self._grid = [
            self._build_row(row, cols, preserved_x_values, preserved_y_values) for row in range(rows)
        ]

    def get_grid(self):
        """Return the cached grid layout.

        Returns:
            The list of row containers, or None if the grid has not been built.
        """

        return self._grid

    _MISSING = object()

    def _build_row(self, row: int, cols: int, preserved_x_values=None, preserved_y_values=None):
        """Build a row container for the grid.

        Args:
            row: Row index.
            cols: Number of columns in the row.
            preserved_x_values: Prior x-dropdown selections in row-major order.
            preserved_y_values: Prior y-dropdown selections in row-major order.

        Returns:
            A Dash HTML Div representing the row.
        """

        cells = []
        for col in range(cols):
            index = row * cols + col
            preserved_x = (
                preserved_x_values[index]
                if preserved_x_values is not None and index < len(preserved_x_values)
                else self._MISSING
            )
            preserved_y = (
                preserved_y_values[index]
                if preserved_y_values is not None and index < len(preserved_y_values)
                else self._MISSING
            )
            cells.append(self._build_cell(row, col, preserved_x=preserved_x, preserved_y=preserved_y))
        return html.Div(
            children=cells,
            style={
                "display": "grid",
                "gridTemplateColumns": f"repeat({cols}, minmax(0, 1fr))",
                "gap": "12px",
                "width": "100%",
            },
        )

    def _resolve_value(self, preserved=_MISSING):
        """Resolve the dropdown value, keeping selections still available."""
        default = self._variable_columns[:1]
        if preserved is self._MISSING:
            return default
        if preserved is None:
            return []
        if isinstance(preserved, str):
            normalized = [preserved] if preserved else []
        else:
            normalized = [variable for variable in preserved if variable]
        kept = [variable for variable in normalized if variable in self._variable_columns]
        if normalized and not kept:
            return default
        return kept

    def _resolve_x_value(self, preserved=_MISSING) -> str:
        """Resolve x-axis selection, defaulting to time."""
        default = "time"
        if preserved is self._MISSING or preserved is None:
            return default
        if isinstance(preserved, Sequence) and not isinstance(preserved, str):
            normalized = next((value for value in preserved if value), None)
        else:
            normalized = preserved
        if normalized in ("time", *self._variable_columns):
            return normalized
        return default

    def _build_cell(self, row: int, col: int, preserved_x=_MISSING, preserved_y=_MISSING):
        """Build a grid cell with a dropdown and graph.

        Args:
            row: Row index.
            col: Column index.
            preserved_x: Prior x-axis selection for this cell.
            preserved_y: Prior y-axis selections for this cell. Values still
                present in ``_variable_columns`` are kept; otherwise the
                default applies. ``_MISSING`` (no prior state) also uses
                the default.

        Returns:
            A Dash HTML Div containing the controls for the cell.
        """

        return html.Div(
            children=[
                dcc.Dropdown(
                    [{"label": "time", "value": "time"}]
                    + [{"label": column, "value": column} for column in self._variable_columns],
                    id={"type": "x-variable-dropdown", "row": row, "col": col},
                    value=self._resolve_x_value(preserved_x),
                    clearable=False,
                ),
                dcc.Dropdown(
                    [{"label": column, "value": column} for column in self._variable_columns],
                    id={"type": "variable-dropdown", "row": row, "col": col},
                    value=self._resolve_value(preserved_y),
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

    @property
    def _catalog(self) -> ResultCatalog:
        return ResultCatalog(self._results_root)

    def build_select(self):
        """Build and cache the result select dropdown with a rescan button.

        Returns:
            None.
        """

        options = self._catalog.build_options(self._result_files)
        self._select = html.Div(
            children=[
                html.Label("Result File"),
                html.Div(
                    children=[
                        dcc.Dropdown(
                            options,
                            id="result-select",
                            value=self._selected_result,
                            clearable=False,
                            style={"flex": "1"},
                        ),
                        html.Button("Rescan", id="rescan-results", n_clicks=0),
                    ],
                    style={"display": "flex", "gap": "8px", "alignItems": "center"},
                ),
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
        return self._catalog.format_label(result_file)


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
        self._layout: List[Component] = []
        self._data = pd.DataFrame()
        self._variable_columns: List[str] = []
        self._results_root: Path | None = None

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
        select = result_select.get_select()
        if select is not None:
            self._layout.append(select)
        if results_root is not None:
            self._remember_results_root(results_root)

    def build_result_explorer(self, results_root: str | Path | None = None):
        """Register a callback that rescans results_root subdirectories.

        Args:
            results_root: Root directory to search for CSV files.
                Defaults to the current working directory when None.

        Returns:
            None.
        """

        self._remember_results_root(results_root if results_root is not None else Path.cwd())
        self._app.callback(
            [Output("result-select", "options"), Output("result-select", "value")],
            Input("rescan-results", "n_clicks"),
            State("result-select", "value"),
            prevent_initial_call=True,
        )(self._refresh_results)

    def _remember_results_root(self, root: str | Path | None) -> None:
        self._results_root = Path(root) if root is not None else None

    def _current_catalog(self) -> ResultCatalog:
        return ResultCatalog(self._results_root)

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
            State({"type": "x-variable-dropdown", "row": ALL, "col": ALL}, "value"),
            State({"type": "variable-dropdown", "row": ALL, "col": ALL}, "value"),
        )(self._build_graph_grid)
        self._app.callback(
            Output({"type": "graph", "row": ALL, "col": ALL}, "figure"),
            Input({"type": "x-variable-dropdown", "row": ALL, "col": ALL}, "value"),
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

    def _refresh_results(self, _, current_value: str | None):
        """Rescan results_root subdirectories and rebuild dropdown options.

        Args:
            _: Unused callback input from the rescan button.
            current_value: Currently selected result file path.

        Returns:
            Tuple of dropdown options and the value to select.
            Returns dash.no_update for the value when the current
            selection is still valid, leaving graphs untouched.
        """

        catalog = self._current_catalog()
        result_files = catalog.list_files()
        options = catalog.build_options(result_files)
        matched = catalog.find_same_file(current_value, result_files)
        if matched is None:
            return options, result_files[0] if result_files else None
        if matched == current_value:
            return options, dash.no_update
        return options, matched

    def _format_result_label(self, result_file: str) -> str:
        """Shorten a result path relative to the results root.

        Args:
            result_file: Result file path to format.

        Returns:
            Relative path when under the results root, else the full path.
        """

        return format_result_label(result_file, self._results_root)

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
        selected_x_variables: Sequence[str | Sequence[str] | None],
        selected_y_variables: Sequence[str | Sequence[str] | None],
    ) -> List[go.Figure]:
        """Build figures for each graph based on selected variables.

        Args:
            selected_x_variables: List of x-axis selections per graph cell.
            selected_y_variables: List of y-axis selections per graph cell.

        Returns:
            A list of Plotly figures aligned with the grid inputs.
        """

        figures = []
        for selected_x, selected_variable in zip_longest(
            selected_x_variables, selected_y_variables, fillvalue=None
        ):
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
                x_variable = (
                    selected_x if isinstance(selected_x, str) and selected_x in self._data.columns else "time"
                )
                figures.append(px.line(self._data, x=x_variable, y=selected_variable))
        return figures

    def _build_graph_grid(
        self,
        _,
        selected_result: str,
        rows: int,
        cols: int,
        current_x_selections=None,
        current_y_selections=None,
    ):
        """Create a grid of graph containers.

        Args:
            _: Unused callback input from Dash.
            selected_result: Selected result file path.
            rows: Number of grid rows.
            cols: Number of grid columns.
            current_x_selections: Prior x-dropdown values in row-major order.
            current_y_selections: Prior y-dropdown values in row-major order.
                Selections still present in the new CSV are kept; only axes
                with no overlap fall back to the default.

        Returns:
            A list of row containers for the grid.
        """

        self._load_results(selected_result)
        graph_grid = GraphGridBuilder(self._variable_columns)
        preserved_x = current_x_selections if current_x_selections else None
        preserved_y = current_y_selections if current_y_selections else None
        graph_grid.build_grid(_, rows, cols, preserved_x_values=preserved_x, preserved_y_values=preserved_y)
        return graph_grid.get_grid()

    @staticmethod
    def _build_grid_controls():
        """Build the grid controls container.

        Returns:
            The Dash controls container.
        """

        grid_controls = GridControlBuilder()
        grid_controls.build_controls()
        controls = grid_controls.get_controls()
        if controls is None:
            raise RuntimeError("Grid controls were not built.")
        return controls
