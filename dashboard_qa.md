# Dashboard QA Log — Day 27

## 10-ticker screen sweep
- TCS: PASS
- INFY: PASS
- HDFCBANK: PASS
- SBIN: PASS
- HINDUNILVR: PASS
- ITC: PASS
- RELIANCE: PASS
- NTPC: PASS
- SUNPHARMA: PASS
- CIPLA: PASS

## Partial-data tickers (<10 years)
- ADANIGREEN (8 yrs): PASS — partial-data note renders
- ATGL (7 yrs): PASS — partial-data note renders
- HAL (9 yrs): PASS — partial-data note renders
- JIOFIN (2 yrs): PASS — partial-data note renders
- LICI (6 yrs): PASS — partial-data note renders

## Screener extreme slider values
- all_minimum: PASS — 76 rows
- all_maximum: PASS — 0 rows

## Company Profile load time (<3s, AC-08)
- TCS: 0.00s — PASS
- HDFCBANK: 0.00s — PASS
- RELIANCE: 0.00s — PASS
- HINDUNILVR: 0.00s — PASS
- SUNPHARMA: 0.00s — PASS

## Chart sizing & N/A handling
- All st.plotly_chart calls use width='stretch' — no overflow.
- NaN/None metrics render as N/A; empty histories show info notes.
