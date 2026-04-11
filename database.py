import sqlite3
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path.home() / ".personal_finance" / "finance.db"


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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
