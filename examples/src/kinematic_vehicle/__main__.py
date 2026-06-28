import hydra
from hydra.core.hydra_config import HydraConfig
import kinematic_vehicle.experiments
import kinematic_vehicle.kinematic_vehicle

import mtools.session_config as session_config
import mtools.sim_tools as sim_tools


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: session_config.SimulationRun):
    sim_tools.save_solutions(sim_tools.simulate(config), HydraConfig.get().runtime.output_dir)


if __name__ == "__main__":
    kinematic_vehicle.kinematic_vehicle.registry.add_to_hydra_store()
    main()
