model Backend "One variable of each kind the backend reads back"
  type Mode = enumeration(low, high);
  model Sub
    parameter Real gain = 1;
  end Sub;
  parameter Real k = 2 "decay rate";
  parameter Real y0[2] = {1, 2};
  parameter Real m[2, 2] = {{1, 2}, {3, 4}};
  parameter Boolean flip = false;
  parameter Integer offset = 0;
  Sub sub;
  Real x(start = 1, fixed = true);
  Real negx = -x;
  Real v[2] = y0 * time;
  Real g = sub.gain * time;
  Real mm = m[1, 2] * time;
  Real s = if flip then -time else time;
  Integer count(start = 0, fixed = true);
  Boolean late = time > 0.55;
  Mode mode = if late then Mode.high else Mode.low;
protected
  parameter Real twice = 2;
  Real hidden = twice * x;
equation
  der(x) = -k * x;
  when time > 0.25 then
    count = pre(count) + 1 + offset;
  end when;
  annotation(experiment(StartTime = 0, StopTime = 1, Interval = 0.1, Tolerance = 1e-8));
end Backend;
