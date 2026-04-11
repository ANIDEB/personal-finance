# Personal Finance Dashboard

A local, privacy-first personal finance tracker built with **Streamlit**. Track your net worth, assets, liabilities, and income — all from a single interactive web dashboard that runs entirely on your machine.

---

## Features

- **Net worth overview** — live KPI cards for total assets, liabilities, net worth, and monthly income
- **Asset tracking** — manual values or live market prices (stocks, ETFs, mutual funds, crypto)
- **Liability management** — loans, mortgages, credit cards with amortisation schedule preview
- **Income projections** — multi-frequency income sources projected up to 60 months into the future
- **Market rates** — live indices, stock/ETF lookup, crypto prices, forex, and US Treasury yields
- **Personal watchlist** — save any ticker/crypto/forex pair for quick reference
- **Net worth history** — daily snapshots stored locally, visualised as an area chart

---

## Project Structure

```
personal-finance/
├── app.py                      # Home page — dashboard entry point
├── database.py                 # SQLite helpers (all CRUD operations)
├── market_data.py              # Market data fetchers (yfinance + CoinGecko)
├── requirements.txt            # Python dependencies
└── pages/
    ├── 1_Assets.py             # Asset management page
    ├── 2_Liabilities.py        # Liability management + amortisation tool
    ├── 3_Income_Projections.py # Income sources + projection charts
    └── 4_Market_Rates.py       # Live market data browser + watchlist
```

Streamlit automatically treats every file in the `pages/` directory as a separate page and renders them in the sidebar in alphabetical order.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Frontend                  │
│  app.py  │  pages/1_Assets  │  pages/2_Liabilities  │
│          │  pages/3_Income  │  pages/4_Market_Rates  │
└────────────────────┬────────────────────────────────┘
                     │ reads/writes
          ┌──────────┴──────────┐
          │     database.py     │  ←─ SQLite at ~/.personal_finance/finance.db
          └─────────────────────┘
                     │
          ┌──────────┴──────────┐
          │   market_data.py    │  ←─ yfinance (stocks/ETFs/forex/bonds)
          └─────────────────────┘    ←─ CoinGecko API (crypto, free, no key)
```

Data never leaves your machine — only outbound calls are to Yahoo Finance and CoinGecko for live prices.

---

## Database Schema

The SQLite database lives at `~/.personal_finance/finance.db` and is created automatically on first run.

| Table | Purpose |
|---|---|
| `assets` | Stocks, crypto, real estate, cash, etc. |
| `liabilities` | Loans, mortgages, credit cards |
| `income_sources` | Salary, dividends, rental income, etc. |
| `market_watchlist` | User's personal ticker watchlist |
| `net_worth_history` | One row per day — assets, liabilities, net worth |

### Key columns

**assets**
- `manual_value` — fallback value used when no live price is available
- `ticker` — optional stock/crypto symbol; triggers a live price lookup
- `quantity` — number of shares/coins; `ticker × quantity = effective_value`

**liabilities**
- `remaining_balance` — the value counted toward total liabilities
- `interest_rate` — annual rate %, used by the amortisation calculator

**income_sources**
- `amount` + `frequency` — every source is normalised to a monthly figure using the multiplier table below
- `is_active` — inactive sources are excluded from projections

---

## Module Reference

### `database.py`

Pure data-access layer. No Streamlit imports — keeps business logic separate from the UI.

| Function | Description |
|---|---|
| `initialize_db()` | Creates all tables if they don't exist |
| `get_all_assets()` / `add_asset()` / `update_asset()` / `delete_asset()` | CRUD for assets |
| `get_all_liabilities()` / `add_liability()` / `update_liability()` / `delete_liability()` | CRUD for liabilities |
| `get_all_income_sources()` / `add_income_source()` / `update_income_source()` / `delete_income_source()` | CRUD for income |
| `get_watchlist()` / `add_to_watchlist()` / `remove_from_watchlist()` | Watchlist management |
| `save_net_worth_snapshot()` | Upserts today's net worth row |
| `get_net_worth_history(days)` | Returns up to `days` daily snapshots (default 365) |

All functions open and close their own SQLite connection. `conn.row_factory = sqlite3.Row` means rows behave like dicts, so results are returned as `list[dict]`.

---

### `market_data.py`

Stateless fetch helpers. Returns plain dicts — no Streamlit types — so results can be cached with `@st.cache_data`.

| Function | Data source | Returns |
|---|---|---|
| `fetch_stock_prices(symbols)` | yfinance | `{TICKER: {price, currency}}` |
| `fetch_single_stock_price(symbol)` | yfinance | `float \| None` |
| `fetch_market_indices()` | yfinance | `{name: {value, change_pct, ticker}}` |
| `fetch_treasury_rates()` | yfinance | `{name: {rate}}` |
| `fetch_forex_rates()` | yfinance | `{pair: {rate}}` |
| `fetch_crypto_prices(coin_ids)` | CoinGecko | `{id: {price_usd, change_24h}}` |
| `fetch_single_crypto_price(coin_id)` | CoinGecko | `float \| None` |

**`CRYPTO_ID_MAP`** — maps common ticker symbols (e.g. `BTC`) to CoinGecko IDs (e.g. `bitcoin`). Add entries here to support more coins.

**`_safe_last_price(ticker_obj)`** — internal helper that tries `fast_info.last_price` first, then falls back to the most recent closing price from `history(period="1d")`, to handle yfinance API quirks.

---

### `app.py` — Home Page

Runs on startup. Key responsibilities:

1. Calls `db.initialize_db()` to ensure tables exist.
2. Loads all assets, liabilities, and income sources from the database.
3. Calls `compute_asset_values()` to resolve live prices for investment assets.
4. Calls `db.save_net_worth_snapshot()` to record today's figures.
5. Renders KPI cards, asset/liability pie charts, net worth history, income projection, and a market snapshot.

**`compute_asset_values(assets)`** — enriches each asset dict with an `effective_value` key:
- For stocks/ETFs/mutual funds: `live_price × quantity` (falls back to `manual_value`)
- For crypto: CoinGecko price × quantity (falls back to `manual_value`)
- For everything else: `manual_value`

**`monthly_income_projection(income_sources, months)`** — iterates month by month, sums all active income sources that are within their `start_date`/`end_date` window, and normalises each to a monthly figure.

**Frequency multipliers** (`FREQUENCY_TO_MONTHLY`):

| Frequency | Multiplier |
|---|---|
| Weekly | 52 / 12 ≈ 4.33 |
| Bi-Weekly | 26 / 12 ≈ 2.17 |
| Monthly | 1 |
| Quarterly | 1 / 3 |
| Semi-Annual | 1 / 6 |
| Annual | 1 / 12 |

---

### Pages

#### `pages/1_Assets.py`

- Batch-fetches live prices for all assets upfront to avoid per-row API calls.
- `resolve_value(asset)` — returns `(effective_value, live_price)` using the same logic as `compute_asset_values` in `app.py`.
- The form (`asset_form`) shows ticker/quantity fields only for investable categories (`Stocks & ETFs`, `Mutual Funds & Retirement`, `Crypto`).
- Edit state is stored in `st.session_state` with key `editing_asset_{id}`.

#### `pages/2_Liabilities.py`

- `amortization_schedule(balance, annual_rate, monthly_payment)` — generates a month-by-month table (up to 600 months) showing principal, interest, and remaining balance. Used in the **Amortization Preview** tab.
- Displays weighted average interest rate across all liabilities.

#### `pages/3_Income_Projections.py`

- `project_monthly(sources, months)` — returns a DataFrame with one row per month and one column per income category, suitable for stacked bar charts.
- The **Projection Charts** tab includes a slider (6–60 months) and a toggle between stacked-by-category bars and a total area chart.
- The **Annual Summary** table groups projected monthly income by year.

#### `pages/4_Market_Rates.py`

Six tabs: Indices, Stocks/ETFs, Crypto, Forex, Treasury Yields, My Watchlist.

- All fetch calls are wrapped with `@st.cache_data(ttl=600)` — prices refresh every 10 minutes.
- Historical OHLC charts use `go.Candlestick` (indices) or `px.line` (forex/bonds).
- The stock comparison chart normalises all tickers to 100 at the start of the selected period so different price scales are comparable.
- `sparkline_fig()` — renders a tiny 60px-tall line chart with no axes for inline sparklines.
- The watchlist persists in the database; prices for all watchlist items are batch-fetched on every page load.

---

## Setup

### Prerequisites

- Python 3.11+
- `pip`

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/personal-finance.git
cd personal-finance

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. The SQLite database is created automatically at `~/.personal_finance/finance.db` on first launch.

---

## Adding Support for More Cryptocurrencies

Edit `CRYPTO_ID_MAP` in [market_data.py](market_data.py) to add a symbol → CoinGecko ID mapping:

```python
CRYPTO_ID_MAP = {
    ...
    "PEPE": "pepe",   # add new entries here
}
```

Find the correct CoinGecko ID by searching at [coingecko.com](https://www.coingecko.com) — it appears in the URL of the coin's page.

---

## Dependencies

| Package | Purpose |
|---|---|
| `streamlit` | Web UI framework |
| `yfinance` | Stock, ETF, index, forex, and bond data |
| `plotly` | Interactive charts |
| `pandas` | Data manipulation |
| `requests` | HTTP calls to CoinGecko |
| `numpy` | Numerical helpers (amortisation) |
| `python-dateutil` | `relativedelta` for month arithmetic |

---

## Data Privacy

All financial data is stored **locally** in a SQLite file at `~/.personal_finance/finance.db`. The only network requests made are:

- Yahoo Finance (via `yfinance`) — for stock, ETF, index, forex, and bond prices
- CoinGecko public API — for cryptocurrency prices (no API key required)

No data is sent to any third-party analytics or tracking service.
