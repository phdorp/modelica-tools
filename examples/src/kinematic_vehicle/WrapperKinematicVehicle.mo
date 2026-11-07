within kinematic_vehicle;

block WrapperKinematicVehicle
  parameter Real v_norm = 10 "velocity";
  parameter Real phi = 0.1 "steering angle";
  parameter Real wheelbase = 2 "wheelbase";

  KinematicVehicle vehicle(wheelbase=wheelbase);

equation
  vehicle.v_norm = v_norm;
  vehicle.phi = phi;
end WrapperKinematicVehicle;