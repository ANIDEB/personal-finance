import sqlite3
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path.home() / ".personal_finance" / "finance.db"


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            manual_value REAL NOT NULL DEFAULT 0,
            ticker TEXT,
            quantity REAL,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS liabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            principal REAL NOT NULL DEFAULT 0,
            interest_rate REAL DEFAULT 0,
            monthly_payment REAL DEFAULT 0,
            remaining_balance REAL NOT NULL DEFAULT 0,
            start_date TEXT,
            due_date TEXT,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS income_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            frequency TEXT NOT NULL DEFAULT 'Monthly',
            start_date TEXT,
            end_date TEXT,
            is_active INTEGER DEFAULT 1,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS market_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            name TEXT,
            asset_type TEXT NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS net_worth_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL UNIQUE,
            total_assets REAL NOT NULL DEFAULT 0,
            total_liabilities REAL NOT NULL DEFAULT 0,
            net_worth REAL NOT NULL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS investment_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            institution TEXT,
            account_type TEXT NOT NULL,
            currency TEXT DEFAULT 'USD',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS investment_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES investment_accounts(id) ON DELETE CASCADE,
            ticker TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT 'Stock/ETF',
            quantity REAL NOT NULL DEFAULT 0,
            cost_basis REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add cash_balance to investment_accounts if it doesn't exist yet
    try:
        c.execute("ALTER TABLE investment_accounts ADD COLUMN cash_balance REAL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Migration: add projection fields to investment_holdings
    for col_sql in [
        "ALTER TABLE investment_holdings ADD COLUMN annual_growth_rate REAL DEFAULT 0",
        "ALTER TABLE investment_holdings ADD COLUMN dividend_per_unit REAL DEFAULT 0",
        "ALTER TABLE investment_holdings ADD COLUMN dividend_frequency TEXT DEFAULT 'Annual'",
        "ALTER TABLE investment_holdings ADD COLUMN reinvest_dividends INTEGER DEFAULT 0",
        "ALTER TABLE investment_holdings ADD COLUMN current_value REAL",
    ]:
        try:
            c.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_connection()
    conn.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


# ── Assets ──────────────────────────────────────────────────────────────────

def get_all_assets():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM assets ORDER BY category, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_asset(name, category, manual_value, ticker=None, quantity=None, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO assets (name, category, manual_value, ticker, quantity, currency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, category, manual_value, ticker or None, quantity or None, currency, notes),
    )
    conn.commit()
    conn.close()


def update_asset(asset_id, name, category, manual_value, ticker=None, quantity=None, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """UPDATE assets SET name=?, category=?, manual_value=?, ticker=?, quantity=?,
           currency=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (name, category, manual_value, ticker or None, quantity or None, currency, notes, asset_id),
    )
    conn.commit()
    conn.close()


def delete_asset(asset_id):
    conn = get_connection()
    conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()


# ── Liabilities ──────────────────────────────────────────────────────────────

def get_all_liabilities():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM liabilities ORDER BY category, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_liability(name, category, principal, interest_rate, monthly_payment,
                  remaining_balance, start_date=None, due_date=None, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO liabilities
           (name, category, principal, interest_rate, monthly_payment,
            remaining_balance, start_date, due_date, currency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, category, principal, interest_rate, monthly_payment,
         remaining_balance, start_date, due_date, currency, notes),
    )
    conn.commit()
    conn.close()


def update_liability(liability_id, name, category, principal, interest_rate, monthly_payment,
                     remaining_balance, start_date=None, due_date=None, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """UPDATE liabilities SET name=?, category=?, principal=?, interest_rate=?,
           monthly_payment=?, remaining_balance=?, start_date=?, due_date=?,
           currency=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (name, category, principal, interest_rate, monthly_payment,
         remaining_balance, start_date, due_date, currency, notes, liability_id),
    )
    conn.commit()
    conn.close()


def delete_liability(liability_id):
    conn = get_connection()
    conn.execute("DELETE FROM liabilities WHERE id=?", (liability_id,))
    conn.commit()
    conn.close()


# ── Income Sources ────────────────────────────────────────────────────────────

def get_all_income_sources():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM income_sources ORDER BY category, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_income_source(name, category, amount, frequency, start_date=None,
                      end_date=None, is_active=True, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO income_sources
           (name, category, amount, frequency, start_date, end_date, is_active, currency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, category, amount, frequency, start_date, end_date, 1 if is_active else 0, currency, notes),
    )
    conn.commit()
    conn.close()


def update_income_source(income_id, name, category, amount, frequency, start_date=None,
                         end_date=None, is_active=True, currency="USD", notes=""):
    conn = get_connection()
    conn.execute(
        """UPDATE income_sources SET name=?, category=?, amount=?, frequency=?,
           start_date=?, end_date=?, is_active=?, currency=?, notes=? WHERE id=?""",
        (name, category, amount, frequency, start_date, end_date, 1 if is_active else 0, currency, notes, income_id),
    )
    conn.commit()
    conn.close()


def delete_income_source(income_id):
    conn = get_connection()
    conn.execute("DELETE FROM income_sources WHERE id=?", (income_id,))
    conn.commit()
    conn.close()


# ── Market Watchlist ──────────────────────────────────────────────────────────

def get_watchlist():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM market_watchlist ORDER BY asset_type, symbol").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_watchlist(symbol, name, asset_type):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO market_watchlist (symbol, name, asset_type) VALUES (?, ?, ?)",
            (symbol.upper(), name, asset_type),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # already in watchlist
    conn.close()


def remove_from_watchlist(symbol):
    conn = get_connection()
    conn.execute("DELETE FROM market_watchlist WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()


# ── Net Worth History ─────────────────────────────────────────────────────────

def save_net_worth_snapshot(total_assets, total_liabilities):
    net_worth = total_assets - total_liabilities
    today = date.today().isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO net_worth_history (snapshot_date, total_assets, total_liabilities, net_worth)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(snapshot_date) DO UPDATE SET
             total_assets=excluded.total_assets,
             total_liabilities=excluded.total_liabilities,
             net_worth=excluded.net_worth""",
        (today, total_assets, total_liabilities, net_worth),
    )
    conn.commit()
    conn.close()


def get_net_worth_history(days=365):
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM net_worth_history
           ORDER BY snapshot_date DESC LIMIT ?""",
        (days,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


# ── Investment Accounts ───────────────────────────────────────────────────────

def get_all_investment_accounts():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM investment_accounts ORDER BY institution, name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_investment_account(name, institution, account_type, currency="USD", notes="", cash_balance=0.0):
    conn = get_connection()
    conn.execute(
        """INSERT INTO investment_accounts
           (name, institution, account_type, currency, notes, cash_balance)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, institution or None, account_type, currency, notes, cash_balance or 0.0),
    )
    conn.commit()
    conn.close()


def update_investment_account(account_id, name, institution, account_type, currency="USD", notes="", cash_balance=0.0):
    conn = get_connection()
    conn.execute(
        """UPDATE investment_accounts SET name=?, institution=?, account_type=?,
           currency=?, notes=?, cash_balance=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (name, institution or None, account_type, currency, notes, cash_balance or 0.0, account_id),
    )
    conn.commit()
    conn.close()


def delete_investment_account(account_id):
    conn = get_connection()
    conn.execute("DELETE FROM investment_accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()


# ── Investment Holdings ───────────────────────────────────────────────────────

def get_all_holdings():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM investment_holdings ORDER BY account_id, ticker"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_holdings_for_account(account_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM investment_holdings WHERE account_id=? ORDER BY ticker",
        (account_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_holding(account_id, ticker, asset_type, quantity, cost_basis=None, notes="",
                annual_growth_rate=0.0, dividend_per_unit=0.0,
                dividend_frequency="Annual", reinvest_dividends=False, current_value=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO investment_holdings
           (account_id, ticker, asset_type, quantity, cost_basis, notes,
            annual_growth_rate, dividend_per_unit, dividend_frequency,
            reinvest_dividends, current_value)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, ticker.upper(), asset_type, quantity, cost_basis or None, notes,
         annual_growth_rate or 0.0, dividend_per_unit or 0.0,
         dividend_frequency, 1 if reinvest_dividends else 0,
         current_value or None),
    )
    conn.commit()
    conn.close()


def update_holding(holding_id, ticker, asset_type, quantity, cost_basis=None, notes="",
                   annual_growth_rate=0.0, dividend_per_unit=0.0,
                   dividend_frequency="Annual", reinvest_dividends=False, current_value=None):
    conn = get_connection()
    conn.execute(
        """UPDATE investment_holdings SET ticker=?, asset_type=?, quantity=?,
           cost_basis=?, notes=?, annual_growth_rate=?, dividend_per_unit=?,
           dividend_frequency=?, reinvest_dividends=?, current_value=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (ticker.upper(), asset_type, quantity, cost_basis or None, notes,
         annual_growth_rate or 0.0, dividend_per_unit or 0.0,
         dividend_frequency, 1 if reinvest_dividends else 0,
         current_value or None, holding_id),
    )
    conn.commit()
    conn.close()


def delete_holding(holding_id):
    conn = get_connection()
    conn.execute("DELETE FROM investment_holdings WHERE id=?", (holding_id,))
    conn.commit()
    conn.close()
