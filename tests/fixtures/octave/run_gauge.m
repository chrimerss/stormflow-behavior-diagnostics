% Reference DMCA-ESR on one of the authors' gauges, following example.m:
% columns datenum, P, Q in mm/day; divided by 24 (mm/h); rain_min 0.05 mm/h;
% max_window 16; EVENT_ANALYSIS with multiple=24.
addpath('shim'); addpath(REFDIR);
d = dlmread(INFILE, ',', 1, 0);
time = d(:,1); multiple = 24;
rain = d(:,2)./multiple; flow = d(:,3)./multiple;
printf('%s: n=%d NaN(P)=%d NaN(Q)=%d\n', OUTPREFIX, numel(time), sum(isnan(rain)), sum(isnan(flow)));
ref_run(rain, flow, time, 0.05, 16, OUTPREFIX, multiple);
