# Nifty 100 Financial Intelligence Platform

Self-contained fundamental analysis platform for 92 Nifty 100 companies:
SQLite warehouse, 50+ computed KPIs, screener, peer engine, valuation flags
and an 8-screen Streamlit dashboard. All monetary values in ₹ Crore.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.template .env


python src/etl/loader.py            # 12 datasets -> data/nifty100.db
python src/analytics/ratios.py      # populate financial_ratios
python src/analytics/valuation.py   # output/valuation_summary.xlsx + valuation_flags.csv

streamlit run src/dashboard/app.py