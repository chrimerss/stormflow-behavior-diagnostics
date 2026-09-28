function y = nansum(x)
  % MATLAB Statistics Toolbox nansum for vectors.
  x(isnan(x)) = 0;
  y = sum(x);
end
