import dash
from dash import html, dcc, Output, Input, State, ALL
from dash.html.Base import ComponentSingleType
from typing import Any, Sequence, List
import plotly.express as px
import pandas as pd


class DashBuilder:
    def __init__(self, name: str, data: pd.DataFrame):
        self._app = dash.Dash(name)
        self._layout: List[ComponentSingleType] = []
        self._data: pd.DataFrame = data
        self._variable_columns = [column for column in data.columns if column != "time"]

    def build_grid_controls(self):
        self._layout.append(self._build_grid_controls())
        self._layout.append(html.Div(id="graphs-grid"))

    def build_graph_grid(self):
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
        self._layout.append(html.H1(title))

    def get_app(self):
        self._app.layout = html.Div(children=self._layout)
        return self._app

    def _update_graph_callback(self, selected_variables):
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
        return [
            html.Div(
                children=[
                    html.Div(
                        children=[
                            dcc.Dropdown(
                                [{"label": column, "value": column} for column in self._variable_columns],
                                id={"type": "variable-dropdown", "row": row, "col": col},
                                value=self._variable_columns[:1],
                                multi=True,
                            ),
                            dcc.Graph(id={"type": "graph", "row": row, "col": col}),
                        ],
                        style={"border": "1px solid #ccc", "padding": "8px"},
                    )
                    for col in range(cols)
                ],
                style={"display": "grid", "gridTemplateColumns": f"repeat({cols}, 1fr)", "gap": "12px"},
            )
            for row in range(rows)
        ]

    @staticmethod
    def _build_grid_controls():
        return html.Div(
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
