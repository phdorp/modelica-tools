import hydra_zen
import models.kinematicVehicle as kinematicVehicle


@hydra_zen.store(name="my_app", director=kinematicVehicle.session_default)
def simulate(director):
    director.make_session().simulate()

if __name__ == "__main__":
    hydra_zen.store.add_to_hydra_store()
    hydra_zen.zen(simulate).hydra_main(config_name="my_app",
                                  version_base="1.1",
                                  config_path=".",
                                  )