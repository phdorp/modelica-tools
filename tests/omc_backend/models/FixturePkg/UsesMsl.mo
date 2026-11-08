within FixturePkg;
model UsesMsl "Uses the MSL without listing it"
  Modelica.Blocks.Sources.Ramp r(height = 2, duration = 1);
  Real y = r.y;
end UsesMsl;
