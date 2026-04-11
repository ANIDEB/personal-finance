"""
Market data helpers — uses yfinance for stocks/ETFs/indices/forex/bonds,
and the CoinGecko free API (no key needed) for crypto.

All fetch functions return plain dicts so they're easy to cache with
st.cache_data and don't drag Streamlit into this module.
"""

import requests
import yfinance as yf

# ── Indices ──────────────────────────────────────────────────────────────────

INDICES = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    "VIX": "^VIX",
}

# ── Treasury / Bond rates ────────────────────────────────────────────────────

TREASURY_TICKERS = {
    "13-Week T-Bill": "^IRX",
    "5-Year Treasury": "^FVX",
    "10-Year Treasury": "^TNX",
    "30-Year Treasury": "^TYX",
}

# ── Forex ────────────────────────────────────────────────────────────────────

FOREX_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/INR": "USDINR=X",
    "USD/CAD": "USDCAD=X",
    "AUD/USD": "AUDUSD=X",
}


def _safe_last_price(ticker_obj):
    """Return last price from yfinance ticker, handling multiple API quirks."""
    try:
        price = ticker_obj.fast_info.last_price
        if price and price > 0:
            return round(float(price), 4)
    except Exception:
        pass
    try:
        hist = ticker_obj.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:
        pass
    return None


def fetch_stock_prices(symbols: list[str]) -> dict:
    """Fetch current prices for a list of stock/ETF tickers."""
    results = {}
    if not symbols:
        return results
    tickers = yf.Tickers(" ".join(symbols))
    for sym in symbols:
        sym_upper = sym.upper()
        try:
            t = tickers.tickers.get(sym_upper) or yf.Ticker(sym_upper)
            price = _safe_last_price(t)
            info = {}
            try:
                info = t.fast_info
            except Exception:
                pass
            results[sym_upper] = {
                "price": price,
                "currency": getattr(info, "currency", "USD") or "USD",
            }
        except Exception:
            results[sym_upper] = {"price": None, "currency": "USD"}
    return results


def fetch_single_stock_price(symbol: str) -> float | None:
    """Convenience helper for a single ticker."""
    result = fetch_stock_prices([symbol])
    return result.get(symbol.upper(), {}).get("price")


def fetch_market_indices() -> dict:
    """Fetch current values for major market indices."""
    results = {}
    for name, ticker in INDICES.items():
        try:
            t = yf.Ticker(ticker)
            price = _safe_last_price(t)
            # Get previous close for change calculation
            hist = t.history(period="5d")
            if price and len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                change_pct = ((price - prev_close) / prev_close) * 100
            else:
                change_pct = None
            results[name] = {"value": price, "change_pct": change_pct, "ticker": ticker}
        except Exception:
            results[name] = {"value": None, "change_pct": None, "ticker": ticker}
    return results


def fetch_treasury_rates() -> dict:
    """Fetch current US Treasury rates (annualised %)."""
    results = {}
    for name, ticker in TREASURY_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            price = _safe_last_price(t)
            results[name] = {"rate": price}
        except Exception:
            results[name] = {"rate": None}
    return results


def fetch_forex_rates() -> dict:
    """Fetch current forex rates."""
    results = {}
    for pair, ticker in FOREX_PAIRS.items():
        try:
            t = yf.Ticker(ticker)
            price = _safe_last_price(t)
            results[pair] = {"rate": price}
        except Exception:
            results[pair] = {"rate": None}
    return results


def fetch_crypto_prices(coin_ids: list[str]) -> dict:
    """
    Fetch crypto prices via CoinGecko free API.

    coin_ids should be CoinGecko IDs, e.g. ['bitcoin', 'ethereum', 'solana'].
    Returns {id: {price_usd, change_24h}} for each requested coin.
    """
    if not coin_ids:
        return {}
    ids_str = ",".join(coin_ids)
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids_str}&vs_currencies=usd&include_24hr_change=true"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            coin_id: {
                "price_usd": data.get(coin_id, {}).get("usd"),
                "change_24h": data.get(coin_id, {}).get("usd_24h_change"),
            }
            for coin_id in coin_ids
        }
    except Exception:
        return {coin_id: {"price_usd": None, "change_24h": None} for coin_id in coin_ids}


def fetch_single_crypto_price(coin_id: str) -> float | None:
    """Convenience helper for a single crypto coin."""
    result = fetch_crypto_prices([coin_id])
    return result.get(coin_id, {}).get("price_usd")


# Common CoinGecko ID map for convenience (symbol → id)
CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "USDC": "usd-coin",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "MATIC": "matic-network",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "SHIB": "shiba-inu",
}
