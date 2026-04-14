# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run the Streamlit app
streamlit run app.py
```

The app opens at `http://localhost:8501`. The SQLite database is created automatically at `~/.personal_finance/finance.db` on first launch.

## Installing Dependencies

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

There are no tests and no linter configured for this project.

## Architecture

This is a Streamlit multi-page app with a clean separation of concerns:

- **[app.py](app.py)** — Home page / entry point. Calls `db.initialize_db()`, resolves live asset prices via `compute_asset_values()`, saves a daily net worth snapshot, and renders KPI cards + charts.
- **[database.py](database.py)** — Pure data-access layer (no Streamlit imports). All CRUD operations against SQLite at `~/.personal_finance/finance.db`. Every function opens/closes its own connection; rows are returned as `list[dict]` via `conn.row_factory = sqlite3.Row`.
- **[market_data.py](market_data.py)** — Stateless fetch helpers. Stocks/ETFs/forex/bonds via `yfinance`; crypto via CoinGecko public API (no key). Returns plain dicts so callers can wrap with `@st.cache_data`.
- **[pages/](pages/)** — Streamlit renders each file as a sidebar page in alphabetical order:
  - `1_Assets.py` — Asset management; batch-fetches live prices upfront
  - `2_Liabilities.py` — Liability management + amortisation schedule calculator
  - `3_Income_Projections.py` — Income sources with stacked bar / area projection charts
  - `4_Market_Rates.py` — Live market browser (indices, stocks, crypto, forex, bonds, watchlist)
  - `5_Investment_Projections.py` — Projects holdings to a configurable retirement date with calendar-year milestones

## Key Design Patterns

**Live price resolution** — `compute_asset_values()` in `app.py` (and `resolve_value()` in `1_Assets.py`) enrich asset dicts with an `effective_value` key: `live_price × quantity` for investable assets, falling back to `manual_value`. Investable categories: `Stocks & ETFs`, `Mutual Funds & Retirement`, `Crypto`.

**Caching** — All `market_data.py` fetch functions should be wrapped with `@st.cache_data(ttl=600)` at the call site in pages. The functions themselves are plain Python so they remain testable and reusable.

**Frequency normalisation** — Income and contribution frequencies are normalised using a multiplier table (`FREQUENCY_TO_MONTHLY` in `app.py`, `FREQ_TO_PAYMENTS` in `5_Investment_Projections.py`). Frequencies: Weekly, Bi-Weekly, Monthly, Quarterly, Semi-Annual, Annual.

**Edit state** — In-progress form edits are tracked in `st.session_state` with keys like `editing_asset_{id}`.

**Adding crypto support** — Edit `CRYPTO_ID_MAP` in [market_data.py](market_data.py) to add `TICKER → CoinGecko ID` mappings. Find IDs at coingecko.com (appears in the coin's page URL).
