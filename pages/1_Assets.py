"""
Assets page — add, edit, and delete all asset types.
Investment assets (stocks, ETFs, crypto) show live market values.
"""

import streamlit as st
import plotly.express as px
import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db
import market_data as md

st.set_page_config(page_title="Assets", page_icon="🏦", layout="wide")
db.initialize_db()

CATEGORIES = [
    "Cash & Bank",
    "Stocks & ETFs",
    "Mutual Funds & Retirement",
    "Real Estate",
    "Crypto",
    "Vehicles",
    "Other",
]

INVESTABLE = {"Stocks & ETFs", "Mutual Funds & Retirement", "Crypto"}
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "CHF", "CNY"]


@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))


@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))


def get_live_price(category, ticker, quantity):
    """Return (live_price, current_value) or (None, manual_value)."""
    if not ticker:
        return None, None
    ticker = ticker.upper()

    if category in ("Stocks & ETFs", "Mutual Funds & Retirement"):
        prices = cached_stock_prices((ticker,))
        price = prices.get(ticker, {}).get("price")
        value = price * quantity if price and quantity else None
        return price, value

    if category == "Crypto":
        coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
        prices = cached_crypto_prices((coin_id,))
        price = prices.get(coin_id, {}).get("price_usd")
        value = price * quantity if price and quantity else None
        return price, value

    return None, None


# ── Sidebar: Add / Edit Form ──────────────────────────────────────────────────

def asset_form(prefill=None, form_key="add_asset"):
    """Render the add/edit form. Returns submitted values or None."""
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Asset" if not prefill else "Edit Asset")
        name = st.text_input("Name *", value=defaults.get("name", ""))
        category = st.selectbox(
            "Category *",
            CATEGORIES,
            index=CATEGORIES.index(defaults["category"]) if defaults.get("category") in CATEGORIES else 0,
        )

        is_investable = category in INVESTABLE
        col1, col2 = st.columns(2)
        with col1:
            manual_value = st.number_input(
                "Value / Cost Basis ($)" if is_investable else "Value ($) *",
                min_value=0.0,
                value=float(defaults.get("manual_value", 0)),
                step=100.0,
                format="%.2f",
            )
        with col2:
            currency = st.selectbox(
                "Currency",
                CURRENCIES,
                index=CURRENCIES.index(defaults["currency"]) if defaults.get("currency") in CURRENCIES else 0,
            )

        ticker, quantity = None, None
        if is_investable:
            col3, col4 = st.columns(2)
            with col3:
                hint = "e.g. AAPL, VOO" if category != "Crypto" else "e.g. BTC, ETH"
                ticker = st.text_input("Ticker / Symbol", value=defaults.get("ticker") or "", help=hint)
            with col4:
                quantity = st.number_input(
                    "Quantity / Shares",
                    min_value=0.0,
                    value=float(defaults.get("quantity") or 0),
                    step=0.0001,
                    format="%.4f",
                )

        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=80)
        submitted = st.form_submit_button("Save Asset", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Name is required.")
            return None
        return dict(
            name=name,
            category=category,
            manual_value=manual_value,
            ticker=ticker.upper() if ticker else None,
            quantity=quantity if quantity else None,
            currency=currency,
            notes=notes,
        )
    return None


# ── Main Page ─────────────────────────────────────────────────────────────────

st.title("🏦 Assets")

assets = db.get_all_assets()

# Collect tickers for batch price fetch
stock_tickers = tuple(
    a["ticker"].upper()
    for a in assets
    if a.get("ticker") and a["category"] in ("Stocks & ETFs", "Mutual Funds & Retirement")
)
crypto_symbols = tuple(
    a["ticker"].upper()
    for a in assets
    if a.get("ticker") and a["category"] == "Crypto"
)
stock_prices = cached_stock_prices(stock_tickers) if stock_tickers else {}
crypto_coin_ids = tuple(md.CRYPTO_ID_MAP.get(s, s.lower()) for s in crypto_symbols)
crypto_prices = cached_crypto_prices(crypto_coin_ids) if crypto_coin_ids else {}


def resolve_value(a):
    cat = a["category"]
    ticker = (a.get("ticker") or "").upper()
    qty = a.get("quantity") or 0
    if ticker and cat in ("Stocks & ETFs", "Mutual Funds & Retirement"):
        price = stock_prices.get(ticker, {}).get("price")
        if price and qty:
            return price * qty, price
        return a["manual_value"], price
    if ticker and cat == "Crypto":
        coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
        price = crypto_prices.get(coin_id, {}).get("price_usd")
        if price and qty:
            return price * qty, price
        return a["manual_value"], price
    return a["manual_value"], None


# ── Asset Table ───────────────────────────────────────────────────────────────

tab_view, tab_add = st.tabs(["View Assets", "Add New Asset"])

with tab_view:
    if not assets:
        st.info("No assets yet. Use the **Add New Asset** tab to get started.")
    else:
        total = 0.0
        rows = []
        for a in assets:
            eff_val, live_price = resolve_value(a)
            total += eff_val
            rows.append({
                "id": a["id"],
                "Name": a["name"],
                "Category": a["category"],
                "Ticker": a.get("ticker") or "—",
                "Qty": a.get("quantity") or "—",
                "Live Price": f"${live_price:,.4f}" if live_price else "—",
                "Value": eff_val,
                "Currency": a["currency"],
            })

        df = pd.DataFrame(rows)

        # Category summary
        st.metric("Total Assets", f"${total:,.2f}")

        cat_summary = df.groupby("Category")["Value"].sum().reset_index()
        cat_summary["Value ($)"] = cat_summary["Value"].map("${:,.2f}".format)
        cat_summary = cat_summary.sort_values("Value", ascending=False)

        c1, c2 = st.columns([2, 3])
        with c1:
            st.dataframe(
                cat_summary[["Category", "Value ($)"]],
                hide_index=True,
                use_container_width=True,
            )
        with c2:
            fig = px.bar(
                cat_summary, x="Category", y="Value",
                color="Category",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"Value": "Total Value ($)"},
            )
            fig.update_layout(showlegend=False, height=250,
                              margin=dict(t=10, b=10), yaxis_tickprefix="$")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("All Assets")

        # Show each asset with edit / delete
        for row in rows:
            with st.expander(
                f"**{row['Name']}** — {row['Category']}  |  ${row['Value']:,.2f}",
                expanded=False,
            ):
                asset = next(a for a in assets if a["id"] == row["id"])
                col_info, col_actions = st.columns([3, 1])
                with col_info:
                    if row["Ticker"] != "—":
                        st.write(f"Ticker: `{row['Ticker']}`  |  Qty: {row['Qty']}  |  Live price: {row['Live Price']}")
                    st.write(f"Currency: {row['Currency']}")
                    if asset.get("notes"):
                        st.write(f"Notes: {asset['notes']}")

                with col_actions:
                    edit_key = f"edit_{row['id']}"
                    delete_key = f"del_{row['id']}"

                    if st.button("Edit", key=edit_key, use_container_width=True):
                        st.session_state[f"editing_asset_{row['id']}"] = True
                        st.rerun()

                    if st.button("Delete", key=delete_key, type="secondary", use_container_width=True):
                        db.delete_asset(row["id"])
                        st.success(f"Deleted {row['Name']}")
                        st.rerun()

                # Inline edit form
                if st.session_state.get(f"editing_asset_{row['id']}"):
                    result = asset_form(prefill=dict(asset), form_key=f"edit_form_{row['id']}")
                    if result:
                        db.update_asset(row["id"], **result)
                        del st.session_state[f"editing_asset_{row['id']}"]
                        st.success("Asset updated!")
                        st.rerun()

with tab_add:
    result = asset_form(form_key="main_add_asset")
    if result:
        db.add_asset(**result)
        st.success(f"Asset '{result['name']}' added successfully!")
        st.rerun()
