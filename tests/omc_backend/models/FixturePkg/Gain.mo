within FixturePkg;
function Gain "Scales with the C include"
  input Real u;
  output Real y;
external "C" y = fixture_gain(u)
  annotation(Include = "#include \"fixture_gain.h\"", IncludeDirectory = "modelica://FixturePkg/Resources/Include");
end Gain;
