"""
Liabilities page — track loans, mortgages, credit cards, and more.
Includes amortization schedule preview for instalment loans.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import date

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db

st.set_page_config(page_title="Liabilities", page_icon="💳", layout="wide")
db.initialize_db()

CATEGORIES = [
    "Mortgage",
    "Auto Loan",
    "Student Loan",
    "Credit Card",
    "Personal Loan",
    "Medical Debt",
    "Other",
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "CHF", "CNY"]


# ── Amortization ──────────────────────────────────────────────────────────────

def amortization_schedule(balance, annual_rate, monthly_payment):
    """Generate month-by-month amortization data (max 600 months)."""
    monthly_rate = annual_rate / 100 / 12
    rows = []
    remaining = balance
    month = 0
    while remaining > 0.01 and month < 600:
        month += 1
        interest = remaining * monthly_rate
        principal_paid = min(monthly_payment - interest, remaining)
        if principal_paid <= 0:
            break  # payment too small
        remaining -= principal_paid
        rows.append({
            "Month": month,
            "Payment": monthly_payment,
            "Principal": round(principal_paid, 2),
            "Interest": round(interest, 2),
            "Balance": round(max(remaining, 0), 2),
        })
    return pd.DataFrame(rows)


# ── Form ──────────────────────────────────────────────────────────────────────

def liability_form(prefill=None, form_key="add_liability"):
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Liability" if not prefill else "Edit Liability")

        name = st.text_input("Name *", value=defaults.get("name", ""))
        category = st.selectbox(
            "Category *",
            CATEGORIES,
            index=CATEGORIES.index(defaults["category"]) if defaults.get("category") in CATEGORIES else 0,
        )

        col1, col2 = st.columns(2)
        with col1:
            remaining_balance = st.number_input(
                "Remaining Balance ($) *",
                min_value=0.0,
                value=float(defaults.get("remaining_balance", 0)),
                step=100.0,
                format="%.2f",
            )
            interest_rate = st.number_input(
                "Annual Interest Rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(defaults.get("interest_rate", 0)),
                step=0.01,
                format="%.2f",
            )
        with col2:
            principal = st.number_input(
                "Original Principal ($)",
                min_value=0.0,
                value=float(defaults.get("principal", 0)),
                step=100.0,
                format="%.2f",
            )
            monthly_payment = st.number_input(
                "Monthly Payment ($)",
                min_value=0.0,
                value=float(defaults.get("monthly_payment", 0)),
                step=10.0,
                format="%.2f",
            )

        col3, col4, col5 = st.columns(3)
        with col3:
            currency = st.selectbox(
                "Currency",
                CURRENCIES,
                index=CURRENCIES.index(defaults["currency"]) if defaults.get("currency") in CURRENCIES else 0,
            )
        with col4:
            start_date_val = None
            if defaults.get("start_date"):
                try:
                    start_date_val = date.fromisoformat(defaults["start_date"])
                except Exception:
                    pass
            start_date = st.date_input("Start Date", value=start_date_val)
        with col5:
            due_date_val = None
            if defaults.get("due_date"):
                try:
                    due_date_val = date.fromisoformat(defaults["due_date"])
                except Exception:
                    pass
            due_date = st.date_input("Payoff / Due Date", value=due_date_val)

        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=70)
        submitted = st.form_submit_button("Save Liability", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Name is required.")
            return None
        return dict(
            name=name,
            category=category,
            principal=principal,
            interest_rate=interest_rate,
            monthly_payment=monthly_payment,
            remaining_balance=remaining_balance,
            start_date=start_date.isoformat() if start_date else None,
            due_date=due_date.isoformat() if due_date else None,
            currency=currency,
            notes=notes,
        )
    return None


# ── Main Page ─────────────────────────────────────────────────────────────────

st.title("💳 Liabilities")

liabilities = db.get_all_liabilities()

tab_view, tab_add, tab_amort = st.tabs(["View Liabilities", "Add New Liability", "Amortization Preview"])

with tab_view:
    if not liabilities:
        st.info("No liabilities recorded. Use **Add New Liability** to get started.")
    else:
        total_balance = sum(l["remaining_balance"] for l in liabilities)
        total_monthly = sum(l["monthly_payment"] for l in liabilities)

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Liabilities", f"${total_balance:,.2f}")
        m2.metric("Total Monthly Payments", f"${total_monthly:,.2f}")
        weighted_rate = (
            sum(l["interest_rate"] * l["remaining_balance"] for l in liabilities) / total_balance
            if total_balance else 0
        )
        m3.metric("Weighted Avg Interest Rate", f"{weighted_rate:.2f}%")

        # Category chart
        df = pd.DataFrame(liabilities)
        cat_totals = df.groupby("category")["remaining_balance"].sum().reset_index()
        cat_totals.columns = ["Category", "Balance"]
        fig = px.bar(
            cat_totals.sort_values("Balance", ascending=True),
            x="Balance", y="Category",
            orientation="h",
            color="Category",
            color_discrete_sequence=px.colors.qualitative.Pastel,
            labels={"Balance": "Remaining Balance ($)"},
        )
        fig.update_layout(showlegend=False, height=max(200, len(cat_totals) * 50),
                          margin=dict(t=10, b=10), xaxis_tickprefix="$")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("All Liabilities")

        for l in liabilities:
            rate_str = f"{l['interest_rate']:.2f}%" if l.get("interest_rate") else "N/A"
            with st.expander(
                f"**{l['name']}** — {l['category']}  |  Balance: ${l['remaining_balance']:,.2f}  |  Rate: {rate_str}",
                expanded=False,
            ):
                c1, c2 = st.columns([3, 1])
                with c1:
                    cols_info = st.columns(3)
                    cols_info[0].metric("Balance", f"${l['remaining_balance']:,.2f}")
                    cols_info[1].metric("Monthly Payment", f"${l['monthly_payment']:,.2f}")
                    cols_info[2].metric("Interest Rate", rate_str)
                    if l.get("due_date"):
                        st.write(f"Payoff Date: {l['due_date']}")
                    if l.get("notes"):
                        st.write(f"Notes: {l['notes']}")
                with c2:
                    if st.button("Edit", key=f"edit_l_{l['id']}", use_container_width=True):
                        st.session_state[f"editing_liab_{l['id']}"] = True
                        st.rerun()
                    if st.button("Delete", key=f"del_l_{l['id']}", type="secondary", use_container_width=True):
                        db.delete_liability(l["id"])
                        st.success("Deleted")
                        st.rerun()

                if st.session_state.get(f"editing_liab_{l['id']}"):
                    result = liability_form(prefill=dict(l), form_key=f"edit_liab_{l['id']}")
                    if result:
                        db.update_liability(l["id"], **result)
                        del st.session_state[f"editing_liab_{l['id']}"]
                        st.success("Updated!")
                        st.rerun()

with tab_add:
    result = liability_form(form_key="main_add_liab")
    if result:
        db.add_liability(**result)
        st.success(f"'{result['name']}' added successfully!")
        st.rerun()

with tab_amort:
    st.subheader("Amortization Schedule Preview")
    st.caption("Calculate how a loan pays down over time.")

    if liabilities:
        loan_names = [l["name"] for l in liabilities]
        selected_name = st.selectbox("Select an existing liability, or enter custom values:", ["(Custom)"] + loan_names)

        if selected_name != "(Custom)":
            selected = next(l for l in liabilities if l["name"] == selected_name)
            balance = selected["remaining_balance"]
            rate = selected["interest_rate"]
            payment = selected["monthly_payment"]
        else:
            balance, rate, payment = 0.0, 0.0, 0.0
    else:
        st.info("No saved liabilities — you can still use the custom calculator below.")
        selected_name = "(Custom)"
        balance, rate, payment = 0.0, 0.0, 0.0

    ca, cb, cc = st.columns(3)
    balance = ca.number_input("Balance ($)", min_value=0.0, value=float(balance), step=1000.0, format="%.2f")
    rate = cb.number_input("Annual Rate (%)", min_value=0.0, max_value=100.0, value=float(rate), step=0.01, format="%.2f")
    payment = cc.number_input("Monthly Payment ($)", min_value=0.0, value=float(payment), step=10.0, format="%.2f")

    if balance > 0 and payment > 0:
        schedule = amortization_schedule(balance, rate, payment)
        if schedule.empty:
            st.error("Monthly payment is too small to cover the interest. Increase the payment amount.")
        else:
            payoff_months = len(schedule)
            total_interest = schedule["Interest"].sum()
            payoff_label = f"{payoff_months // 12} yr {payoff_months % 12} mo"

            m1, m2, m3 = st.columns(3)
            m1.metric("Months to Payoff", payoff_label)
            m2.metric("Total Interest Paid", f"${total_interest:,.2f}")
            m3.metric("Total Cost", f"${balance + total_interest:,.2f}")

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=schedule["Month"], y=schedule["Balance"],
                                     name="Balance", line=dict(color="#e74c3c", width=2)))
            fig.add_trace(go.Bar(x=schedule["Month"], y=schedule["Interest"],
                                 name="Interest", marker_color="rgba(231,76,60,0.3)"))
            fig.add_trace(go.Bar(x=schedule["Month"], y=schedule["Principal"],
                                 name="Principal", marker_color="rgba(46,204,113,0.5)"))
            fig.update_layout(
                barmode="stack", height=320,
                margin=dict(t=10, b=10),
                xaxis_title="Month",
                yaxis_tickprefix="$",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("Full Schedule"):
                st.dataframe(
                    schedule.style.format({"Payment": "${:,.2f}", "Principal": "${:,.2f}",
                                           "Interest": "${:,.2f}", "Balance": "${:,.2f}"}),
                    use_container_width=True,
                    height=400,
                )
