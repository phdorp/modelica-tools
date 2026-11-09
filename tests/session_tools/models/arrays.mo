model Arrays
  parameter Real y[2] = {1, 2};
  parameter Real m[2, 2] = {{1, 2}, {3, 4}};
  Real s(start = 0, fixed = true);
  Real t(start = 0, fixed = true);
equation
  der(s) = y[1] + 10 * y[2];
  der(t) = m[1, 2] + 10 * m[2, 1];
end Arrays;
