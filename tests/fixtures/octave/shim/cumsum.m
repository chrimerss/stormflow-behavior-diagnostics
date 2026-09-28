function y = cumsum(x, varargin)
  % MATLAB-compatible 'omitnan' flag for Octave: NaN contributes zero.
  if numel(varargin) > 0 && ischar(varargin{end}) && strcmpi(varargin{end}, 'omitnan')
    x(isnan(x)) = 0;
    varargin(end) = [];
  end
  y = builtin('cumsum', x, varargin{:});
end
