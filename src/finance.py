from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

DEFAULT_DB = Path("data/finance.db")
REQUIRED_COLUMNS = {"date", "description", "amount"}
CATEGORY_RULES = {
    "Housing": ["rent", "mortgage", "property"],
    "Groceries": ["grocery", "supermarket", "vegetables", "market", "food store"],
    "Dining": ["restaurant", "cafe", "coffee", "pizza", "takeaway", "swiggy", "zomato"],
    "Transport": ["uber", "ola", "fuel", "petrol", "metro", "bus", "train", "parking"],
    "Utilities": ["electricity", "water bill", "internet", "broadband", "mobile bill", "gas bill"],
    "Healthcare": ["pharmacy", "hospital", "doctor", "clinic", "medical"],
    "Shopping": ["amazon", "flipkart", "clothing", "clothes", "mall", "electronics"],
    "Entertainment": ["movie", "cinema", "netflix", "spotify", "game", "concert"],
    "Education": ["course", "tuition", "college", "book", "udemy"],
    "Income": ["salary", "payroll", "interest", "refund", "freelance", "dividend"],
}
CATEGORIES = list(CATEGORY_RULES) + ["Other"]


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL DEFAULT 'Other',
            transaction_type TEXT NOT NULL DEFAULT 'expense',
            source TEXT NOT NULL DEFAULT 'manual/import',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, description, amount, category)
        );
        CREATE TABLE IF NOT EXISTS budgets (
            category TEXT PRIMARY KEY,
            monthly_limit REAL NOT NULL CHECK(monthly_limit >= 0),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
        CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
        """)


def categorize(description: str, amount: float | None = None) -> str:
    text = str(description).lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in text for keyword in keywords):
            return category
    if amount is not None and float(amount) > 0:
        # Positive values are not automatically income: transaction sign conventions vary.
        return "Other"
    return "Other"


def validate_csv(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Normalize transaction data and return (valid rows, validation messages).

    Required input columns: date, description, amount. Category is optional.
    Positive amounts are expenses by default; negative amounts are income. This is
    configurable in the app's import controls because bank CSV conventions vary.
    """
    messages: list[str] = []
    if df.empty:
        return pd.DataFrame(columns=["date", "description", "amount", "category", "transaction_type"]), ["The CSV contains no rows."]
    work = df.copy()
    work.columns = [str(c).strip().lower() for c in work.columns]
    aliases = {"transaction date": "date", "posted date": "date", "details": "description", "merchant": "description", "memo": "description", "value": "amount", "debit/credit": "amount"}
    work = work.rename(columns={c: aliases[c] for c in work.columns if c in aliases})
    missing = REQUIRED_COLUMNS - set(work.columns)
    if missing:
        return pd.DataFrame(columns=["date", "description", "amount", "category", "transaction_type"]), ["Missing required column(s): " + ", ".join(sorted(missing))]

    work["date"] = pd.to_datetime(work["date"], errors="coerce", dayfirst=False)
    work["amount"] = pd.to_numeric(work["amount"].astype(str).str.replace(",", "", regex=False).str.replace("₹", "", regex=False).str.strip(), errors="coerce")
    work["description"] = work["description"].fillna("").astype(str).str.strip()
    bad_date = work["date"].isna()
    bad_amount = work["amount"].isna()
    bad_description = work["description"].eq("")
    if bad_date.any(): messages.append(f"Skipped {int(bad_date.sum())} row(s) with missing or invalid dates.")
    if bad_amount.any(): messages.append(f"Skipped {int(bad_amount.sum())} row(s) with missing or invalid amounts.")
    if bad_description.any(): messages.append(f"Skipped {int(bad_description.sum())} row(s) with empty descriptions.")
    valid = work.loc[~(bad_date | bad_amount | bad_description)].copy()
    valid["date"] = valid["date"].dt.strftime("%Y-%m-%d")
    if "category" not in valid.columns:
        valid["category"] = [categorize(d, a) for d, a in zip(valid["description"], valid["amount"])]
    else:
        blank = valid["category"].isna() | valid["category"].astype(str).str.strip().eq("")
        valid.loc[blank, "category"] = [categorize(d, a) for d, a in zip(valid.loc[blank, "description"], valid.loc[blank, "amount"])]
        valid["category"] = valid["category"].astype(str).str.strip()
    if "transaction_type" not in valid.columns:
        valid["transaction_type"] = valid["amount"].apply(lambda x: "income" if x < 0 else "expense")
    else:
        valid["transaction_type"] = valid["transaction_type"].astype(str).str.lower().str.strip()
        valid["transaction_type"] = valid["transaction_type"].where(valid["transaction_type"].isin(["income", "expense"]), "expense")
    # Store magnitudes as positive values; type records the direction.
    valid["amount"] = valid["amount"].abs().astype(float)
    valid = valid[["date", "description", "amount", "category", "transaction_type"]]
    before = len(valid)
    valid = valid.drop_duplicates(subset=["date", "description", "amount", "category", "transaction_type"])
    if len(valid) < before: messages.append(f"Removed {before - len(valid)} duplicate row(s) within the uploaded file.")
    if not messages: messages.append(f"Validation passed: {len(valid)} valid row(s).")
    return valid.reset_index(drop=True), messages


def import_transactions(df: pd.DataFrame, db_path: str | Path = DEFAULT_DB, source: str = "csv upload") -> dict[str, int]:
    valid, messages = validate_csv(df)
    if valid.empty:
        return {"read": len(df), "valid": 0, "inserted": 0, "duplicates": 0}
    inserted = 0
    with connect(db_path) as conn:
        for row in valid.itertuples(index=False):
            cur = conn.execute("""INSERT OR IGNORE INTO transactions
                (date, description, amount, category, transaction_type, source)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (row.date, row.description, float(row.amount), row.category, row.transaction_type, source))
            inserted += cur.rowcount
    return {"read": len(df), "valid": len(valid), "inserted": inserted, "duplicates": len(valid) - inserted}


def load_transactions(db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    init_db(db_path)
    with connect(db_path) as conn:
        df = pd.read_sql_query("SELECT id, date, description, amount, category, transaction_type, source FROM transactions ORDER BY date DESC, id DESC", conn)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.to_period("M").astype(str)
    return df


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["month", "income", "expenses", "net"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    data = df.copy()
    if "month" not in data:
        data["month"] = pd.to_datetime(data["date"]).dt.to_period("M").astype(str)
    data["signed"] = data.apply(lambda r: float(r["amount"]) if r["transaction_type"] == "income" else -float(r["amount"]), axis=1)
    grouped = data.groupby("month").apply(lambda g: pd.Series({
        "income": g.loc[g.transaction_type == "income", "amount"].sum(),
        "expenses": g.loc[g.transaction_type == "expense", "amount"].sum(),
        "net": g["signed"].sum(),
    }), include_groups=False).reset_index()
    return grouped.sort_values("month").reset_index(drop=True)


def set_budget(category: str, monthly_limit: float, db_path: str | Path = DEFAULT_DB) -> None:
    if monthly_limit < 0:
        raise ValueError("Budget must be zero or greater.")
    with connect(db_path) as conn:
        conn.execute("INSERT INTO budgets(category, monthly_limit, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit, updated_at=CURRENT_TIMESTAMP", (category, float(monthly_limit)))


def load_budgets(db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    init_db(db_path)
    with connect(db_path) as conn:
        return pd.read_sql_query("SELECT category, monthly_limit FROM budgets ORDER BY category", conn)


def budget_status(df: pd.DataFrame, budgets: pd.DataFrame, month: str | None = None) -> pd.DataFrame:
    columns = ["category", "monthly_limit", "spent", "remaining", "used_pct", "status"]
    if budgets.empty: return pd.DataFrame(columns=columns)
    data = df.copy()
    if not data.empty:
        data = data[data["transaction_type"] == "expense"]
        if month:
            data = data[data["month"] == month]
        spent = data.groupby("category")["amount"].sum()
    else:
        spent = pd.Series(dtype=float)
    out = budgets.copy()
    out["spent"] = out["category"].map(spent).fillna(0.0)
    out["remaining"] = out["monthly_limit"] - out["spent"]
    out["used_pct"] = out.apply(lambda r: (r.spent / r.monthly_limit * 100) if r.monthly_limit else (100.0 if r.spent else 0.0), axis=1)
    out["status"] = out.apply(lambda r: "Over budget" if r.spent > r.monthly_limit else ("Near limit" if r.used_pct >= 80 else "On track"), axis=1)
    return out[columns].sort_values("used_pct", ascending=False)


def unusual_spending(df: pd.DataFrame, multiplier: float = 2.5) -> pd.DataFrame:
    """Flag large transactions against category history; treat as review prompts, not fraud claims."""
    if df.empty: return df.copy()
    expenses = df[df["transaction_type"] == "expense"].copy()
    if expenses.empty: return expenses
    alerts = []
    for category, group in expenses.groupby("category"):
        values = group["amount"].astype(float)
        median = values.median()
        mad = (values - median).abs().median()
        # Require enough history and avoid a zero MAD threshold.
        if len(group) < 5: continue
        threshold = median + multiplier * max(1.4826 * mad, median * 0.5, 1.0)
        flagged = group[group["amount"] > threshold].copy()
        if not flagged.empty:
            flagged["category_median"] = median
            flagged["review_threshold"] = threshold
            alerts.append(flagged)
    return pd.concat(alerts, ignore_index=True) if alerts else pd.DataFrame(columns=list(expenses.columns) + ["category_median", "review_threshold"])


def forecast_monthly_spending(df: pd.DataFrame, periods: int = 3) -> pd.DataFrame:
    """Forecast total monthly expenses with a simple linear trend when history permits.

    With fewer than 3 observed months, use the historical mean. This is an estimate,
    not financial advice; incomplete months and irregular expenses can skew it.
    """
    cols = ["month", "forecast_expenses", "method"]
    if periods < 1: raise ValueError("periods must be at least 1")
    expenses = df[df["transaction_type"] == "expense"].copy() if not df.empty else pd.DataFrame()
    if expenses.empty: return pd.DataFrame(columns=cols)
    expenses["month_period"] = pd.to_datetime(expenses["date"]).dt.to_period("M")
    monthly = expenses.groupby("month_period")["amount"].sum().sort_index()
    # Include zero-spend months between first and last observations.
    full_index = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    monthly = monthly.reindex(full_index, fill_value=0.0)
    future = pd.period_range(full_index[-1] + 1, periods=periods, freq="M")
    if len(monthly) >= 3:
        # Ordinary least-squares linear trend using Python arithmetic only.
        # This avoids importing scikit-learn/SciPy native extensions, which can
        # be blocked by Windows Application Control policies on some machines.
        y_values = [float(value) for value in monthly.tolist()]
        x_values = list(range(len(y_values)))
        n = len(y_values)
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x_squared = sum(x * x for x in x_values)
        denominator = n * sum_x_squared - sum_x * sum_x

        if denominator == 0:
            preds = [sum_y / n] * periods
            method = "Historical average (limited trend variation)"
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
            intercept = (sum_y - slope * sum_x) / n
            future_x = range(n, n + periods)
            preds = [intercept + slope * x for x in future_x]
            method = "Linear trend (clipped at zero)"
    else:
        preds = [monthly.mean()] * periods
        method = "Historical average (limited history)"
    preds = [max(0.0, float(p)) for p in preds]
    return pd.DataFrame({"month": [str(p) for p in future], "forecast_expenses": preds, "method": method})


def summary_export(df: pd.DataFrame) -> bytes:
    return monthly_summary(df).to_csv(index=False).encode("utf-8")
