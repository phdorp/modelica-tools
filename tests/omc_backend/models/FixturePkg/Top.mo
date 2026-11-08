within FixturePkg;
model Top "Uses C code from the include and from the library"
  Real a = Gain(time);
  Real b = Offset(time);
end Top;
