"""
Investment Projections page — projects each holding to retirement date,
showing Dec 31 balance for every calendar year.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import date, timedelta

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

MILESTONE_YEARS = [1, 3, 5, 10, 15, 20, 25, 30]


# ── Market data (cached 10 min) ───────────────────────────────────────────────

@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))


@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))


# ── Retirement date setting ───────────────────────────────────────────────────

st.title("🔭 Investment Projections")

with st.expander("⚙️ Retirement Settings", expanded=False):
    saved_str = db.get_setting("retirement_date")
    saved_date = date.fromisoformat(saved_str) if saved_str else None

    with st.form("retirement_form"):
        ret_date_input = st.date_input(
            "Projected Retirement Date",
            value=saved_date or date(date.today().year + 25, 1, 1),
            min_value=date.today() + timedelta(days=1),
        )
        if st.form_submit_button("Save Retirement Date", type="primary"):
            db.set_setting("retirement_date", ret_date_input.isoformat())
            st.success(f"Retirement date saved: {ret_date_input.strftime('%B %d, %Y')}")
            st.rerun()

# Reload after possible save
retirement_str = db.get_setting("retirement_date")
if not retirement_str:
    st.warning("Set your **Projected Retirement Date** in the settings above to see projections.")
    st.stop()

retirement_date = date.fromisoformat(retirement_str)
today = date.today()

if retirement_date <= today:
    st.error("Retirement date must be in the future. Please update it above.")
    st.stop()

# Calendar years from current year to retirement year (inclusive)
current_year = today.year
retirement_year = retirement_date.year
cal_years = list(range(current_year, retirement_year + 1))
years_to_retirement = retirement_year - current_year

years_left = (retirement_date - today).days / 365.25
st.caption(
    f"Projecting to **{retirement_date.strftime('%B %d, %Y')}** "
    f"— {years_left:.1f} years away. "
    f"Balances shown as of **Dec 31** each calendar year."
)

# ── Load data ─────────────────────────────────────────────────────────────────

accounts = db.get_all_investment_accounts()
all_holdings = db.get_all_holdings()

if not accounts or not all_holdings:
    st.info(
        "No investment positions found. "
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

account_map = {a["id"]: a for a in accounts}


# ── Projection helpers ────────────────────────────────────────────────────────

def current_holding_value(h):
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
    if h.get("cost_basis") and qty:
        return h["cost_basis"] * qty, h["cost_basis"]
    return 0.0, price


def project_by_calendar_year(h, current_value, live_price, cal_years):
    """
    Return a list of {cal_year, dec31_value, annual_dividend_income}
    for each calendar year in cal_years.

    The first year uses a partial-year fraction (months remaining / 12).
    Subsequent years are full-year growth.
    """
    growth_rate = (h.get("annual_growth_rate") or 0) / 100
    div_per_unit = h.get("dividend_per_unit") or 0
    payments_per_year = FREQ_TO_PAYMENTS.get(h.get("dividend_frequency", "Annual"), 0)
    annual_div_per_unit = div_per_unit * payments_per_year
    reinvest = bool(h.get("reinvest_dividends", False))
    qty = h.get("quantity") or 0

    div_yield = (annual_div_per_unit / live_price) if (live_price and live_price > 0 and annual_div_per_unit > 0) else 0.0
    effective_rate = growth_rate + (div_yield if reinvest else 0)

    rows = []
    value = current_value

    for i, yr in enumerate(cal_years):
        if i == 0:
            # Partial year: days from today to Dec 31 of current year
            dec31 = date(yr, 12, 31)
            fraction = (dec31 - today).days / 365.25
        else:
            fraction = 1.0

        value = value * ((1 + effective_rate) ** fraction)
        annual_div_income = 0.0 if reinvest else (qty * annual_div_per_unit * fraction)

        rows.append({
            "cal_year": yr,
            "dec31_value": round(value, 2),
            "annual_dividend_income": round(annual_div_income, 2),
        })

    return rows


# ── Build full projection dataset ─────────────────────────────────────────────

all_proj_rows = []

for h in all_holdings:
    val, price = current_holding_value(h)
    if val <= 0:
        continue
    acct = account_map.get(h["account_id"], {})
    proj = project_by_calendar_year(h, val, price, cal_years)
    for r in proj:
        all_proj_rows.append({
            "cal_year": r["cal_year"],
            "dec31_value": r["dec31_value"],
            "annual_dividend_income": r["annual_dividend_income"],
            "ticker": h["ticker"],
            "asset_type": h["asset_type"],
            "account_id": h["account_id"],
            "account_name": acct.get("name", "Unknown"),
            "account_type": acct.get("account_type", ""),
            "growth_rate": h.get("annual_growth_rate") or 0,
            "reinvest": bool(h.get("reinvest_dividends", False)),
        })

# Prepend today's snapshot (year 0 = now)
today_rows = []
for h in all_holdings:
    val, price = current_holding_value(h)
    if val <= 0:
        continue
    acct = account_map.get(h["account_id"], {})
    today_rows.append({
        "cal_year": f"Today ({today.strftime('%b %d, %Y')})",
        "dec31_value": val,
        "annual_dividend_income": 0.0,
        "ticker": h["ticker"],
        "asset_type": h["asset_type"],
        "account_id": h["account_id"],
        "account_name": acct.get("name", "Unknown"),
        "account_type": acct.get("account_type", ""),
        "growth_rate": h.get("annual_growth_rate") or 0,
        "reinvest": bool(h.get("reinvest_dividends", False)),
    })

if not all_proj_rows:
    st.warning("No projectable positions found. Ensure positions have a live price or cost basis.")
    st.stop()

df_all = pd.DataFrame(all_proj_rows)

# Current total
current_total = sum(r["dec31_value"] for r in today_rows)


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_portfolio, tab_accounts, tab_detail = st.tabs([
    "Portfolio Overview", "By Account", "Holding Detail"
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — PORTFOLIO OVERVIEW
# ════════════════════════════════════════════════════════════════════════════

with tab_portfolio:
    df_total = (
        df_all.groupby("cal_year")["dec31_value"]
        .sum()
        .reset_index()
        .rename(columns={"cal_year": "Year", "dec31_value": "Portfolio Value"})
    )

    # Retirement year value
    ret_row = df_total[df_total["Year"] == retirement_year]
    ret_value = ret_row["Portfolio Value"].values[0] if not ret_row.empty else None

    # KPI row
    k1, k2, k3 = st.columns(3)
    k1.metric("Current Portfolio", f"${current_total:,.0f}")
    if ret_value:
        k2.metric(
            f"At Retirement ({retirement_year})",
            f"${ret_value:,.0f}",
            delta=f"+${ret_value - current_total:,.0f}",
        )
    k3.metric("Years to Retirement", f"{years_left:.1f}")

    # Milestone KPIs
    milestone_cols = [
        (yr, current_year + yr)
        for yr in MILESTONE_YEARS
        if current_year + yr <= retirement_year
    ]
    if milestone_cols:
        cols = st.columns(len(milestone_cols))
        for col, (offset, cal_yr) in zip(cols, milestone_cols):
            row = df_total[df_total["Year"] == cal_yr]
            if not row.empty:
                v = row["Portfolio Value"].values[0]
                col.metric(f"{cal_yr}", f"${v:,.0f}", delta=f"+${v - current_total:,.0f}")

    st.divider()

    # Area chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_total["Year"],
        y=df_total["Portfolio Value"],
        fill="tozeroy",
        line=dict(color="#3498db", width=2.5),
        fillcolor="rgba(52,152,219,0.15)",
        name="Portfolio Value",
        hovertemplate="Dec 31, %{x}<br>$%{y:,.0f}<extra></extra>",
    ))
    # Retirement marker
    if ret_value:
        fig.add_vline(
            x=retirement_year,
            line_dash="dash",
            line_color="#e74c3c",
            annotation_text=f"Retirement {retirement_year}",
            annotation_position="top right",
        )
    fig.update_layout(
        height=400,
        margin=dict(t=20, b=20),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        xaxis_title="Calendar Year (Dec 31 balance)",
        yaxis_title="Portfolio Value ($)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Dividend income bar chart
    df_div = df_all.groupby("cal_year")["annual_dividend_income"].sum().reset_index()
    df_div.columns = ["Year", "Dividend Income"]
    if df_div["Dividend Income"].sum() > 0:
        st.subheader("Annual Dividend Income (Cash Paid Out — non-DRIP positions)")
        fig_div = px.bar(
            df_div,
            x="Year",
            y="Dividend Income",
            color_discrete_sequence=["#2ecc71"],
            labels={"Dividend Income": "Dividend Income ($)", "Year": "Calendar Year"},
        )
        fig_div.update_layout(
            height=260,
            margin=dict(t=10, b=10),
            yaxis_tickprefix="$",
            yaxis_tickformat=",.0f",
        )
        fig_div.update_traces(
            hovertemplate="Year %{x}<br>$%{y:,.0f}<extra></extra>"
        )
        st.plotly_chart(fig_div, use_container_width=True)

    # Year-end balance table
    st.subheader("Year-End Balance Table")
    df_table = df_total.copy()
    df_table["Portfolio Value ($)"] = df_table["Portfolio Value"].map("${:,.0f}".format)
    df_table["Growth vs Today"] = (df_table["Portfolio Value"] - current_total).map(
        lambda x: f"+${x:,.0f}" if x >= 0 else f"-${abs(x):,.0f}"
    )
    df_table[""] = df_table["Year"].apply(
        lambda y: "🎯 Retirement" if y == retirement_year else ""
    )
    df_table["Year"] = df_table["Year"].astype(str)
    st.dataframe(
        df_table[["Year", "Portfolio Value ($)", "Growth vs Today", ""]],
        hide_index=True,
        use_container_width=True,
        height=min(400, (len(df_table) + 1) * 35 + 10),
    )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — BY ACCOUNT
# ════════════════════════════════════════════════════════════════════════════

with tab_accounts:
    df_acct = (
        df_all.groupby(["cal_year", "account_name"])["dec31_value"]
        .sum()
        .reset_index()
        .rename(columns={"cal_year": "Year", "account_name": "Account", "dec31_value": "Value"})
    )

    fig_acct = px.line(
        df_acct,
        x="Year",
        y="Value",
        color="Account",
        markers=True,
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"Value": "Portfolio Value ($)", "Year": "Calendar Year"},
    )
    if ret_value:
        fig_acct.add_vline(
            x=retirement_year,
            line_dash="dash",
            line_color="#e74c3c",
            annotation_text=f"Retirement {retirement_year}",
        )
    fig_acct.update_layout(
        height=420,
        margin=dict(t=20, b=30),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.2),
    )
    fig_acct.update_traces(hovertemplate="Dec 31, %{x}<br>$%{y:,.0f}<extra></extra>")
    st.plotly_chart(fig_acct, use_container_width=True)

    # Stacked area
    fig_stack = px.area(
        df_acct,
        x="Year",
        y="Value",
        color="Account",
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"Value": "Portfolio Value ($)", "Year": "Calendar Year"},
    )
    fig_stack.update_layout(
        height=360,
        margin=dict(t=10, b=30),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # Milestone pivot table
    st.subheader("Projected Balance at Milestone Years")
    milestone_cal_yrs = sorted(set(
        [current_year + m for m in MILESTONE_YEARS if current_year + m <= retirement_year]
        + [retirement_year]
    ))
    pivot = df_acct[df_acct["Year"].isin(milestone_cal_yrs)].copy()
    pivot = pivot.pivot(index="Account", columns="Year", values="Value").reset_index()
    pivot.columns.name = None
    for c in pivot.columns:
        if c != "Account":
            pivot[c] = pivot[c].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "—")
    pivot = pivot.rename(columns={retirement_year: f"{retirement_year} 🎯"})
    st.dataframe(pivot, hide_index=True, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — HOLDING DETAIL
# ════════════════════════════════════════════════════════════════════════════

with tab_detail:
    account_names = sorted(df_all["account_name"].unique())
    selected_accounts = st.multiselect(
        "Filter by account", account_names, default=account_names
    )
    df_filtered = df_all[df_all["account_name"].isin(selected_accounts)]

    # Per-ticker line chart
    df_ticker = (
        df_filtered.groupby(["cal_year", "ticker", "account_name"])["dec31_value"]
        .sum()
        .reset_index()
    )
    df_ticker["label"] = df_ticker["ticker"] + " (" + df_ticker["account_name"] + ")"

    fig_tick = px.line(
        df_ticker,
        x="cal_year",
        y="dec31_value",
        color="label",
        markers=True,
        labels={"dec31_value": "Value ($)", "cal_year": "Calendar Year", "label": "Position"},
        color_discrete_sequence=px.colors.qualitative.Alphabet,
    )
    if ret_value:
        fig_tick.add_vline(
            x=retirement_year,
            line_dash="dash",
            line_color="#e74c3c",
            annotation_text=f"Retirement {retirement_year}",
        )
    fig_tick.update_layout(
        height=440,
        margin=dict(t=20, b=40),
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
        legend=dict(orientation="h", y=-0.3, font=dict(size=10)),
    )
    fig_tick.update_traces(hovertemplate="Dec 31, %{x}<br>$%{y:,.0f}<extra></extra>")
    st.plotly_chart(fig_tick, use_container_width=True)

    # Detail table — per holding, milestone year columns
    st.subheader("Position Detail — Dec 31 Balance at Milestone Years")
    milestone_cal_yrs = sorted(set(
        [current_year + m for m in MILESTONE_YEARS if current_year + m <= retirement_year]
        + [retirement_year]
    ))

    detail_rows = []
    for h in all_holdings:
        acct = account_map.get(h["account_id"], {})
        if acct.get("name") not in selected_accounts:
            continue
        val, price = current_holding_value(h)
        if val <= 0:
            continue

        proj = project_by_calendar_year(h, val, price, cal_years)
        proj_map = {r["cal_year"]: r for r in proj}

        payments = FREQ_TO_PAYMENTS.get(h.get("dividend_frequency", "Annual"), 0)
        annual_div = (h.get("dividend_per_unit") or 0) * payments * (h.get("quantity") or 0)
        reinvest = bool(h.get("reinvest_dividends", False))

        row = {
            "Account": acct.get("name", ""),
            "Ticker": h["ticker"],
            "Type": h["asset_type"],
            "Today": f"${val:,.0f}",
            "Growth %": f"{h.get('annual_growth_rate') or 0:.1f}%",
            "Ann. Div": f"${annual_div:,.2f}" if annual_div else "—",
            "DRIP": "Yes" if reinvest else "No",
        }
        for yr in milestone_cal_yrs:
            label = f"{yr} 🎯" if yr == retirement_year else str(yr)
            row[label] = (
                f"${proj_map[yr]['dec31_value']:,.0f}" if yr in proj_map else "—"
            )
        detail_rows.append(row)

    if detail_rows:
        st.dataframe(
            pd.DataFrame(detail_rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No projectable positions in the selected accounts.")
