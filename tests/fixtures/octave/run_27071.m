% example.m without plotting, from the reference repository
addpath('shim'); addpath(REFDIR);
rain_original = dlmread(fullfile(REFDIR, 'daily_rainfall_27071.txt'));
flow_original = dlmread(fullfile(REFDIR, 'daily_flow_27071.txt'));
multiple = 24;
rain = rain_original(:,7)./multiple;
flow = flow_original(:,7)./multiple;
time = datenum(rain_original(:,1:6));
printf('NaN in flow: %d\n', sum(isnan(flow)));
ref_run(rain, flow, time, 0.02, 100, 'out/ex27071');
% same data, example.m analysis with multiple=24
[BR, ER, BF, EF] = EVENT_IDENTIFICATION_DMCA(rain, flow, time, 0.02, 100);
[DR, VR, DQ, VQ, RR] = EVENT_ANALYSIS(BR, ER, BF, EF, rain, flow, time, 0, multiple);
dlmwrite('out/ex27071_analysis_example.txt', [DR(:), VR(:), DQ(:), VQ(:), RR(:)], 'precision', '%.17g');
printf('events: %d\n', numel(BR));
