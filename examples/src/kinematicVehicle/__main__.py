import hydra
import hydra_zen
import simTools
import sessionConfig
import kinematicVehicle.configs.kinematicVehicle

store = hydra_zen.ZenStore()
store(kinematicVehicle.configs.kinematicVehicle.session_default, name="default")


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: sessionConfig.Session):
    return simTools.simulate(config)


if __name__ == "__main__":
    store.add_to_hydra_store()
    main()
