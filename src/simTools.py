import hydra_zen
import pandas
from hydra.core.hydra_config import HydraConfig

import sessionConfig
import sessionTools


def simulate(config: sessionConfig.SimulationRun):
    director: sessionTools.SessionDirector = hydra_zen.instantiate(config.session)
    session = director.make_session()
    session.simulate(model_name=config.model_name)
    solutions = session.get_solutions()
    save_solutions(solutions, HydraConfig.get().runtime.output_dir)
    return solutions

def save_solutions(solutions: dict[str, pandas.DataFrame], output_path: str):
    for name, solution in solutions.items():
        solution.to_csv(f"{output_path}/{name}.csv", index=False)