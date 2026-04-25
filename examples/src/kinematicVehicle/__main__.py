import hydra
import kinematicVehicle.kinematicVehicle

import sessionConfig
import simTools


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: sessionConfig.SimulationRun):
    return simTools.simulate(config)


if __name__ == "__main__":
    kinematicVehicle.kinematicVehicle.store.add_to_hydra_store()
    main()
