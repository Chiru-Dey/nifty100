# DQ Review Notes — Day 06

Sampled companies: SUNPHARMA, BAJFINANCE, ADANIGREEN, HAL, EICHERMOT

## Year coverage (sample)
        table company_id  years
profitandloss     JIOFIN      2
 balancesheet     JIOFIN      3
     cashflow     JIOFIN      2

        table             column  nulls
profitandloss              sales      0
profitandloss         net_profit      0
profitandloss                eps      4
 balancesheet       total_assets      0
 balancesheet  total_liabilities      0
 balancesheet       fixed_assets      0
     cashflow operating_activity      2
     cashflow      net_cash_flow      2

company_id    year  src_sales  db_sales  match
 SUNPHARMA 2024-03      48497   48497.0   True
BAJFINANCE 2024-03      54972   54972.0   True
ADANIGREEN 2024-03       9220    9220.0   True
       HAL 2024-03      30381   30381.0   True
 EICHERMOT 2024-03      16536   16536.0   True

                       profitandloss  balancesheet  cashflow
pct_companies_ge_10yr           95.7          95.6      93.4


## Loader bugs

None found. Re-run idempotent; row counts unchanged.
