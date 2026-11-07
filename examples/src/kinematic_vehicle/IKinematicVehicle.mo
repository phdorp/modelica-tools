within kinematic_vehicle;

partial model IKinematicVehicle
  input Real v_norm "velocity";
  input Real phi "steering angle";
  output Real px "x position";
  output Real py "y position";
  output Real theta "heading angle";
end IKinematicVehicle;