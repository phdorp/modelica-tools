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

  model SampledDecay "A decaying state and a counter incremented by time events, so CVODE runs with sample() events"
    Real x(start = 1, fixed = true);
    Integer count(start = 0);
  equation
    der(x) = -x;
    when sample(0.1, 0.1) then
      count = pre(count) + 1;
    end when;
    annotation(experiment(StopTime = 1));
  end SampledDecay;

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

  model BuildTime "Parameters OMC fixes at build time, a final and a protected parameter"
    parameter Integer n = 2;
    parameter Real y0[n] = fill(1, n) "Sized by n, but settable in a run";
    parameter Boolean useA = true annotation(Evaluate = true);
    final parameter Real f = 1;
    Real y[n](start = y0, each fixed = true);
    Real z;
  equation
    for i in 1:n loop
      der(y[i]) = -f*y[i];
    end for;
    if useA then
      z = 1;
    else
      z = 2;
    end if;
  protected
    parameter Real hp = 3;
  end BuildTime;

  model Segfault "Raises SIGSEGV once time passes 0.5"
    function crash
      input Real t;
      output Real y;
      external "C" y = fmu_tests_crash(t) annotation(
        Include = "#include <signal.h>\nstatic double fmu_tests_crash(double t) { raise(SIGSEGV); return t; }");
    end crash;
    Real x(start = 0, fixed = true);
    Real y;
  equation
    der(x) = 1;
    y = if time > 0.5 then crash(time) else 0;
    annotation(experiment(StopTime = 1, Interval = 0.01));
  end Segfault;

  model Hang "Loops forever once time passes 0.5"
    function spin
      input Real t;
      output Real y;
      external "C" y = fmu_tests_spin(t) annotation(
        Include = "static double fmu_tests_spin(double t) { volatile int stop = 0; while (!stop) {} return t; }");
    end spin;
    Real x(start = 0, fixed = true);
    Real y;
  equation
    der(x) = 1;
    y = if time > 0.5 then spin(time) else 0;
    annotation(experiment(StopTime = 1, Interval = 0.01));
  end Hang;

  model SlowThenHang "Sleeps 30 ms per sample until time passes 0.5, then loops forever"
    function slow
      input Real t;
      output Real y;
      external "C" y = fmu_tests_slow(t) annotation(
        Include = "#include <unistd.h>\nstatic double fmu_tests_slow(double t) { if (t <= 0.5) { usleep(30000); return t; } volatile int stop = 0; while (!stop) {} return t; }");
    end slow;
    Real x(start = 0, fixed = true);
    discrete Real y(start = 0, fixed = true);
  equation
    der(x) = 1;
    when sample(0, 0.01) then
      y = slow(time);
    end when;
    annotation(experiment(StopTime = 1));
  end SlowThenHang;

  model AssertFails "Decay that fails an assertion once time passes 0.5"
    extends Decay;
  equation
    assert(time < 0.5, "time passed 0.5");
  end AssertFails;

  model AssertWarns "Decay that warns through an assertion once time passes 0.5"
    extends Decay;
  equation
    assert(time < 0.5, "time passed 0.5", level = AssertionLevel.warning);
  end AssertWarns;

  model SqrtFails "Decay whose sqrt(x - 0.5) fails once x drops below 0.5; the FMU reports it through the FMI logger"
    extends Decay;
    Real y;
  equation
    y = sqrt(x - 0.5);
  end SqrtFails;
end FmuTests;
