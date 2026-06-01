import hydra
import kinematic_vehicle.experiments
import kinematic_vehicle.kinematic_vehicle

import mtools.session_config as session_config
import mtools.sim_tools as sim_tools


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: session_config.SimulationRun):
    return sim_tools.simulate(config)


if __name__ == "__main__":
    kinematic_vehicle.kinematic_vehicle.registry.add_to_hydra_store()
    main()
