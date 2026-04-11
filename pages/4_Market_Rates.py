"""
Market Rates page — live prices for stocks, crypto, forex, indices, and treasury yields.
Also lets the user maintain a personal watchlist.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import yfinance as yf
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db
import market_data as md

st.set_page_config(page_title="Market Rates", page_icon="📊", layout="wide")
db.initialize_db()


# ── Cached fetchers ───────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def cached_indices():
    return md.fetch_market_indices()

@st.cache_data(ttl=600)
def cached_treasury():
    return md.fetch_treasury_rates()

@st.cache_data(ttl=600)
def cached_forex():
    return md.fetch_forex_rates()

@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))

@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))

@st.cache_data(ttl=3600)
def cached_history(ticker, period, interval):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        return hist
    except Exception:
        return pd.DataFrame()


# ── Helpers ───────────────────────────────────────────────────────────────────

def sparkline_fig(data_series, color="#3498db"):
    fig = go.Figure(go.Scatter(
        y=data_series, mode="lines",
        line=dict(color=color, width=1.5),
    ))
    fig.update_layout(
        height=60, margin=dict(t=0, b=0, l=0, r=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def delta_color(val):
    if val is None:
        return "normal"
    return "normal" if val >= 0 else "inverse"


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("📊 Market Rates")
st.caption(f"Data refreshed every 10 minutes. Last load: {datetime.now().strftime('%H:%M:%S')}")

if st.button("Force Refresh", type="secondary"):
    st.cache_data.clear()
    st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_indices, tab_stocks, tab_crypto, tab_forex, tab_bonds, tab_watchlist = st.tabs([
    "Indices", "Stocks / ETFs", "Crypto", "Forex", "Treasury Yields", "My Watchlist"
])


# ── Market Indices ────────────────────────────────────────────────────────────

with tab_indices:
    st.subheader("Major Market Indices")
    with st.spinner("Fetching index data..."):
        indices_data = cached_indices()

    cols = st.columns(len(indices_data))
    for col, (name, data) in zip(cols, indices_data.items()):
        val = data.get("value")
        chg = data.get("change_pct")
        display = f"{val:,.2f}" if val else "N/A"
        delta_str = f"{chg:+.2f}%" if chg is not None else None
        col.metric(name, display, delta=delta_str, delta_color=delta_color(chg))

    st.divider()
    st.subheader("Index Chart")
    index_options = list(md.INDICES.keys())
    selected_index = st.selectbox("Select Index", index_options)
    period = st.select_slider("Period", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], value="1y")

    ticker = md.INDICES[selected_index]
    hist = cached_history(ticker, period, "1d")
    if not hist.empty:
        fig = go.Figure(go.Candlestick(
            x=hist.index,
            open=hist["Open"],
            high=hist["High"],
            low=hist["Low"],
            close=hist["Close"],
            name=selected_index,
            increasing_line_color="#2ecc71",
            decreasing_line_color="#e74c3c",
        ))
        fig.update_layout(
            height=400, margin=dict(t=20, b=20),
            xaxis_title=None, yaxis_title="Price",
            xaxis_rangeslider_visible=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not fetch historical data.")


# ── Stocks / ETFs ─────────────────────────────────────────────────────────────

with tab_stocks:
    st.subheader("Stock & ETF Lookup")
    col_input, col_period = st.columns([3, 1])
    with col_input:
        raw_input = st.text_input(
            "Enter tickers (comma-separated)",
            value="AAPL, MSFT, GOOGL, AMZN, VOO, QQQ",
            placeholder="AAPL, TSLA, SPY",
        )
    with col_period:
        stock_period = st.selectbox("Chart period", ["1mo", "3mo", "6mo", "1y"], index=2)

    tickers = [t.strip().upper() for t in raw_input.split(",") if t.strip()]

    if tickers:
        with st.spinner("Fetching prices..."):
            prices = cached_stock_prices(tuple(tickers))

        rows = []
        for sym, data in prices.items():
            price = data.get("price")
            rows.append({
                "Symbol": sym,
                "Price": f"${price:,.2f}" if price else "N/A",
                "Price_raw": price or 0,
            })
        df_stocks = pd.DataFrame(rows)
        st.dataframe(
            df_stocks[["Symbol", "Price"]],
            hide_index=True,
            use_container_width=True,
        )

        # Chart for multiple tickers (normalised %)
        if len(tickers) > 0:
            st.subheader("Price Performance (Normalised to 100)")
            fig = go.Figure()
            for sym in tickers[:8]:  # limit to 8 for readability
                hist = cached_history(sym, stock_period, "1d")
                if not hist.empty:
                    normalised = (hist["Close"] / hist["Close"].iloc[0]) * 100
                    fig.add_trace(go.Scatter(x=hist.index, y=normalised, name=sym, mode="lines"))
            fig.update_layout(
                height=380, margin=dict(t=20, b=20),
                yaxis_title="Indexed Value (start=100)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Crypto ────────────────────────────────────────────────────────────────────

with tab_crypto:
    st.subheader("Cryptocurrency Prices")
    st.caption("Powered by CoinGecko free API")

    default_coins = "bitcoin, ethereum, solana, binancecoin, ripple, cardano, dogecoin"
    raw_coins = st.text_input(
        "CoinGecko IDs (comma-separated)",
        value=default_coins,
        help="Use CoinGecko coin IDs e.g. bitcoin, ethereum, solana",
    )
    coin_ids = [c.strip().lower() for c in raw_coins.split(",") if c.strip()]

    if coin_ids:
        with st.spinner("Fetching crypto prices..."):
            crypto_data = cached_crypto_prices(tuple(coin_ids))

        rows = []
        for cid, data in crypto_data.items():
            price = data.get("price_usd")
            chg = data.get("change_24h")
            rows.append({
                "Coin": cid.title(),
                "Price (USD)": f"${price:,.4f}" if price else "N/A",
                "24h Change": f"{chg:+.2f}%" if chg is not None else "N/A",
                "chg_raw": chg or 0,
            })
        df_crypto = pd.DataFrame(rows)

        def style_change(val):
            if "+" in str(val):
                return "color: #2ecc71"
            elif "-" in str(val):
                return "color: #e74c3c"
            return ""

        st.dataframe(
            df_crypto[["Coin", "Price (USD)", "24h Change"]].style.map(
                style_change, subset=["24h Change"]
            ),
            hide_index=True,
            use_container_width=True,
        )

        # 24h change bar chart
        fig = px.bar(
            df_crypto.sort_values("chg_raw"),
            x="chg_raw", y="Coin",
            orientation="h",
            color="chg_raw",
            color_continuous_scale=["#e74c3c", "#f1c40f", "#2ecc71"],
            color_continuous_midpoint=0,
            labels={"chg_raw": "24h Change (%)", "Coin": ""},
        )
        fig.update_layout(coloraxis_showscale=False, height=max(200, len(rows) * 40),
                          margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)


# ── Forex ─────────────────────────────────────────────────────────────────────

with tab_forex:
    st.subheader("Foreign Exchange Rates")
    with st.spinner("Fetching forex rates..."):
        forex_data = cached_forex()

    cols = st.columns(3)
    for i, (pair, data) in enumerate(forex_data.items()):
        rate = data.get("rate")
        display = f"{rate:.4f}" if rate else "N/A"
        cols[i % 3].metric(pair, display)

    st.divider()
    st.subheader("Forex Chart")
    forex_options = list(md.FOREX_PAIRS.keys())
    selected_pair = st.selectbox("Select pair", forex_options)
    forex_period = st.select_slider("Period ", ["1mo", "3mo", "6mo", "1y"], value="6mo")

    fx_ticker = md.FOREX_PAIRS[selected_pair]
    hist = cached_history(fx_ticker, forex_period, "1d")
    if not hist.empty:
        fig = px.line(hist, y="Close", labels={"Close": selected_pair, "Date": ""})
        fig.update_layout(height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not fetch forex history.")


# ── Treasury Yields ───────────────────────────────────────────────────────────

with tab_bonds:
    st.subheader("US Treasury Yields")
    with st.spinner("Fetching treasury rates..."):
        treasury_data = cached_treasury()

    cols = st.columns(len(treasury_data))
    for col, (name, data) in zip(cols, treasury_data.items()):
        rate = data.get("rate")
        display = f"{rate:.2f}%" if rate else "N/A"
        col.metric(name, display)

    st.divider()
    st.subheader("Yield Curve (Historical)")
    selected_bond = st.selectbox("Select treasury", list(md.TREASURY_TICKERS.keys()))
    bond_period = st.select_slider("Period  ", ["3mo", "6mo", "1y", "2y", "5y"], value="1y")

    bond_ticker = md.TREASURY_TICKERS[selected_bond]
    hist = cached_history(bond_ticker, bond_period, "1d")
    if not hist.empty:
        fig = px.line(
            hist, y="Close",
            labels={"Close": "Yield (%)", "Date": ""},
            color_discrete_sequence=["#9b59b6"],
        )
        fig.update_layout(height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not fetch treasury history.")


# ── Watchlist ─────────────────────────────────────────────────────────────────

with tab_watchlist:
    st.subheader("My Watchlist")

    # Add to watchlist form
    with st.form("add_watchlist", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        with col1:
            w_symbol = st.text_input("Symbol / ID", placeholder="AAPL or bitcoin")
        with col2:
            w_name = st.text_input("Label (optional)", placeholder="Apple Inc.")
        with col3:
            w_type = st.selectbox("Type", ["Stock/ETF", "Crypto", "Index", "Forex"])
        with col4:
            st.write("")
            st.write("")
            add_btn = st.form_submit_button("Add", type="primary", use_container_width=True)

        if add_btn and w_symbol:
            db.add_to_watchlist(w_symbol, w_name or w_symbol.upper(), w_type)
            st.success(f"Added {w_symbol.upper()} to watchlist")
            st.rerun()

    watchlist = db.get_watchlist()
    if not watchlist:
        st.info("Your watchlist is empty. Add symbols above.")
    else:
        # Batch-fetch prices
        stock_syms = tuple(w["symbol"] for w in watchlist if w["asset_type"] in ("Stock/ETF", "Index"))
        crypto_syms = tuple(
            md.CRYPTO_ID_MAP.get(w["symbol"].upper(), w["symbol"].lower())
            for w in watchlist if w["asset_type"] == "Crypto"
        )
        forex_syms = tuple(w["symbol"] for w in watchlist if w["asset_type"] == "Forex")

        all_yf_syms = stock_syms + forex_syms
        yf_prices = cached_stock_prices(all_yf_syms) if all_yf_syms else {}
        crypto_prices_map = cached_crypto_prices(crypto_syms) if crypto_syms else {}

        for w in watchlist:
            sym = w["symbol"].upper()
            wtype = w["asset_type"]
            label = w.get("name") or sym
            price = None

            if wtype in ("Stock/ETF", "Index", "Forex"):
                price = yf_prices.get(sym, {}).get("price")
            elif wtype == "Crypto":
                coin_id = md.CRYPTO_ID_MAP.get(sym, sym.lower())
                price = crypto_prices_map.get(coin_id, {}).get("price_usd")

            display = f"${price:,.4f}" if price else "N/A"
            col_sym, col_price, col_type, col_remove = st.columns([2, 2, 1, 1])
            col_sym.write(f"**{label}** `{sym}`")
            col_price.write(display)
            col_type.write(wtype)
            if col_remove.button("Remove", key=f"rm_{sym}", use_container_width=True):
                db.remove_from_watchlist(sym)
                st.rerun()
