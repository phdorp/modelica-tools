model VariantsBase
  parameter Real inh = 1 annotation(Evaluate = true);
  Real xb(start = 0, fixed = true);
equation
  der(xb) = inh;
end VariantsBase;

model VariantsSub
  parameter Real m = 1 annotation(Evaluate = true);
  parameter Real free = 1;
end VariantsSub;

model Variants "Parameters OMC fixes at build time, and some it does not"
  extends VariantsBase;
  type Mode = enumeration(low, high);
  parameter Integer n = 2;
  parameter Real y[n] = ones(n);
  parameter Boolean sel = false;
  parameter Mode mode = Mode.low;
  parameter Real loc = 3 annotation(Evaluate = true);
  parameter Real a[2] = {1, 2} annotation(Evaluate = true);
  parameter Real mm[2, 2] = {{1, 2}, {3, 4}} annotation(Evaluate = true);
  parameter String label = "a" annotation(Evaluate = true);
  final parameter Real fixedValue = 5;
  parameter Real k = 1;
  VariantsSub sub;
  Real sumY = sum(y);
  Real selected;
  Real modeValue;
  Real localOut = loc;
  Real aOut = a[1] * 10 + a[2];
  Real mmOut = mm[1, 2] * 10 + mm[2, 1];
  Real subOut = sub.m + sub.free * 100;
  Real kOut = k * time;
protected
  parameter Real hidden = 2 annotation(Evaluate = true);
equation
  if sel then
    selected = 1;
  else
    selected = 2;
  end if;
  if mode == Mode.high then
    modeValue = 1;
  else
    modeValue = 2;
  end if;
  annotation(experiment(StartTime = 0, StopTime = 2, Interval = 0.5, Tolerance = 1e-8));
end Variants;
