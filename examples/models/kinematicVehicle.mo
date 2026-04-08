record State
  Real px;
  Real py;
  Real theta;
end State;

record Input
  Real v_norm;
  Real phi;
end Input;

model KinematicVehicle
  parameter Real v_norm = 10 "velocity";
  parameter Real phi = 0.1 "steering angle";
  parameter Real l = 2 "wheelbase";
  parameter State state_0 = State(px=0, py=0, theta=0) "initial state";

  State state(px(start=state_0.px), py(start=state_0.py), theta(start=state_0.theta));
  Input control(v_norm=v_norm, phi=phi);
equation
  der(state.px) = v_norm * cos(state.theta);
  der(state.py) = v_norm * sin(state.theta);
  der(state.theta) = v_norm / l * tan(control.phi);
end KinematicVehicle;