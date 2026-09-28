function y = nanmin(x)
  % Octave min already ignores NaN.
  y = min(x);
end
