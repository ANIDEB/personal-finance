"""
Income Projections page — manage income sources and visualise future cash flow.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db

st.set_page_config(page_title="Income Projections", page_icon="📈", layout="wide")
db.initialize_db()

CATEGORIES = [
    "Salary / Wages",
    "Freelance / Side Income",
    "Rental Income",
    "Dividends",
    "Interest",
    "Pension / Social Security",
    "Business Income",
    "Other",
]

FREQUENCIES = ["Weekly", "Bi-Weekly", "Monthly", "Quarterly", "Semi-Annual", "Annual"]

FREQ_TO_MONTHLY = {
    "Weekly": 52 / 12,
    "Bi-Weekly": 26 / 12,
    "Monthly": 1,
    "Quarterly": 1 / 3,
    "Semi-Annual": 1 / 6,
    "Annual": 1 / 12,
}

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "INR", "CAD", "AUD", "CHF", "CNY"]


def to_monthly(amount, frequency):
    return amount * FREQ_TO_MONTHLY.get(frequency, 1)


def to_annual(amount, frequency):
    return to_monthly(amount, frequency) * 12


def project_monthly(sources, months=36):
    today = date.today()
    rows = []
    for m in range(months):
        target = today + relativedelta(months=m)
        label = target.strftime("%b %Y")
        month_total = 0.0
        breakdown = {}
        for src in sources:
            if not src["is_active"]:
                continue
            start = date.fromisoformat(src["start_date"]) if src.get("start_date") else None
            end = date.fromisoformat(src["end_date"]) if src.get("end_date") else None
            if start and target.replace(day=1) < start.replace(day=1):
                continue
            if end and target.replace(day=1) > end.replace(day=1):
                continue
            monthly = to_monthly(src["amount"], src["frequency"])
            month_total += monthly
            cat = src["category"]
            breakdown[cat] = breakdown.get(cat, 0) + monthly
        row = {"Month": label, "Total": month_total}
        row.update(breakdown)
        rows.append(row)
    return pd.DataFrame(rows).fillna(0)


# ── Form ──────────────────────────────────────────────────────────────────────

def income_form(prefill=None, form_key="add_income"):
    defaults = prefill or {}
    with st.form(form_key, clear_on_submit=True):
        st.subheader("Add Income Source" if not prefill else "Edit Income Source")

        name = st.text_input("Name *", value=defaults.get("name", ""))
        cat_idx = CATEGORIES.index(defaults["category"]) if defaults.get("category") in CATEGORIES else 0
        category = st.selectbox("Category *", CATEGORIES, index=cat_idx)

        col1, col2, col3 = st.columns(3)
        with col1:
            amount = st.number_input(
                "Amount *",
                min_value=0.0,
                value=float(defaults.get("amount", 0)),
                step=100.0,
                format="%.2f",
            )
        with col2:
            freq_idx = FREQUENCIES.index(defaults["frequency"]) if defaults.get("frequency") in FREQUENCIES else 2
            frequency = st.selectbox("Frequency", FREQUENCIES, index=freq_idx)
        with col3:
            currency = st.selectbox(
                "Currency",
                CURRENCIES,
                index=CURRENCIES.index(defaults["currency"]) if defaults.get("currency") in CURRENCIES else 0,
            )

        col4, col5, col6 = st.columns(3)
        with col4:
            start_val = None
            if defaults.get("start_date"):
                try:
                    start_val = date.fromisoformat(defaults["start_date"])
                except Exception:
                    pass
            start_date = st.date_input("Start Date (optional)", value=start_val)
        with col5:
            end_val = None
            if defaults.get("end_date"):
                try:
                    end_val = date.fromisoformat(defaults["end_date"])
                except Exception:
                    pass
            end_date = st.date_input("End Date (optional)", value=end_val)
        with col6:
            is_active = st.checkbox("Active", value=bool(defaults.get("is_active", True)))

        notes = st.text_area("Notes", value=defaults.get("notes") or "", height=70)
        submitted = st.form_submit_button("Save", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Name is required.")
            return None
        return dict(
            name=name,
            category=category,
            amount=amount,
            frequency=frequency,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            is_active=is_active,
            currency=currency,
            notes=notes,
        )
    return None


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("📈 Income Projections")

sources = db.get_all_income_sources()
active_sources = [s for s in sources if s["is_active"]]

tab_view, tab_add, tab_proj = st.tabs(["Income Sources", "Add New Source", "Projection Charts"])

with tab_view:
    if not sources:
        st.info("No income sources yet. Use **Add New Source** to get started.")
    else:
        m1, m2, m3 = st.columns(3)
        monthly_active = sum(to_monthly(s["amount"], s["frequency"]) for s in active_sources)
        annual_active = monthly_active * 12
        m1.metric("Monthly Income (Active)", f"${monthly_active:,.2f}")
        m2.metric("Annual Income (Active)", f"${annual_active:,.2f}")
        m3.metric("Active Sources", len(active_sources))

        # Category breakdown bar
        cat_data = {}
        for s in active_sources:
            cat_data[s["category"]] = cat_data.get(s["category"], 0) + to_monthly(s["amount"], s["frequency"])
        if cat_data:
            cat_df = pd.DataFrame(list(cat_data.items()), columns=["Category", "Monthly ($)"])
            fig = px.bar(
                cat_df.sort_values("Monthly ($)", ascending=True),
                x="Monthly ($)", y="Category", orientation="h",
                color="Category",
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig.update_layout(showlegend=False, height=max(180, len(cat_df) * 45),
                              margin=dict(t=10, b=10), xaxis_tickprefix="$")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("All Income Sources")
        for src in sources:
            monthly = to_monthly(src["amount"], src["frequency"])
            status = "Active" if src["is_active"] else "Inactive"
            badge = "🟢" if src["is_active"] else "🔴"
            with st.expander(
                f"{badge} **{src['name']}** — {src['category']}  |  "
                f"${monthly:,.2f}/mo  ({src['amount']:,.2f} {src['frequency']})"
            ):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"Status: **{status}**  |  Currency: {src['currency']}")
                    if src.get("start_date"):
                        st.write(f"Period: {src['start_date']} → {src.get('end_date') or 'Ongoing'}")
                    if src.get("notes"):
                        st.write(f"Notes: {src['notes']}")
                with c2:
                    if st.button("Edit", key=f"edit_inc_{src['id']}", use_container_width=True):
                        st.session_state[f"editing_inc_{src['id']}"] = True
                        st.rerun()
                    if st.button("Delete", key=f"del_inc_{src['id']}", type="secondary", use_container_width=True):
                        db.delete_income_source(src["id"])
                        st.success("Deleted")
                        st.rerun()

                if st.session_state.get(f"editing_inc_{src['id']}"):
                    result = income_form(prefill=dict(src), form_key=f"edit_inc_form_{src['id']}")
                    if result:
                        db.update_income_source(src["id"], **result)
                        del st.session_state[f"editing_inc_{src['id']}"]
                        st.success("Updated!")
                        st.rerun()

with tab_add:
    result = income_form(form_key="main_add_income")
    if result:
        db.add_income_source(**result)
        st.success(f"Income source '{result['name']}' added!")
        st.rerun()

with tab_proj:
    st.subheader("Future Income Projection")

    if not active_sources:
        st.info("Add active income sources to see projections.")
    else:
        col_months, col_view = st.columns([1, 3])
        with col_months:
            projection_months = st.slider("Projection window (months)", 6, 60, 24, step=6)
            show_stacked = st.toggle("Stack by category", value=True)

        df_proj = project_monthly(active_sources, months=projection_months)

        category_cols = [c for c in df_proj.columns if c not in ("Month", "Total")]

        with col_view:
            if show_stacked and category_cols:
                fig = px.bar(
                    df_proj,
                    x="Month",
                    y=category_cols,
                    labels={"value": "Income ($)", "variable": "Category"},
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig.update_layout(barmode="stack", height=380,
                                  margin=dict(t=10, b=40),
                                  yaxis_tickprefix="$",
                                  legend=dict(orientation="h", y=-0.2))
            else:
                fig = px.area(
                    df_proj, x="Month", y="Total",
                    labels={"Total": "Total Monthly Income ($)"},
                    color_discrete_sequence=["#3498db"],
                )
                fig.update_layout(height=380, margin=dict(t=10, b=10),
                                  yaxis_tickprefix="$")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("Annual Summary")
        df_proj["Year"] = pd.to_datetime(df_proj["Month"], format="%b %Y").dt.year
        annual = df_proj.groupby("Year")["Total"].sum().reset_index()
        annual.columns = ["Year", "Projected Annual Income"]
        annual["Projected Annual Income ($)"] = annual["Projected Annual Income"].map("${:,.2f}".format)
        st.dataframe(annual[["Year", "Projected Annual Income ($)"]], hide_index=True, use_container_width=True)
