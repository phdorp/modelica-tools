import hydra_zen
import simTools
import kinematicVehicle.configs.kinematicVehicle

store = hydra_zen.ZenStore()
store(kinematicVehicle.configs.kinematicVehicle.session_default, name="default")


if __name__ == "__main__":
    hydra_zen.store.add_to_hydra_store()
    hydra_zen.zen(simTools.simulate).hydra_main(config_name="default",
                                  version_base="1.1",
                                  config_path=".",
                                  )