# Personal Finance Analytics Platform

A local-first personal finance analytics app built with Python, Pandas, SQLite, scikit-learn, Streamlit, and Plotly.

## Features

- Import transaction CSVs and validate required fields, dates, amounts, and descriptions.
- Rule-based expense categorization with editable categories in source data.
- Store records in SQLite with duplicate protection.
- Monthly income, expenses, and net cash-flow summaries.
- Category breakdowns and month-by-month spending trends.
- Cautious 1–6 month expense forecast: linear regression with at least three observed months, otherwise historical average.
- Interactive Streamlit/Plotly dashboard.
- Download all transactions, selected-month transactions, and monthly summary CSVs.
- Configurable category budgets with near-limit and over-budget indicators.
- Potentially unusual-spending flags using robust category-level thresholds; flags are review prompts, not fraud determinations.
- Synthetic sample data and automated tests.

## Requirements

Python 3.10+ recommended. No AWS account or cloud services are required.

## Run on Windows PowerShell

```powershell
cd personal_finance_analytics
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -v
streamlit run app.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again. Alternatively, install dependencies with `.venv\Scripts\python.exe -m pip install -r requirements.txt` and launch with `.venv\Scripts\python.exe -m streamlit run app.py`.

The app opens in your browser. Upload `data/sample_transactions.csv` using the sidebar to load the synthetic example data. The local SQLite database is created at `data/finance.db` the first time the app runs.

## CSV format

Required columns: `date`, `description`, `amount`. Optional: `category`, `transaction_type` (`income` or `expense`). Example:

```csv
date,description,amount,category,transaction_type
2026-01-01,Monthly salary,42000,Income,income
2026-01-02,Apartment rent,12000,Housing,expense
```

If `transaction_type` is absent, negative amounts are treated as income and positive amounts as expenses. The import sidebar offers a sign-convention option. If a bank uses a different convention, verify the option before importing. The app stores amount magnitudes as positive values and uses `transaction_type` to distinguish income from expenses.

## Data safety

The included sample data is synthetic. Do not commit real bank statements, account numbers, personal identifiers, or the generated `data/finance.db` file. The `.gitignore` excludes the database by default. Review and anonymize any data before using it in a public repository.

## Forecasting limitations

The forecast is a simple baseline, not financial advice. It uses monthly expense totals and cannot know about upcoming bills, one-off purchases, seasonality, inflation, or incomplete current months. Interpret estimates alongside the actual monthly trend.

## Tests

```powershell
python -m pytest -v
```

Tests cover invalid CSV rows, category assignment, duplicate imports, SQL persistence, monthly summaries, budget status, forecasts, and unusual-spending alerts.
