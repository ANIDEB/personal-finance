"""
Investment Projections page — visualise how each holding and account
is expected to grow over time based on annual growth rate, dividends,
and reinvestment settings entered on the Assets page.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db
import market_data as md

st.set_page_config(page_title="Investment Projections", page_icon="🔭", layout="wide")
db.initialize_db()

# ── Constants ─────────────────────────────────────────────────────────────────

FREQ_TO_PAYMENTS = {
    "None": 0,
    "Monthly": 12,
    "Quarterly": 4,
    "Semi-Annual": 2,
    "Annual": 1,
}

MILESTONE_YEARS = [1, 3, 5, 10, 15, 20, 30]


# ── Market data (cached 10 min) ───────────────────────────────────────────────

@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))


@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))


# ── Projection engine ─────────────────────────────────────────────────────────

def current_holding_value(h, stock_prices, crypto_prices):
    """Return best available current value for a holding."""
    ticker = h["ticker"].upper()
    qty = h.get("quantity") or 0
    price = None

    if h["asset_type"] in ("Stock/ETF", "Mutual Fund"):
        price = stock_prices.get(ticker, {}).get("price")
    elif h["asset_type"] == "Crypto":
        coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
        price = crypto_prices.get(coin_id, {}).get("price_usd")

    if price and qty:
        return price * qty, price
    # Fallback: cost basis
    if h.get("cost_basis") and qty:
        return h["cost_basis"] * qty, h["cost_basis"]
    return 0.0, price


def project_holding(h, current_value, live_price, years):
    """
    Return a list of dicts {year, value, annual_dividend_income}
    for years 0..years.

    If reinvest_dividends:  dividend yield is added to the growth rate
                            (DRIP — dividends compound with the principal)
    If not reinvest:        principal grows at growth_rate only;
                            dividend income is reported separately each year
    """
    growth_rate = (h.get("annual_growth_rate") or 0) / 100
    div_per_unit = h.get("dividend_per_unit") or 0
    payments_per_year = FREQ_TO_PAYMENTS.get(h.get("dividend_frequency", "Annual"), 0)
    annual_div_per_unit = div_per_unit * payments_per_year
    reinvest = bool(h.get("reinvest_dividends", False))
    qty = h.get("quantity") or 0

    # Dividend yield relative to current price (used for DRIP compounding)
    if live_price and live_price > 0 and annual_div_per_unit > 0:
        div_yield = annual_div_per_unit / live_price
    else:
        div_yield = 0.0

    rows = []
    value = current_value

    for year in range(years + 1):
        if reinvest:
            annual_div_income = 0.0       # reinvested, not paid out as cash
        else:
            annual_div_income = qty * annual_div_per_unit

        rows.append({
            "year": year,
            "value": round(value, 2),
            "annual_dividend_income": round(annual_div_income, 2),
        })

        # Grow for next year
        if reinvest:
            value *= (1 + growth_rate + div_yield)
        else:
            value *= (1 + growth_rate)

    return rows


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("🔭 Investment Projections")
st.caption(
    "Projections are based on the annual growth rate, dividend settings, "
    "and reinvestment indicator you entered for each position. "
    "They are illustrative — not financial advice."
)

# ── Load data ─────────────────────────────────────────────────────────────────

accounts = db.get_all_investment_accounts()
all_holdings = db.get_all_holdings()

if not accounts or not all_holdings:
    st.info(
        "No investment accounts or positions found. "
        "Go to **Assets → Investment Accounts** to add accounts and positions."
    )
    st.stop()

# Batch-fetch prices
stock_tickers = tuple(
    h["ticker"].upper()
    for h in all_holdings
    if h["asset_type"] in ("Stock/ETF", "Mutual Fund")
)
crypto_syms = [h["ticker"].upper() for h in all_holdings if h["asset_type"] == "Crypto"]
crypto_ids = tuple(md.CRYPTO_ID_MAP.get(s, s.lower()) for s in crypto_syms)

with st.spinner("Fetching live prices..."):
    stock_prices = cached_stock_prices(stock_tickers) if stock_tickers else {}
    crypto_prices = cached_crypto_prices(crypto_ids) if crypto_ids else {}

# ── Controls ──────────────────────────────────────────────────────────────────

ctrl1, ctrl2 = st.columns([1, 2])
with ctrl1:
    horizon = st.slider("Projection Horizon (years)", min_value=5, max_value=30,
                        value=20, step=5)

# Build account lookup
account_map = {a["id"]: a for a in accounts}

# ── Compute projections for every holding ─────────────────────────────────────

all_projections = []   # flat list of per-holding year rows

for h in all_holdings:
    val, price = current_holding_value(h, stock_prices, crypto_prices)
    if val <= 0:
        continue
    acct = account_map.get(h["account_id"], {})
    rows = project_holding(h, val, price, horizon)
    for r in rows:
        all_projections.append({
            "year": r["year"],
            "value": r["value"],
            "annual_dividend_income": r["annual_dividend_income"],
            "ticker": h["ticker"],
            "asset_type": h["asset_type"],
            "account_id": h["account_id"],
            "account_name": acct.get("name", "Unknown"),
            "account_type": acct.get("account_type", ""),
            "institution": acct.get("institution", ""),
            "growth_rate": h.get("annual_growth_rate") or 0,
            "reinvest": bool(h.get("reinvest_dividends", False)),
        })

if not all_projections:
    st.warning(
        "No projectable holdings found. "
        "Make sure your positions have a live price or cost basis set."
    )
    st.stop()

df_all = pd.DataFrame(all_projections)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_portfolio, tab_accounts, tab_detail = st.tabs([
    "Portfolio Overview", "By Account", "Holding Detail"
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — PORTFOLIO OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

with tab_portfolio:
    # Total projected value per year
    df_total = df_all.groupby("year")["value"].sum().reset_index()
    df_total.columns = ["Year", "Total Portfolio Value"]

    # KPIs at milestone years
    today_val = df_total.loc[df_total["Year"] == 0, "Total Portfolio Value"].values[0]
    st.metric("Current Portfolio Value", f"${today_val:,.0f}")

    kpi_cols = st.columns(len([y for y in MILESTONE_YEARS if y <= horizon]))
    for col, yr in zip(kpi_cols, [y for y in MILESTONE_YEARS if y <= horizon]):
        row = df_total[df_total["Year"] == yr]
        if not row.empty:
            proj_val = row["Total Portfolio Value"].values[0]
            gain = proj_val - today_val
            col.metric(
                f"Year {yr}",
                f"${proj_val:,.0f}",
                delta=f"+${gain:,.0f}",
            )

    st.divider()

    # Area chart — total portfolio over time
    fig = px.area(
        df_total,
        x="Year",
        y="Total Portfolio Value",
        labels={"Total Portfolio Value": "Projected Value ($)"},
        color_discrete_sequence=["#3498db"],
    )
    fig.update_traces(
        line=dict(width=2),
        fillcolor="rgba(52,152,219,0.15)",
    )
    fig.update_layout(
        height=380,
        margin=dict(t=20, b=20),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        xaxis_title="Years from Today",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Annual dividend income (non-reinvested only)
    df_div = df_all.groupby("year")["annual_dividend_income"].sum().reset_index()
    df_div.columns = ["Year", "Annual Dividend Income"]
    total_annual_div = df_div[df_div["Year"] == 1]["Annual Dividend Income"].values
    if total_annual_div.size and total_annual_div[0] > 0:
        st.subheader("Annual Dividend Income (Cash Paid Out)")
        st.caption("Only includes dividends from positions where DRIP is OFF.")
        fig_div = px.bar(
            df_div[df_div["Year"] > 0],
            x="Year",
            y="Annual Dividend Income",
            color_discrete_sequence=["#2ecc71"],
            labels={"Annual Dividend Income": "Dividend Income ($)"},
        )
        fig_div.update_layout(
            height=260,
            margin=dict(t=10, b=10),
            yaxis_tickprefix="$",
            yaxis_tickformat=",.0f",
        )
        st.plotly_chart(fig_div, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — BY ACCOUNT
# ════════════════════════════════════════════════════════════════════════════

with tab_accounts:
    df_by_acct = df_all.groupby(["year", "account_name"])["value"].sum().reset_index()
    df_by_acct.columns = ["Year", "Account", "Value"]

    fig_acct = px.line(
        df_by_acct,
        x="Year",
        y="Value",
        color="Account",
        labels={"Value": "Projected Value ($)", "Year": "Years from Today"},
        markers=False,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_acct.update_layout(
        height=420,
        margin=dict(t=20, b=20),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_acct, use_container_width=True)

    # Milestone table per account
    st.subheader("Projected Value at Milestone Years")
    milestone_yrs = [y for y in MILESTONE_YEARS if y <= horizon]
    pivot = df_by_acct[df_by_acct["Year"].isin([0] + milestone_yrs)].copy()
    pivot = pivot.pivot(index="Account", columns="Year", values="Value").reset_index()
    pivot.columns.name = None

    fmt_cols = [c for c in pivot.columns if c != "Account"]
    for c in fmt_cols:
        pivot[c] = pivot[c].map("${:,.0f}".format)
    pivot = pivot.rename(columns={0: "Today"})
    pivot = pivot.rename(columns={y: f"Year {y}" for y in milestone_yrs})

    st.dataframe(pivot, hide_index=True, use_container_width=True)

    # Stacked area by account
    st.subheader("Stacked Growth by Account")
    fig_stack = px.area(
        df_by_acct,
        x="Year",
        y="Value",
        color="Account",
        labels={"Value": "Projected Value ($)", "Year": "Years from Today"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_stack.update_layout(
        height=380,
        margin=dict(t=10, b=20),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_stack, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — HOLDING DETAIL
# ════════════════════════════════════════════════════════════════════════════

with tab_detail:
    # Account filter
    account_names = sorted(df_all["account_name"].unique())
    selected_accounts = st.multiselect(
        "Filter by account",
        account_names,
        default=account_names,
    )
    df_filtered = df_all[df_all["account_name"].isin(selected_accounts)]

    # Line chart — one line per ticker
    df_ticker = df_filtered.groupby(["year", "ticker", "account_name"])["value"].sum().reset_index()
    df_ticker["label"] = df_ticker["ticker"] + " (" + df_ticker["account_name"] + ")"

    fig_tickers = px.line(
        df_ticker,
        x="year",
        y="value",
        color="label",
        labels={"value": "Projected Value ($)", "year": "Years from Today", "label": "Position"},
        markers=False,
        color_discrete_sequence=px.colors.qualitative.Alphabet,
    )
    fig_tickers.update_layout(
        height=420,
        margin=dict(t=20, b=20),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.25, font=dict(size=11)),
    )
    st.plotly_chart(fig_tickers, use_container_width=True)

    st.divider()
    st.subheader("Detail Table — Projected Value at Milestone Years")

    # Build milestone table per ticker
    milestone_yrs = [y for y in MILESTONE_YEARS if y <= horizon]
    detail_rows = []
    for h in all_holdings:
        acct = account_map.get(h["account_id"], {})
        if acct.get("name") not in selected_accounts:
            continue
        val, price = current_holding_value(h, stock_prices, crypto_prices)
        if val <= 0:
            continue
        proj = project_holding(h, val, price, max(milestone_yrs))
        proj_map = {r["year"]: r for r in proj}

        reinvest = bool(h.get("reinvest_dividends", False))
        payments = FREQ_TO_PAYMENTS.get(h.get("dividend_frequency", "Annual"), 0)
        annual_div = (h.get("dividend_per_unit") or 0) * payments * (h.get("quantity") or 0)

        row = {
            "Account": acct.get("name", ""),
            "Ticker": h["ticker"],
            "Type": h["asset_type"],
            "Current Value": f"${val:,.2f}",
            "Growth Rate": f"{h.get('annual_growth_rate') or 0:.1f}%",
            "Annual Div ($)": f"${annual_div:,.2f}" if annual_div else "—",
            "DRIP": "Yes" if reinvest else "No",
        }
        for yr in milestone_yrs:
            if yr in proj_map:
                row[f"Yr {yr}"] = f"${proj_map[yr]['value']:,.0f}"
            else:
                row[f"Yr {yr}"] = "—"
        detail_rows.append(row)

    if detail_rows:
        st.dataframe(
            pd.DataFrame(detail_rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No positions with projectable values in the selected accounts.")
