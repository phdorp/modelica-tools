package FmuTests "Models the FMU tests export and run"
  model Decay "Exponential decay with a sampled counter and a Boolean"
    parameter Real k = 1;
    parameter Real x0 = 1;
    Real x(start = x0, fixed = true);
    Integer count;
    Boolean positive;
  initial equation
    count = 0;
  equation
    der(x) = -k*x;
    when sample(0.25, 0.25) then
      count = pre(count) + 1;
    end when;
    positive = x > 0.5;
    annotation(experiment(StopTime = 1, Interval = 0.01));
  end Decay;

  model Protected "Decay plus protected variables"
    extends Decay;
  protected
    Real hidden = 2*x;
    parameter Real hp = 3;
  end Protected;

  model Sampled "A counter incremented by time events"
    Integer count(start = 0);
  equation
    when sample(0.1, 0.1) then
      count = pre(count) + 1;
    end when;
    annotation(experiment(StopTime = 1));
  end Sampled;

  model Warns "Decay plus a state without a start value, so translation warns"
    extends Decay;
    Real y;
  equation
    der(y) = 1;
  end Warns;

  model Params "One parameter of each type, an array, a calculated parameter and a constant"
    type Mode = enumeration(low, high);
    parameter Real k = 1;
    parameter Integer n = 2;
    parameter Boolean on = true;
    parameter String label = "a";
    parameter Mode mode = Mode.low;
    parameter Real y0[2] = {1, 2};
    parameter Real twice = 2*k;
    constant Real c = 3;
    Real x(start = y0[1], fixed = true);
    Real total "Uses every parameter, so none is removed";
  equation
    der(x) = -k*x;
    total = n + y0[2] + twice + c + (if on then 1 else 0) + (if mode == Mode.high then 1 else 0)
      + (if label == "a" then 1 else 0);
  end Params;
end FmuTests;
