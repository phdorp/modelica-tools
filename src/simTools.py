import hydra_zen

import sessionConfig
import sessionTools


def simulate(config: sessionConfig.Session):
    director: sessionTools.SessionDirector = hydra_zen.instantiate(config)
    session = director.make_session()
    session.simulate()
    return session.get_solutions()