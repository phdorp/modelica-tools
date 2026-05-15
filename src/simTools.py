import hydra_zen
import pandas
from hydra.core.hydra_config import HydraConfig

import sessionConfig
import sessionTools


def simulate(config: sessionConfig.SimulationRun):
    """Run a configured simulation session and persist all solution tables.

    Args:
        config: Simulation run configuration including session factory settings
            and the model name to simulate.

    Returns:
        Mapping of solution names to simulation result data frames.
    """
    director: sessionTools.SessionDirector = hydra_zen.instantiate(config.session)
    session = director.make_session()
    session.simulate(model_name=config.model_name)
    solutions = session.get_solutions()
    save_solutions(solutions, HydraConfig.get().runtime.output_dir)
    return solutions

def save_solutions(solutions: dict[str, pandas.DataFrame], output_path: str):
    """Write each solution data frame to CSV in the configured output path.

    Args:
        solutions: Mapping of solution names to pandas data frames.
        output_path: Directory path where CSV files are written.
    """
    for name, solution in solutions.items():
        solution.to_csv(f"{output_path}/{name}.csv", index=False)
