PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id VARCHAR(12) PRIMARY KEY,
    company_logo TEXT,
    company_name TEXT NOT NULL,
    chart_link TEXT,
    about_company TEXT,
    website TEXT,
    nse_profile TEXT,
    bse_profile TEXT,
    face_value REAL,
    book_value REAL,
    roce_percentage REAL,
    roe_percentage REAL
);

CREATE TABLE IF NOT EXISTS profitandloss (
    id INTEGER,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    year VARCHAR(7) NOT NULL,
    sales REAL,
    expenses REAL,
    operating_profit REAL,
    opm_percentage REAL,
    other_income REAL,
    interest REAL,
    depreciation REAL,
    profit_before_tax REAL,
    tax_percentage REAL,
    net_profit REAL,
    eps REAL,
    dividend_payout REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS balancesheet (
    id INTEGER,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    year VARCHAR(7) NOT NULL,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_liabilities REAL,
    fixed_assets REAL,
    cwip REAL,
    investments REAL,
    other_asset REAL,
    total_assets REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS cashflow (
    id INTEGER,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    year VARCHAR(7) NOT NULL,
    operating_activity REAL,
    investing_activity REAL,
    financing_activity REAL,
    net_cash_flow REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    compounded_sales_growth TEXT,
    compounded_profit_growth TEXT,
    stock_price_cagr TEXT,
    roe TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    Year INTEGER NOT NULL,
    Annual_Report TEXT,
    PRIMARY KEY (company_id, Year)
);

CREATE TABLE IF NOT EXISTS prosandcons (
    id INTEGER PRIMARY KEY,
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    pros TEXT,
    cons TEXT
);

CREATE TABLE IF NOT EXISTS sectors (
    company_id VARCHAR(12) PRIMARY KEY REFERENCES companies(id),
    broad_sector TEXT NOT NULL,
    sub_sector TEXT,
    index_weight_pct REAL,
    market_cap_category TEXT
);

CREATE TABLE IF NOT EXISTS market_cap (
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    year INTEGER NOT NULL,
    market_cap_crore REAL,
    enterprise_value_crore REAL,
    pe_ratio REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    dividend_yield_pct REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS stock_prices (
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    date TEXT NOT NULL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    close_price REAL,
    volume INTEGER,
    adjusted_close REAL,
    PRIMARY KEY (company_id, date)
);

CREATE TABLE IF NOT EXISTS financial_ratios (
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    year VARCHAR(7) NOT NULL,
    net_profit_margin_pct REAL,
    operating_profit_margin_pct REAL,
    return_on_equity_pct REAL,
    debt_to_equity REAL,
    interest_coverage REAL,
    asset_turnover REAL,
    free_cash_flow_cr REAL,
    capex_cr REAL,
    earnings_per_share REAL,
    book_value_per_share REAL,
    dividend_payout_ratio_pct REAL,
    total_debt_cr REAL,
    cash_from_operations_cr REAL,
    PRIMARY KEY (company_id, year)
);

CREATE TABLE IF NOT EXISTS peer_groups (
    company_id VARCHAR(12) NOT NULL REFERENCES companies(id),
    peer_group_name TEXT NOT NULL,
    is_benchmark INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (company_id, peer_group_name)
);