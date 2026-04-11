"""
Assets page — track general assets and investment accounts.
Investment accounts hold individual positions tracked by ticker and quantity,
with live market prices pulled automatically.
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

# ── Constants ─────────────────────────────────────────────────────────────────

GENERAL_CATEGORIES = ["Cash & Bank", "Real Estate", "Vehicles", "Other"]

ACCOUNT_TYPES = [
    "Taxable Brokerage",
    "Roth IRA",
    "Traditional IRA",
    "401(k)",
    "403(b)",
    "HSA",
    "Crypto Exchange",
    "529 Plan",
    "Other",
]

HOLDING_TYPES = ["Stock/ETF", "Mutual Fund", "Crypto"]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "CHF", "CNY"]


# ── Market data (cached 10 min) ───────────────────────────────────────────────

@st.cache_data(ttl=600)
def cached_stock_prices(tickers_tuple):
    return md.fetch_stock_prices(list(tickers_tuple))


@st.cache_data(ttl=600)
def cached_crypto_prices(ids_tuple):
    return md.fetch_crypto_prices(list(ids_tuple))


def resolve_holding(h, stock_prices, crypto_prices):
    """Return (live_price, effective_value, gain_loss) for a holding dict."""
    ticker = h["ticker"].upper()
    qty = h.get("quantity") or 0
    cost_basis = h.get("cost_basis")

    price = None
    if h["asset_type"] in ("Stock/ETF", "Mutual Fund"):
        price = stock_prices.get(ticker, {}).get("price")
    elif h["asset_type"] == "Crypto":
        coin_id = md.CRYPTO_ID_MAP.get(ticker, ticker.lower())
        price = crypto_prices.get(coin_id, {}).get("price_usd")

    value = (price * qty) if price and qty else 0.0
    gain_loss = (value - cost_basis * qty) if (cost_basis and value) else None
    return price, value, gain_loss


# ── Forms ─────────────────────────────────────────────────────────────────────

def asset_form(prefill=None, form_key="add_asset"):
    """Form for non-investment assets (cash, real estate, vehicles, other)."""
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Asset" if not prefill else "Edit Asset")
        name = st.text_input("Name *", value=defaults.get("name", ""))
        category = st.selectbox(
            "Category *",
            GENERAL_CATEGORIES,
            index=GENERAL_CATEGORIES.index(defaults["category"])
            if defaults.get("category") in GENERAL_CATEGORIES else 0,
        )
        col1, col2 = st.columns(2)
        with col1:
            manual_value = st.number_input(
                "Value ($) *",
                min_value=0.0,
                value=float(defaults.get("manual_value", 0)),
                step=100.0,
                format="%.2f",
            )
        with col2:
            currency = st.selectbox(
                "Currency",
                CURRENCIES,
                index=CURRENCIES.index(defaults["currency"])
                if defaults.get("currency") in CURRENCIES else 0,
            )
        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=80)
        submitted = st.form_submit_button("Save Asset", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Name is required.")
            return None
        return dict(name=name, category=category, manual_value=manual_value,
                    ticker=None, quantity=None, currency=currency, notes=notes)
    return None


def account_form(prefill=None, form_key="add_account"):
    """Form to create or edit a brokerage/investment account."""
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Account" if not prefill else "Edit Account")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Account Name *", value=defaults.get("name", ""),
                                  placeholder="e.g. Fidelity Roth IRA")
        with col2:
            institution = st.text_input("Institution", value=defaults.get("institution") or "",
                                         placeholder="e.g. Fidelity, Schwab, Coinbase")
        col3, col4 = st.columns(2)
        with col3:
            account_type = st.selectbox(
                "Account Type *",
                ACCOUNT_TYPES,
                index=ACCOUNT_TYPES.index(defaults["account_type"])
                if defaults.get("account_type") in ACCOUNT_TYPES else 0,
            )
        with col4:
            currency = st.selectbox(
                "Currency",
                CURRENCIES,
                index=CURRENCIES.index(defaults["currency"])
                if defaults.get("currency") in CURRENCIES else 0,
            )
        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=70)
        submitted = st.form_submit_button("Save Account", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Account name is required.")
            return None
        return dict(name=name, institution=institution, account_type=account_type,
                    currency=currency, notes=notes)
    return None


def holding_form(account_id, prefill=None, form_key="add_holding"):
    """Form to add or edit a single position within an account."""
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Position" if not prefill else "Edit Position")
        col1, col2, col3 = st.columns(3)
        with col1:
            asset_type = st.selectbox(
                "Type",
                HOLDING_TYPES,
                index=HOLDING_TYPES.index(defaults["asset_type"])
                if defaults.get("asset_type") in HOLDING_TYPES else 0,
            )
        with col2:
            ticker = st.text_input(
                "Ticker / Symbol *",
                value=defaults.get("ticker", ""),
                help="e.g. AAPL, VOO, VTSAX  —  or BTC, ETH for crypto",
            )
        with col3:
            quantity = st.number_input(
                "Quantity / Shares *",
                min_value=0.0,
                value=float(defaults.get("quantity", 0)),
                step=0.0001,
                format="%.4f",
            )
        cost_basis = st.number_input(
            "Cost Basis per Share ($)  —  optional",
            min_value=0.0,
            value=float(defaults.get("cost_basis") or 0),
            step=0.01,
            format="%.4f",
            help="Your average purchase price per share. Used to calculate unrealised gain/loss.",
        )
        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=60)
        submitted = st.form_submit_button("Save Position", type="primary", use_container_width=True)

    if submitted:
        if not ticker:
            st.error("Ticker is required.")
            return None
        if not quantity:
            st.error("Quantity must be greater than 0.")
            return None
        return dict(
            account_id=account_id,
            ticker=ticker.upper().strip(),
            asset_type=asset_type,
            quantity=quantity,
            cost_basis=cost_basis if cost_basis > 0 else None,
            notes=notes,
        )
    return None


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("🏦 Assets")

tab_general, tab_investment = st.tabs(["General Assets", "Investment Accounts"])


# ════════════════════════════════════════════════════════════════════════════
# GENERAL ASSETS
# ════════════════════════════════════════════════════════════════════════════

with tab_general:
    st.caption("Cash, real estate, vehicles, and other non-investment property.")

    all_assets = db.get_all_assets()
    general_assets = [a for a in all_assets if a["category"] in GENERAL_CATEGORIES]

    sub_view, sub_add = st.tabs(["View", "Add New Asset"])

    with sub_view:
        if not general_assets:
            st.info("No general assets yet. Use the **Add New Asset** tab to get started.")
        else:
            total = sum(a["manual_value"] for a in general_assets)
            st.metric("Total General Assets", f"${total:,.2f}")

            rows = [
                {"id": a["id"], "Name": a["name"], "Category": a["category"],
                 "Value": a["manual_value"], "Currency": a["currency"]}
                for a in general_assets
            ]
            df = pd.DataFrame(rows)
            cat_summary = (
                df.groupby("Category")["Value"].sum()
                .reset_index()
                .sort_values("Value", ascending=False)
            )
            cat_summary["Value ($)"] = cat_summary["Value"].map("${:,.2f}".format)

            c1, c2 = st.columns([2, 3])
            with c1:
                st.dataframe(cat_summary[["Category", "Value ($)"]], hide_index=True,
                             use_container_width=True)
            with c2:
                fig = px.bar(cat_summary, x="Category", y="Value", color="Category",
                             color_discrete_sequence=px.colors.qualitative.Set2,
                             labels={"Value": "Total Value ($)"})
                fig.update_layout(showlegend=False, height=220,
                                  margin=dict(t=10, b=10), yaxis_tickprefix="$")
                st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.subheader("All General Assets")
            for row in rows:
                asset = next(a for a in general_assets if a["id"] == row["id"])
                with st.expander(
                    f"**{row['Name']}** — {row['Category']}  |  ${row['Value']:,.2f}",
                    expanded=False,
                ):
                    c_info, c_act = st.columns([3, 1])
                    with c_info:
                        st.write(f"Currency: {row['Currency']}")
                        if asset.get("notes"):
                            st.write(f"Notes: {asset['notes']}")
                    with c_act:
                        if st.button("Edit", key=f"edit_a_{row['id']}", use_container_width=True):
                            st.session_state[f"editing_asset_{row['id']}"] = True
                            st.rerun()
                        if st.button("Delete", key=f"del_a_{row['id']}", type="secondary",
                                     use_container_width=True):
                            db.delete_asset(row["id"])
                            st.success(f"Deleted {row['Name']}")
                            st.rerun()
                    if st.session_state.get(f"editing_asset_{row['id']}"):
                        result = asset_form(prefill=dict(asset),
                                            form_key=f"edit_form_{row['id']}")
                        if result:
                            db.update_asset(row["id"], **result)
                            del st.session_state[f"editing_asset_{row['id']}"]
                            st.success("Asset updated!")
                            st.rerun()

    with sub_add:
        result = asset_form(form_key="main_add_asset")
        if result:
            db.add_asset(**result)
            st.success(f"Asset '{result['name']}' added successfully!")
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# INVESTMENT ACCOUNTS
# ════════════════════════════════════════════════════════════════════════════

with tab_investment:
    st.caption(
        "Organise investments by brokerage account. "
        "Each account holds positions tracked by ticker and quantity — "
        "live prices are fetched automatically."
    )

    accounts = db.get_all_investment_accounts()
    all_holdings = db.get_all_holdings()

    # ── Batch-fetch all live prices upfront ──────────────────────────────────
    stock_tickers = tuple(
        h["ticker"].upper()
        for h in all_holdings
        if h["asset_type"] in ("Stock/ETF", "Mutual Fund")
    )
    crypto_syms_raw = [
        h["ticker"].upper() for h in all_holdings if h["asset_type"] == "Crypto"
    ]
    crypto_ids = tuple(md.CRYPTO_ID_MAP.get(s, s.lower()) for s in crypto_syms_raw)

    stock_prices = cached_stock_prices(stock_tickers) if stock_tickers else {}
    crypto_prices = cached_crypto_prices(crypto_ids) if crypto_ids else {}

    # Per-account value totals
    account_totals: dict[int, float] = {a["id"]: 0.0 for a in accounts}
    for h in all_holdings:
        _, val, _ = resolve_holding(h, stock_prices, crypto_prices)
        account_totals[h["account_id"]] = account_totals.get(h["account_id"], 0.0) + val

    inv_view, inv_add = st.tabs(["View Accounts", "Add New Account"])

    # ── View Accounts ─────────────────────────────────────────────────────────
    with inv_view:
        if not accounts:
            st.info("No investment accounts yet. Use **Add New Account** to create one.")
        else:
            total_inv = sum(account_totals.values())
            st.metric("Total Investment Value", f"${total_inv:,.2f}")

            # Allocation pie by account type
            type_totals: dict[str, float] = {}
            for a in accounts:
                t = a["account_type"]
                type_totals[t] = type_totals.get(t, 0.0) + account_totals[a["id"]]
            if any(v > 0 for v in type_totals.values()):
                df_types = pd.DataFrame(type_totals.items(), columns=["Account Type", "Value"])
                fig = px.pie(df_types, names="Account Type", values="Value", hole=0.45,
                             color_discrete_sequence=px.colors.qualitative.Set2)
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(showlegend=True, height=280, margin=dict(t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

            st.divider()

            for acct in accounts:
                acct_total = account_totals[acct["id"]]
                institution_str = f" · {acct['institution']}" if acct.get("institution") else ""
                with st.expander(
                    f"**{acct['name']}**{institution_str}  —  "
                    f"{acct['account_type']}  |  ${acct_total:,.2f}",
                    expanded=False,
                ):
                    # ── Account header actions ────────────────────────────────
                    c_info, c_acct_act = st.columns([3, 1])
                    with c_info:
                        st.write(f"Currency: {acct['currency']}")
                        if acct.get("notes"):
                            st.write(f"Notes: {acct['notes']}")
                    with c_acct_act:
                        if st.button("Edit Account", key=f"edit_acct_{acct['id']}",
                                     use_container_width=True):
                            st.session_state[f"editing_acct_{acct['id']}"] = True
                            st.rerun()
                        if st.button("Delete Account", key=f"del_acct_{acct['id']}",
                                     type="secondary", use_container_width=True):
                            db.delete_investment_account(acct["id"])
                            st.success(f"Deleted '{acct['name']}'")
                            st.rerun()

                    if st.session_state.get(f"editing_acct_{acct['id']}"):
                        result = account_form(prefill=dict(acct),
                                              form_key=f"edit_acct_form_{acct['id']}")
                        if result:
                            db.update_investment_account(acct["id"], **result)
                            del st.session_state[f"editing_acct_{acct['id']}"]
                            st.success("Account updated!")
                            st.rerun()

                    st.divider()

                    # ── Holdings table ────────────────────────────────────────
                    holdings = [h for h in all_holdings if h["account_id"] == acct["id"]]

                    if holdings:
                        h_rows = []
                        for h in holdings:
                            price, val, gl = resolve_holding(h, stock_prices, crypto_prices)
                            h_rows.append({
                                "id": h["id"],
                                "Ticker": h["ticker"],
                                "Type": h["asset_type"],
                                "Quantity": h["quantity"],
                                "Live Price": f"${price:,.4f}" if price else "—",
                                "Market Value": f"${val:,.2f}" if val else "—",
                                "Cost Basis/sh": (
                                    f"${h['cost_basis']:,.4f}" if h.get("cost_basis") else "—"
                                ),
                                "Gain / Loss": (
                                    f"${gl:+,.2f}" if gl is not None else "—"
                                ),
                                "_gl": gl,
                            })

                        def _style_gl(v):
                            if isinstance(v, str) and v.startswith("$"):
                                try:
                                    num = float(v.replace("$", "").replace(",", ""))
                                    return "color: #2ecc71" if num >= 0 else "color: #e74c3c"
                                except Exception:
                                    pass
                            return ""

                        display_cols = [
                            "Ticker", "Type", "Quantity",
                            "Live Price", "Market Value", "Cost Basis/sh", "Gain / Loss",
                        ]
                        styled = (
                            pd.DataFrame(h_rows)[display_cols]
                            .style.applymap(_style_gl, subset=["Gain / Loss"])
                        )
                        st.dataframe(styled, hide_index=True, use_container_width=True)

                        # Per-row edit / remove
                        st.caption("Edit or remove individual positions:")
                        for h_row in h_rows:
                            holding = next(h for h in holdings if h["id"] == h_row["id"])
                            hc1, hc2, hc3 = st.columns([4, 1, 1])
                            hc1.write(
                                f"`{h_row['Ticker']}` — "
                                f"{h_row['Quantity']} × {h_row['Live Price']} "
                                f"= **{h_row['Market Value']}**"
                            )
                            if hc2.button("Edit", key=f"edit_h_{h_row['id']}",
                                          use_container_width=True):
                                st.session_state[f"editing_holding_{h_row['id']}"] = True
                                st.rerun()
                            if hc3.button("Remove", key=f"del_h_{h_row['id']}",
                                          type="secondary", use_container_width=True):
                                db.delete_holding(h_row["id"])
                                st.success(f"Removed {h_row['Ticker']}")
                                st.rerun()

                            if st.session_state.get(f"editing_holding_{h_row['id']}"):
                                edit_result = holding_form(
                                    account_id=acct["id"],
                                    prefill=dict(holding),
                                    form_key=f"edit_holding_form_{h_row['id']}",
                                )
                                if edit_result:
                                    db.update_holding(
                                        h_row["id"],
                                        ticker=edit_result["ticker"],
                                        asset_type=edit_result["asset_type"],
                                        quantity=edit_result["quantity"],
                                        cost_basis=edit_result["cost_basis"],
                                        notes=edit_result["notes"],
                                    )
                                    del st.session_state[f"editing_holding_{h_row['id']}"]
                                    st.success("Position updated!")
                                    st.rerun()
                    else:
                        st.info("No positions in this account yet.")

                    # ── Add new position ──────────────────────────────────────
                    st.subheader("Add Position")
                    new_holding = holding_form(
                        account_id=acct["id"],
                        form_key=f"add_holding_{acct['id']}",
                    )
                    if new_holding:
                        db.add_holding(**new_holding)
                        st.success(f"Added {new_holding['ticker']} to {acct['name']}")
                        st.rerun()

    # ── Add New Account ───────────────────────────────────────────────────────
    with inv_add:
        result = account_form(form_key="main_add_account")
        if result:
            db.add_investment_account(**result)
            st.success(f"Account '{result['name']}' added successfully!")
            st.rerun()
