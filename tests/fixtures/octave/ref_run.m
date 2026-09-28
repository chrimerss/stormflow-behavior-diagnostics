function ref_run(rain, flow, time, rain_min, max_window, outprefix, multiple)
  if nargin < 7, multiple = 1; end
  % Run the reference DMCA-ESR code step by step (same sequence as
  % EVENT_IDENTIFICATION_DMCA.m) and dump intermediates, then run the
  % top-level function itself and EVENT_ANALYSIS (flag=0, multiple=1).
  w = @(name, v) dlmwrite([outprefix '_' name '.txt'], v(:), 'precision', '%.17g');
  [Tr, fr, ff, fb] = STEP1_STEP2_Tr_and_fluctuations_timeseries(rain, flow, rain_min, max_window);
  w('Tr', Tr); w('fluct_rain_Tr', fr); w('fluct_flow_Tr', ff);
  [bc, ec] = STEP3_core_identification(fb);
  w('beginning_core', bc); w('end_core', ec);
  er = STEP4_end_rain_events(bc, ec, rain, fr, rain_min); w('end_rain', er);
  br = STEP5_beginning_rain_events(bc, er, rain, fr, rain_min); w('beginning_rain', br);
  [brc, erc] = STEP6_checks_on_rain_events(br, er, rain, rain_min); w('brc', brc); w('erc', erc);
  ef = STEP7_end_flow_events(brc, erc, bc, ec, flow, fr, ff, Tr); w('end_flow', ef);
  bf = STEP8_beginning_flow_events(brc, erc, ef, bc, fr, ff); w('beginning_flow', bf);
  [bru, eru, bfu, efu] = STEP9_checks_on_flow_events(brc, erc, bf, ef, ff);
  w('bru', bru); w('eru', eru); w('bfu', bfu); w('efu', efu);
  [BR, ER, BF, EF] = EVENT_IDENTIFICATION_DMCA(rain, flow, time, rain_min, max_window);
  idx = @(t) arrayfun(@(x) find(time == x), t);
  events = [idx(BR(:)), idx(ER(:)), idx(BF(:)), idx(EF(:))];  % 1-based
  dlmwrite([outprefix '_events.txt'], events, 'precision', '%d');
  baseflow = BASEFLOW_CURVE(BF, EF, flow, time); w('baseflow', baseflow);
  [DR, VR, DQ, VQ, RR] = EVENT_ANALYSIS(BR, ER, BF, EF, rain, flow, time, 0, multiple);
  dlmwrite([outprefix '_analysis.txt'], [VR(:), VQ(:), RR(:)], 'precision', '%.17g');
end
