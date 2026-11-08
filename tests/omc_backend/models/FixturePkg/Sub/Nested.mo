within FixturePkg.Sub;
model Nested "Uses a sibling file of the parent package"
  Real a = FixturePkg.Gain(time);
end Nested;
