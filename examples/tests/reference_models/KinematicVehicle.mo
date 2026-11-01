within reference_models;

model KinematicVehicle
  parameter Real v_norm = 10 "velocity";
  parameter Real phi = 0.1 "steering angle";
  parameter Real l = 2 "wheelbase";
  parameter State state_0 = State(px=0, py=0, theta=0) "initial state";

  State state(px(start=state_0.px, fixed=true), py(start=state_0.py, fixed=true), theta(start=state_0.theta, fixed=true));
  Input control(v_norm=v_norm, phi=phi);

protected
  Real px_dot = der(state.px);
  Real py_dot = der(state.py);
  Real theta_dot = der(state.theta);

equation
  px_dot = v_norm * cos(state.theta);
  py_dot = v_norm * sin(state.theta);
  theta_dot = v_norm / l * tan(control.phi);
end KinematicVehicle;
