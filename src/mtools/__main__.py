import pandas as pd

from plotTools import DashBuilder

data = pd.read_csv("/workspaces/modelica-tools/examples/outputs/2026-05-15/13-19-33/KinematicVehicle.csv")

builder = DashBuilder(__name__, data)
builder.build_title("Kinematic Vehicle Data")
builder.build_grid_controls()
builder.build_graph_grid()
app = builder.get_app()

if __name__ == "__main__":
    app.run(debug=True)
