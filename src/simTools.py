import hydra_zen

import sessionConfig
import sessionTools


def simulate(config: sessionConfig.SimulationRun):
    director: sessionTools.SessionDirector = hydra_zen.instantiate(config.session)
    session = director.make_session()
    session.simulate(model_name=config.model_name)
    return session.get_solutions()