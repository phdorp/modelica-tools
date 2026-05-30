"""CLI entry point for visualizing Modelica result CSV files."""

import argparse
from pathlib import Path

import pandas as pd

from plotTools import DashBuilder, find_results


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments containing the results_dir.
    """

    parser = argparse.ArgumentParser(description="Visualize Modelica result CSV files.")
    parser.add_argument(
        "results_dir",
        nargs="?",
        default=str(Path.cwd()),
        help="Directory to search for result CSV files (default: current working directory).",
    )
    return parser.parse_args()


def main() -> None:
    """Run the visualization app."""

    args = parse_args()
    result_files = find_results(args.results_dir)
    if not result_files:
        raise FileNotFoundError(f"No .csv results found under: {args.results_dir}")

    selected_result = result_files[0]
    data = pd.read_csv(selected_result)

    builder = DashBuilder(__name__, data, result_files=result_files, selected_result=selected_result)
    builder.build_title("Kinematic Vehicle Data")
    builder.build_result_select()
    builder.build_grid_controls()
    builder.build_graph_grid()
    app = builder.get_app()
    app.run(debug=True)


if __name__ == "__main__":
    main()
