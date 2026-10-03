from pathlib import Path

import dash
import pandas as pd

from mtools.internal.plot_tools import DashBuilder, ResultSelectBuilder


def _find_by_id(component, target_id: str):
    """Recursively find a Dash component by id."""
    component_id = getattr(component, "id", None)
    if component_id == target_id:
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_by_id(child, target_id)
            if found is not None:
                return found
    elif children is not None:
        return _find_by_id(children, target_id)
    return None


class TestResultExplorerButton:
    def test_select_contains_rescan_button_next_to_dropdown(self, tmp_path: Path):
        result_file = tmp_path / "a.csv"
        result_file.write_text("time,value\n0,1\n")

        builder = ResultSelectBuilder([str(result_file)], results_root=tmp_path)
        builder.build_select()
        select = builder.get_select()

        assert select is not None
        dropdown = _find_by_id(select, "result-select")
        button = _find_by_id(select, "rescan-results")

        assert dropdown is not None
        assert button is not None
        assert getattr(button, "children", None) is not None

    def test_build_result_explorer_defaults_to_cwd(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.csv").write_text("time,value\n0,1\n")

        app_builder = DashBuilder(__name__)
        app_builder.build_result_select(
            result_files=[],
            selected_result=None,
            results_root=None,
        )
        app_builder.build_result_explorer()

        assert app_builder._results_root == Path.cwd()

    def test_refresh_discovers_new_files(self, tmp_path: Path):
        first = tmp_path / "a.csv"
        first.write_text("time,value\n0,1\n")

        app_builder = DashBuilder(__name__)
        app_builder.build_result_select(
            result_files=[str(first)],
            selected_result=str(first),
            results_root=tmp_path,
        )
        app_builder.build_result_explorer(results_root=tmp_path)

        second = tmp_path / "sub" / "b.csv"
        second.parent.mkdir(parents=True)
        second.write_text("time,value\n0,2\n")

        options, value = app_builder._refresh_results(1, str(first))

        values = [option["value"] for option in options]
        assert values == [str(first), str(second)]
        # Existing selection is preserved via no_update, leaving graphs untouched.
        assert value is dash.no_update

    def test_refresh_falls_back_when_selected_removed(self, tmp_path: Path):
        first = tmp_path / "a.csv"
        first.write_text("time,value\n0,1\n")
        second = tmp_path / "b.csv"
        second.write_text("time,value\n0,2\n")

        app_builder = DashBuilder(__name__)
        app_builder.build_result_select(
            result_files=[str(first), str(second)],
            selected_result=str(first),
            results_root=tmp_path,
        )
        app_builder.build_result_explorer(results_root=tmp_path)

        first.unlink()
        options, value = app_builder._refresh_results(1, str(first))

        assert [option["value"] for option in options] == [str(second)]
        assert value == str(second)

    def test_refresh_preserves_relative_selection_after_absolute_rescan(
        self, tmp_path: Path, monkeypatch
    ):
        from mtools.internal.plot_tools import find_results

        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.csv").write_text("time,value\n0,1\n")
        sub_b = tmp_path / "sub" / "b.csv"
        sub_b.parent.mkdir(parents=True)
        sub_b.write_text("time,value\n0,2\n")

        relative_files = find_results(".")
        relative_selected = relative_files[1]
        assert relative_selected != str(sub_b)

        app_builder = DashBuilder(__name__)
        app_builder.build_result_select(
            result_files=relative_files,
            selected_result=relative_selected,
            results_root=".",
        )
        app_builder.build_result_explorer()

        options, value = app_builder._refresh_results(1, relative_selected)

        values = [option["value"] for option in options]
        assert values == [str(tmp_path / "a.csv"), str(sub_b)]
        assert value == str(sub_b)


def _x_dropdown_values(grid):
    """Collect x-variable-dropdown values from a built grid in row-major order."""
    values = []
    for row in grid:
        cells = row.children if isinstance(row.children, (list, tuple)) else [row.children]
        for cell in cells:
            children = cell.children if isinstance(cell.children, (list, tuple)) else []
            dropdown = children[0]
            values.append(dropdown.value)
    return values


def _y_dropdown_values(grid):
    """Collect variable-dropdown values from a built grid in row-major order."""
    values = []
    for row in grid:
        cells = row.children if isinstance(row.children, (list, tuple)) else [row.children]
        for cell in cells:
            children = cell.children if isinstance(cell.children, (list, tuple)) else []
            dropdown = children[1]
            values.append(dropdown.value)
    return values


class TestGraphGridPreservesSelections:
    def test_keeps_available_variables_when_csv_changes(self, tmp_path: Path):
        new_file = tmp_path / "new.csv"
        new_file.write_text("time,a,c\n0,1,2\n1,3,4\n")

        app_builder = DashBuilder(__name__)
        grid = app_builder._build_graph_grid(
            0, str(new_file), 1, 1, current_x_selections=["a"], current_y_selections=[["a", "b"]]
        )

        assert _x_dropdown_values(grid) == ["a"]
        assert _y_dropdown_values(grid) == [["a"]]

    def test_resets_only_missing_variables_to_default(self, tmp_path: Path):
        new_file = tmp_path / "new.csv"
        new_file.write_text("time,a,c\n0,1,2\n1,3,4\n")

        app_builder = DashBuilder(__name__)
        grid = app_builder._build_graph_grid(
            0,
            str(new_file),
            1,
            2,
            current_x_selections=["z", None],
            current_y_selections=[["a", "b"], ["b"]],
        )

        assert _x_dropdown_values(grid) == ["time", "time"]
        assert _y_dropdown_values(grid) == [["a"], ["a"]]

    def test_defaults_x_to_time(self, tmp_path: Path):
        new_file = tmp_path / "new.csv"
        new_file.write_text("time,a,c\n0,1,2\n1,3,4\n")

        app_builder = DashBuilder(__name__)
        grid = app_builder._build_graph_grid(0, str(new_file), 1, 2)

        assert _x_dropdown_values(grid) == ["time", "time"]


class TestGraphUpdates:
    def test_supports_signal_vs_signal_plots(self):
        app_builder = DashBuilder(__name__)
        app_builder._set_data(pd.DataFrame({"time": [0, 1], "phi": [10, 20], "w": [2, 3]}))

        figure = app_builder._update_graph_callback(["phi"], [["w"]])[0]

        assert list(figure.data[0].x) == [10, 20]
        assert list(figure.data[0].y) == [2, 3]
