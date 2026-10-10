from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from src.finance import (CATEGORIES, DEFAULT_DB, budget_status, forecast_monthly_spending,
                         import_transactions, init_db, load_budgets, load_transactions,
                         monthly_summary, set_budget, summary_export, unusual_spending,
                         validate_csv)

st.set_page_config(page_title="Personal Finance Analytics", page_icon="💸", layout="wide")
DB_PATH = ROOT / "data" / "finance.db"
init_db(DB_PATH)

st.title("💸 Personal Finance Analytics Platform")
st.caption("Understand spending patterns with transparent summaries and cautious forecasts. All demo data is synthetic.")

with st.sidebar:
    st.header("Import transactions")
    st.markdown("CSV needs **date**, **description**, and **amount** columns. Optional: `category`, `transaction_type`.")
    uploaded = st.file_uploader("Choose a transaction CSV", type=["csv"])
    if uploaded is not None:
        try:
            raw = pd.read_csv(uploaded)
            st.write("Preview", raw.head(5))
            sign_convention = st.radio("Amount sign convention", ["Positive = expense; negative = income", "Positive = income; negative = expense"], help="Use the convention that matches your file. If transaction_type is provided, it is used instead.")
            if st.button("Validate and import", type="primary"):
                if sign_convention.startswith("Positive = income") and "transaction_type" not in [c.lower().strip() for c in raw.columns]:
                    raw["amount"] = pd.to_numeric(raw["amount"].astype(str).str.replace(",", "", regex=False).str.replace("₹", "", regex=False), errors="coerce") * -1
                valid, messages = validate_csv(raw)
                for msg in messages: st.info(msg)
                result = import_transactions(raw, DB_PATH, source=uploaded.name)
                st.success(f"Imported {result['inserted']} new transaction(s); {result['duplicates']} database duplicate(s) ignored.")
                st.rerun()
        except Exception as exc:
            st.error(f"Could not read/import this CSV: {exc}")
    st.divider()
    st.download_button("Download synthetic sample CSV", data=(ROOT / "data" / "sample_transactions.csv").read_bytes(), file_name="sample_transactions.csv", mime="text/csv")
    st.caption("Privacy tip: remove account numbers, addresses, and other personal details before importing or sharing data.")

df = load_transactions(DB_PATH)
if df.empty:
    st.info("No transactions yet. Import the included synthetic sample CSV from the sidebar to explore the dashboard.")
    st.stop()

months = sorted(df["month"].dropna().unique())
with st.sidebar:
    selected_month = st.selectbox("Dashboard month", options=months, index=len(months)-1)
month_df = df[df["month"] == selected_month]
month_expenses = month_df.loc[month_df.transaction_type == "expense", "amount"].sum()
month_income = month_df.loc[month_df.transaction_type == "income", "amount"].sum()
net = month_income - month_expenses

c1, c2, c3, c4 = st.columns(4)
c1.metric("Expenses", f"₹{month_expenses:,.2f}")
c2.metric("Income", f"₹{month_income:,.2f}")
c3.metric("Net cash flow", f"₹{net:,.2f}", delta=f"{net:,.2f}")
c4.metric("Transactions", f"{len(month_df):,}")

summary = monthly_summary(df)
expense_df = month_df[month_df.transaction_type == "expense"]
left, right = st.columns(2)
with left:
    st.subheader("Spending by category")
    if expense_df.empty:
        st.write("No expenses for this month.")
    else:
        cat = expense_df.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        st.plotly_chart(px.pie(cat, names="category", values="amount", hole=0.45, title=selected_month + " expense mix"), use_container_width=True)
with right:
    st.subheader("Monthly spending trend")
    if summary.empty:
        st.write("No monthly data available.")
    else:
        st.plotly_chart(px.line(summary, x="month", y="expenses", markers=True, title="Actual monthly expenses"), use_container_width=True)

st.subheader("Monthly summary")
st.dataframe(summary.style.format({"income": "₹{:,.2f}", "expenses": "₹{:,.2f}", "net": "₹{:,.2f}"}), use_container_width=True, hide_index=True)

budget_tab, forecast_tab, alerts_tab, records_tab, export_tab = st.tabs(["Budgets", "Forecast", "Unusual spending", "Transactions", "Export reports"])
with budget_tab:
    st.subheader("Configure monthly budgets")
    with st.form("budget_form"):
        b1, b2 = st.columns([2, 1])
        category = b1.selectbox("Category", options=[c for c in CATEGORIES if c != "Income"])
        limit = b2.number_input("Monthly limit (₹)", min_value=0.0, value=5000.0, step=500.0)
        save = st.form_submit_button("Save budget")
        if save:
            set_budget(category, limit, DB_PATH)
            st.success(f"Saved {category} budget: ₹{limit:,.2f}")
            st.rerun()
    budgets = load_budgets(DB_PATH)
    status = budget_status(df, budgets, selected_month)
    if status.empty:
        st.info("No budgets configured yet. Add one above.")
    else:
        st.dataframe(status.style.format({"monthly_limit": "₹{:,.2f}", "spent": "₹{:,.2f}", "remaining": "₹{:,.2f}", "used_pct": "{:.1f}%"}), use_container_width=True, hide_index=True)
        over = status[status.status != "On track"]
        for row in over.itertuples(index=False):
            (st.error if row.status == "Over budget" else st.warning)(f"{row.category}: ₹{row.spent:,.2f} spent of ₹{row.monthly_limit:,.2f} budget ({row.used_pct:.0f}%).")

with forecast_tab:
    st.subheader("Cautious spending forecast")
    st.caption("Forecasts are estimates, not guarantees. Irregular expenses, incomplete months, inflation, and limited history can reduce accuracy.")
    periods = st.slider("Months to forecast", min_value=1, max_value=6, value=3)
    forecast = forecast_monthly_spending(df, periods)
    if forecast.empty:
        st.info("Import expense history to create a forecast.")
    else:
        st.dataframe(forecast.style.format({"forecast_expenses": "₹{:,.2f}"}), use_container_width=True, hide_index=True)
        hist = summary[["month", "expenses"]].rename(columns={"expenses": "amount"}).copy()
        hist["type"] = "Actual"
        fc = forecast.rename(columns={"forecast_expenses": "amount"})[["month", "amount"]].copy()
        fc["type"] = "Forecast"
        chart_data = pd.concat([hist[["month", "amount", "type"]], fc], ignore_index=True)
        st.plotly_chart(px.line(chart_data, x="month", y="amount", color="type", markers=True, title="Actual vs forecast monthly expenses"), use_container_width=True)
        st.caption("Method: " + str(forecast["method"].iloc[0]))

with alerts_tab:
    st.subheader("Potentially unusual spending")
    st.caption("These statistical flags are prompts to review a transaction, not accusations of fraud. At least five same-category transactions are required.")
    alerts = unusual_spending(df)
    if alerts.empty:
        st.success("No transactions met the current unusual-spending threshold, or there is not enough category history yet.")
    else:
        st.dataframe(alerts[["date", "description", "category", "amount", "category_median", "review_threshold"]].style.format({"amount": "₹{:,.2f}", "category_median": "₹{:,.2f}", "review_threshold": "₹{:,.2f}"}), use_container_width=True, hide_index=True)

with records_tab:
    st.subheader("Transaction records")
    f1, f2 = st.columns(2)
    categories = sorted(df["category"].dropna().unique())
    chosen_categories = f1.multiselect("Filter categories", categories, default=categories)
    chosen_type = f2.selectbox("Transaction type", ["All", "expense", "income"])
    filtered = df[df.category.isin(chosen_categories)]
    if chosen_type != "All": filtered = filtered[filtered.transaction_type == chosen_type]
    st.dataframe(filtered[["date", "description", "amount", "category", "transaction_type", "source"]], use_container_width=True, hide_index=True)

with export_tab:
    st.subheader("Export your reports")
    st.download_button("Download all transactions (CSV)", data=df.drop(columns=["month"], errors="ignore").to_csv(index=False).encode("utf-8"), file_name="transactions_export.csv", mime="text/csv")
    st.download_button("Download monthly summary (CSV)", data=summary_export(df), file_name="monthly_summary.csv", mime="text/csv")
    st.download_button("Download selected-month transactions (CSV)", data=month_df.drop(columns=["month"], errors="ignore").to_csv(index=False).encode("utf-8"), file_name=f"transactions_{selected_month}.csv", mime="text/csv")

st.divider()
st.caption("Personal Finance Analytics Platform · Python · Pandas · SQLite · scikit-learn · Streamlit · Plotly | Rutuja C Pawar ")
