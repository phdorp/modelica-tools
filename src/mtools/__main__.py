"""CLI entry point for visualizing Modelica result CSV files."""

import argparse
from pathlib import Path

from mtools.internal.plot_tools import DashBuilder, find_results


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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run the Dash server in debug mode.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the visualization app."""

    args = parse_args()
    result_files = find_results(args.results_dir)
    if not result_files:
        raise FileNotFoundError(f"No .csv results found under: {args.results_dir}")

    selected_result = result_files[0]

    results_dir_path = Path(args.results_dir).resolve()
    title = results_dir_path.name or results_dir_path.as_posix()
    builder = DashBuilder(__name__)
    builder.build_title(title)
    builder.build_result_select(
        result_files=result_files,
        selected_result=selected_result,
        results_root=args.results_dir,
    )
    builder.build_grid_controls()
    builder.build_graph_grid()
    app = builder.get_app()
    app.run(debug=args.debug)


if __name__ == "__main__":
    main()
