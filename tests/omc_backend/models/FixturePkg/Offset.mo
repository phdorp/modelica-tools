within FixturePkg;
function Offset "Adds the offset from the static library"
  input Real u;
  output Real y;
external "C" y = fixture_offset(u)
  annotation(Include = "#include \"fixture_offset.h\"", IncludeDirectory = "modelica://FixturePkg/Resources/Include",
    Library = "fixture", LibraryDirectory = "modelica://FixturePkg/Resources/Library");
end Offset;
