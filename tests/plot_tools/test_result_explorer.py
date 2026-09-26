from pathlib import Path

import dash

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
