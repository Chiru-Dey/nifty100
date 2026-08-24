PY = uv run python

.PHONY: load ratios test report dashboard api clean

load:
	$(PY) -m src.etl.loader

ratios:
	$(PY) src/analytics/ratios.py

test:
	uv run pytest tests/ --html=reports/pytest_report.html

report:
	$(PY) src/reports/portfolio_report.py

dashboard:
	uv run streamlit run src/dashboard/app.py

api:
	uv run uvicorn src.api.main:app --port 8000

clean:
	pwsh -NoProfile -Command "Get-ChildItem -Recurse -Include '__pycache__','*.pyc','.pytest_cache' | Remove-Item -Recurse -Force"

ratios:
	python -m src.analytics.ratios

leverage:
	python -m src.analytics.leverage