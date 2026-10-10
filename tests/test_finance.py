import pandas as pd

from src.finance import (budget_status, forecast_monthly_spending, import_transactions,
                         init_db, load_budgets, load_transactions, monthly_summary,
                         set_budget, unusual_spending, validate_csv)


def test_validation_skips_bad_rows_and_categorizes():
    raw = pd.DataFrame({"date": ["2026-01-01", "not-a-date", "2026-01-03"],
                        "description": ["Cafe coffee", "Rent", ""],
                        "amount": ["100", "200", "300"]})
    valid, messages = validate_csv(raw)
    assert len(valid) == 1
    assert valid.iloc[0]["category"] == "Dining"
    assert any("invalid dates" in m for m in messages)


def test_import_duplicate_and_monthly_summary(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    raw = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"],
                        "description": ["Salary", "Rent"], "amount": [-3000, 1000]})
    first = import_transactions(raw, db)
    second = import_transactions(raw, db)
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    df = load_transactions(db)
    summary = monthly_summary(df)
    assert summary.iloc[0]["income"] == 3000
    assert summary.iloc[0]["expenses"] == 1000
    assert summary.iloc[0]["net"] == 2000


def test_budget_status(tmp_path):
    db = tmp_path / "budget.db"
    init_db(db)
    set_budget("Dining", 1000, db)
    budgets = load_budgets(db)
    df = pd.DataFrame({"month": ["2026-01"], "category": ["Dining"], "amount": [900], "transaction_type": ["expense"]})
    status = budget_status(df, budgets, "2026-01")
    assert status.iloc[0]["status"] == "Near limit"
    assert status.iloc[0]["remaining"] == 100


def test_forecast_nonnegative_and_unusual_spending():
    rows = []
    for month in range(1, 7):
        rows.append({"date": f"2026-{month:02d}-05", "description": "Groceries", "amount": 1000 + month * 10, "category": "Groceries", "transaction_type": "expense"})
    rows.append({"date": "2026-06-20", "description": "Large grocery purchase", "amount": 10000, "category": "Groceries", "transaction_type": "expense"})
    df = pd.DataFrame(rows)
    forecast = forecast_monthly_spending(df, 2)
    assert len(forecast) == 2
    assert (forecast["forecast_expenses"] >= 0).all()
    alerts = unusual_spending(df)
    assert not alerts.empty
