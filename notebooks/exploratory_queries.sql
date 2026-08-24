-- Q1: row counts per table
SELECT 'companies' AS tbl, COUNT(*) AS rows FROM companies
UNION ALL SELECT 'profitandloss', COUNT(*) FROM profitandloss
UNION ALL SELECT 'balancesheet', COUNT(*) FROM balancesheet
UNION ALL SELECT 'cashflow', COUNT(*) FROM cashflow
UNION ALL SELECT 'analysis', COUNT(*) FROM analysis
UNION ALL SELECT 'documents', COUNT(*) FROM documents
UNION ALL SELECT 'prosandcons', COUNT(*) FROM prosandcons
UNION ALL SELECT 'sectors', COUNT(*) FROM sectors
UNION ALL SELECT 'stock_prices', COUNT(*) FROM stock_prices
UNION ALL SELECT 'market_cap', COUNT(*) FROM market_cap
UNION ALL SELECT 'financial_ratios', COUNT(*) FROM financial_ratios
UNION ALL SELECT 'peer_groups', COUNT(*) FROM peer_groups;

-- Q2: null audit on key numeric columns
SELECT 'profitandloss' AS tbl, 'sales' AS col, COUNT(*) AS nulls FROM profitandloss WHERE sales IS NULL
UNION ALL SELECT 'profitandloss', 'net_profit', COUNT(*) FROM profitandloss WHERE net_profit IS NULL
UNION ALL SELECT 'profitandloss', 'eps', COUNT(*) FROM profitandloss WHERE eps IS NULL
UNION ALL SELECT 'balancesheet', 'total_assets', COUNT(*) FROM balancesheet WHERE total_assets IS NULL
UNION ALL SELECT 'balancesheet', 'fixed_assets', COUNT(*) FROM balancesheet WHERE fixed_assets IS NULL
UNION ALL SELECT 'cashflow', 'operating_activity', COUNT(*) FROM cashflow WHERE operating_activity IS NULL;

-- Q3: year coverage per company across time-series tables
SELECT c.id,
       (SELECT COUNT(DISTINCT year) FROM profitandloss p WHERE p.company_id = c.id) AS pl_years,
       (SELECT COUNT(DISTINCT year) FROM balancesheet b WHERE b.company_id = c.id) AS bs_years,
       (SELECT COUNT(DISTINCT year) FROM cashflow f WHERE f.company_id = c.id) AS cf_years,
       (SELECT COUNT(DISTINCT Year) FROM documents d WHERE d.company_id = c.id) AS doc_years
FROM companies c
ORDER BY pl_years, c.id;

-- Q4: P&L year distribution
SELECT year, COUNT(*) AS rows, COUNT(DISTINCT company_id) AS companies
FROM profitandloss GROUP BY year ORDER BY year;

-- Q5: companies with <5yr P&L history (DQ-16)
SELECT company_id, COUNT(DISTINCT year) AS yrs
FROM profitandloss GROUP BY company_id HAVING yrs < 5;

-- Q6: AC-02 — % companies with >=10yr P&L history
SELECT ROUND(100.0 * SUM(yrs >= 10) / COUNT(*), 1) AS pct_ge_10yr
FROM (SELECT COUNT(DISTINCT year) AS yrs FROM profitandloss GROUP BY company_id);

-- Q7: duplicate annual PK scan (DQ-02)
SELECT 'profitandloss' AS tbl, company_id, year, COUNT(*) AS n FROM profitandloss GROUP BY company_id, year HAVING n > 1
UNION ALL SELECT 'balancesheet', company_id, year, COUNT(*) AS n FROM balancesheet GROUP BY company_id, year HAVING n > 1
UNION ALL SELECT 'cashflow', company_id, year, COUNT(*) AS n FROM cashflow GROUP BY company_id, year HAVING n > 1;

-- Q8: orphan FK scan (DQ-03)
SELECT 'profitandloss' AS tbl, company_id FROM profitandloss WHERE company_id NOT IN (SELECT id FROM companies)
UNION ALL SELECT 'balancesheet', company_id FROM balancesheet WHERE company_id NOT IN (SELECT id FROM companies)
UNION ALL SELECT 'cashflow', company_id FROM cashflow WHERE company_id NOT IN (SELECT id FROM companies)
UNION ALL SELECT 'stock_prices', company_id FROM stock_prices WHERE company_id NOT IN (SELECT id FROM companies)
UNION ALL SELECT 'market_cap', company_id FROM market_cap WHERE company_id NOT IN (SELECT id FROM companies);

-- Q9: missing annual reports per company
SELECT c.id, c.company_name, 15 - COUNT(DISTINCT d.Year) AS missing_yrs
FROM companies c LEFT JOIN documents d ON d.company_id = c.id
GROUP BY c.id, c.company_name
HAVING missing_yrs > 0
ORDER BY missing_yrs DESC;

-- Q10: stock_prices completeness (expect 60 months per company)
SELECT company_id, COUNT(*) AS months
FROM stock_prices GROUP BY company_id HAVING months <> 60;