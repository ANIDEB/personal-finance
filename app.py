"""
Personal Finance Dashboard — main entry point / home page.
Run with: streamlit run app.py
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

import database as db
import market_data as md

st.set_page_config(
    page_title="Personal Finance",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.initialize_db()


# ── Market data (cached 10 min) ───────────────────────────────────────────────

@st.cache_data(ttl=600)
def cached_indices():
    return md.fetch_market_indices()


@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))


@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))


# ── Helpers ──────────────────────────────────────────────────────────────────

FREQUENCY_TO_MONTHLY = {
    "Weekly": 52 / 12,
    "Bi-Weekly": 26 / 12,
    "Monthly": 1,
    "Quarterly": 1 / 3,
    "Semi-Annual": 1 / 6,
    "Annual": 1 / 12,
}


def compute_asset_values(assets):
    """
    Return (enriched_assets, total_value).
    For assets with ticker/crypto, try to use live market value.
    """
    stock_tickers = [
        a["ticker"].upper()
        for a in assets
        if a.get("ticker") and a["category"] in ("Stocks & ETFs", "Mutual Funds & Retirement")
    ]
    crypto_symbols = [
        a["ticker"].upper()
        for a in assets
        if a.get("ticker") and a["category"] == "Crypto"
    ]

    stock_prices = cached_stock_prices(tuple(stock_tickers)) if stock_tickers else {}
    crypto_ids = [
        md.CRYPTO_ID_MAP.get(sym, sym.lower()) for sym in crypto_symbols
    ]
    crypto_prices = cached_crypto_prices(tuple(crypto_ids)) if crypto_ids else {}

    enriched = []
    total = 0.0
    for a in assets:
        a = dict(a)
        cat = a["category"]
        ticker = (a.get("ticker") or "").upper()
        qty = a.get("quantity") or 0

        effective_value = a["manual_value"]

        if ticker and cat in ("Stocks & ETFs", "Mutual Funds & Retirement"):
            price = stock_prices.get(ticker, {}).get("price")
            if price and qty:
                effective_value = price * qty
                a["live_price"] = price
            elif price:
                a["live_price"] = price
        elif ticker and cat == "Crypto":
            coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
            price = crypto_prices.get(coin_id, {}).get("price_usd")
            if price and qty:
                effective_value = price * qty
                a["live_price"] = price
            elif price:
                a["live_price"] = price

        a["effective_value"] = effective_value
        total += effective_value
        enriched.append(a)

    return enriched, total


def compute_investment_account_values(accounts, all_holdings):
    """
    Return (enriched_accounts, total_value).
    Each account dict gains a 'total_value' key computed from live prices.
    """
    stock_tickers = tuple(
        h["ticker"].upper()
        for h in all_holdings
        if h["asset_type"] in ("Stock/ETF", "Mutual Fund")
    )
    crypto_symbols = [
        h["ticker"].upper()
        for h in all_holdings
        if h["asset_type"] == "Crypto"
    ]
    crypto_ids = tuple(md.CRYPTO_ID_MAP.get(s, s.lower()) for s in crypto_symbols)

    stock_prices = cached_stock_prices(stock_tickers) if stock_tickers else {}
    crypto_prices = cached_crypto_prices(crypto_ids) if crypto_ids else {}

    account_totals = {a["id"]: 0.0 for a in accounts}
    for h in all_holdings:
        ticker = h["ticker"].upper()
        qty = h.get("quantity") or 0
        price = None
        if h["asset_type"] in ("Stock/ETF", "Mutual Fund"):
            price = stock_prices.get(ticker, {}).get("price")
        elif h["asset_type"] == "Crypto":
            coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
            price = crypto_prices.get(coin_id, {}).get("price_usd")
        val = (price * qty) if price and qty else 0.0
        account_totals[h["account_id"]] = account_totals.get(h["account_id"], 0.0) + val

    enriched = []
    total = 0.0
    for a in accounts:
        a = dict(a)
        holdings_value = account_totals.get(a["id"], 0.0)
        cash = a.get("cash_balance") or 0.0
        a["total_value"] = holdings_value + cash
        total += a["total_value"]
        enriched.append(a)
    return enriched, total


def monthly_income_projection(income_sources, months=24):
    """Return a list of (year_month_label, amount) for the next `months` months."""
    today = date.today()
    projection = []
    for m in range(months):
        target = today + relativedelta(months=m)
        label = target.strftime("%b %Y")
        month_total = 0.0
        for src in income_sources:
            if not src["is_active"]:
                continue
            start = date.fromisoformat(src["start_date"]) if src.get("start_date") else None
            end = date.fromisoformat(src["end_date"]) if src.get("end_date") else None
            if start and target < start:
                continue
            if end and target > end:
                continue
            monthly = src["amount"] * FREQUENCY_TO_MONTHLY.get(src["frequency"], 1)
            month_total += monthly
        projection.append({"month": label, "income": month_total})
    return projection


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("💰 Personal Finance Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%B %d, %Y  %H:%M')}")

assets = db.get_all_assets()
liabilities = db.get_all_liabilities()
income_sources = db.get_all_income_sources()
investment_accounts = db.get_all_investment_accounts()
all_holdings = db.get_all_holdings()

enriched_assets, total_general_assets = compute_asset_values(assets)
enriched_inv_accounts, total_investment = compute_investment_account_values(investment_accounts, all_holdings)
total_assets = total_general_assets + total_investment
total_liabilities = sum(l["remaining_balance"] for l in liabilities)
net_worth = total_assets - total_liabilities

# Save daily snapshot
db.save_net_worth_snapshot(total_assets, total_liabilities)

# ── Top KPI row ───────────────────────────────────────────────────────────────

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Assets", f"${total_assets:,.0f}")
k2.metric("Total Liabilities", f"${total_liabilities:,.0f}")
k3.metric(
    "Net Worth",
    f"${net_worth:,.0f}",
    delta=None,
)

active_income = [s for s in income_sources if s["is_active"]]
monthly_income = sum(
    s["amount"] * FREQUENCY_TO_MONTHLY.get(s["frequency"], 1)
    for s in active_income
)
k4.metric("Monthly Income", f"${monthly_income:,.0f}")

st.divider()

# ── Charts row 1: Asset breakdown + Liability breakdown ──────────────────────

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Asset Allocation")
    allocation: dict[str, float] = {}
    # General assets by category
    for a in enriched_assets:
        allocation[a["category"]] = allocation.get(a["category"], 0.0) + a["effective_value"]
    # Investment accounts by account type
    for acct in enriched_inv_accounts:
        if acct["total_value"] > 0:
            label = acct["account_type"]
            allocation[label] = allocation.get(label, 0.0) + acct["total_value"]

    if allocation:
        df_alloc = pd.DataFrame(allocation.items(), columns=["Category", "Value"])
        fig = px.pie(
            df_alloc,
            names="Category",
            values="Value",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=True, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No assets recorded yet. Go to **Assets** to add some.")

with col_right:
    st.subheader("Liability Breakdown")
    if liabilities:
        df_liab = pd.DataFrame(liabilities)
        cat_totals = df_liab.groupby("category")["remaining_balance"].sum().reset_index()
        cat_totals.columns = ["Category", "Balance"]
        fig = px.pie(
            cat_totals,
            names="Category",
            values="Balance",
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=True, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No liabilities recorded yet. Go to **Liabilities** to add some.")

# ── Net Worth History ─────────────────────────────────────────────────────────

st.subheader("Net Worth Over Time")
history = db.get_net_worth_history()
if len(history) > 1:
    df_hist = pd.DataFrame(history)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_hist["snapshot_date"], y=df_hist["total_assets"],
        name="Assets", fill="tozeroy",
        line=dict(color="#2ecc71", width=2),
        fillcolor="rgba(46,204,113,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=df_hist["snapshot_date"], y=df_hist["total_liabilities"],
        name="Liabilities", fill="tozeroy",
        line=dict(color="#e74c3c", width=2),
        fillcolor="rgba(231,76,60,0.15)",
    ))
    fig.add_trace(go.Scatter(
        x=df_hist["snapshot_date"], y=df_hist["net_worth"],
        name="Net Worth",
        line=dict(color="#3498db", width=3, dash="dash"),
    ))
    fig.update_layout(height=280, margin=dict(t=10, b=10),
                      xaxis_title=None, yaxis_tickprefix="$",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Net worth history will appear here as you visit each day.")

# ── Income Projection ─────────────────────────────────────────────────────────

st.subheader("Income Projection — Next 24 Months")
if income_sources:
    projection = monthly_income_projection(income_sources, months=24)
    df_proj = pd.DataFrame(projection)
    fig = px.bar(
        df_proj, x="month", y="income",
        color_discrete_sequence=["#3498db"],
        labels={"income": "Projected Income ($)", "month": ""},
    )
    fig.update_layout(height=280, margin=dict(t=10, b=10),
                      yaxis_tickprefix="$")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No income sources added yet. Go to **Income Projections** to add some.")

# ── Market Snapshot ───────────────────────────────────────────────────────────

st.subheader("Market Snapshot")
with st.spinner("Loading market data..."):
    indices = cached_indices()

cols = st.columns(len(indices))
for col, (name, data) in zip(cols, indices.items()):
    val = data.get("value")
    chg = data.get("change_pct")
    display = f"{val:,.2f}" if val else "N/A"
    delta_str = f"{chg:+.2f}%" if chg is not None else None
    col.metric(name, display, delta=delta_str)

st.caption("Market data provided by Yahoo Finance (via yfinance). Prices may be delayed ~15 min.")
