# Sprint 3 Retrospective (Days 15-21)

## Delivered
- src/screener/engine.py — 18 filters, 6 presets, composite score (25.1 weights, sector-relative winsorisation)
- output/screener_output.xlsx — 6 colour-coded sheets; output/peer_comparison.xlsx — 11 sheets
- reports/radar_charts/ — 92 PNGs with peer/Nifty-100 overlay
- src/analytics/peer.py + peer_percentiles table — 11 groups, 10 metrics
- 14 DQ rule tests + screener/peer unit tests — all green

## Exit criteria
- [x] 6 presets within 5-50 companies (verify_sprint3.py)
- [x] Quality Compounder top-5 manually reviewed — ROE > 15%, D/E < 1 holds
- [x] IT Services & FMCG: highest ROE = highest percentile rank
- [x] 14/14 DQ tests pass
- [x] Demoed screener_output.xlsx + peer_comparison.xlsx to team lead

## Issues / carry-forward
- Turnaround Watch near lower band — monitor after D/E declining flag tuning
- 46/92 companies lack peer groups — radar falls back to Nifty 100 avg (R-10 accepted)