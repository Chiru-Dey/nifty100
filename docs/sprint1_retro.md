# Sprint 1 Retrospective — Days 01–07

## Exit criteria

| Gate | Result | Status |
| --- | --- | --- |
| SELECT COUNT(*) FROM companies = 92 | 92 | PASS |
| PRAGMA foreign_key_check = 0 rows | 0 | PASS |
| load_audit.csv zero CRITICAL | 0 critical | PASS |
| 35+ ETL unit tests pass | 55 passed (43 ETL + 12 DQ) | PASS |
| Manual review 5 companies | docs/dq_review_notes.md | PASS |
| 12 files loaded | load_audit.csv 12 rows | PASS |

## Loaded row counts (rows_in -> rows_out)

companies 92->92; profitandloss 1276->1070; balancesheet 1312->1140;
cashflow 1187->1056; analysis 20->20; documents 1585->1585; prosandcons 16->16;
sectors 92->92; stock_prices 5520->5520; market_cap 552->552;
financial_ratios 1184->1184; peer_groups 56->56.

## Findings

- 103 P&L + 5 BS parse rejections: TTM and partial periods ("Mar 2023 15", "Mar 2016 9m") — correct per DQ-07 (annual rows only).
- DQ-02 dedup removed duplicate (company_id, year) rows: P&L 103, BS 167, CF 131.
- Coverage gaps confirmed: analysis ~8 companies, prosandcons ~8, documents ~82%.
- DQ-16 flags <5yr companies; exclude from CAGR in Sprint 2.
- validation_failures.csv holds WARNING/INFO only (DQ-05 rounding, DQ-15 strict balance, DQ-16 coverage).

## Issues fixed during sprint

- analysis.xlsx has multiple rows per company -> PK moved to row id.
- Supplementary files carry redundant id column -> dropped at load.
- PyPI jupyter metapackage frozen at 1.x -> replaced with notebook>=7.0.
- Black safety check on py3.12 -> target-version py312.
- Empty float Series + str concat crash in DQ-04 -> .astype(str).

## Carry into Sprint 2

- Ratio Engine must apply INSUFFICIENT flag for <5yr histories and bank/NBFC carve-outs.
- financial_ratios currently holds screener-supplied values; D12 overwrites with computed values.