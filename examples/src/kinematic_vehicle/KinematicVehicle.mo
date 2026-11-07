within kinematic_vehicle;

model KinematicVehicle
  extends IKinematicVehicle;
  parameter Real wheelbase = 2 "wheelbase";

protected
  Real px_dot = der(px);
  Real py_dot = der(py);
  Real theta_dot = der(theta);

equation
  px_dot = v_norm * cos(theta);
  py_dot = v_norm * sin(theta);
  theta_dot = v_norm / wheelbase * tan(phi);

initial equation
  px = 0;
  py = 0;
  theta = 0;
end KinematicVehicle;