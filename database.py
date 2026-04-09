import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'statements.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                account_number TEXT,
                card_number TEXT,
                card_type TEXT DEFAULT 'Credit Card',
                cardholder_name TEXT,
                statement_date TEXT,
                payment_due_date TEXT,
                credit_line REAL DEFAULT 0,
                total_balance REAL DEFAULT 0,
                minimum_payment REAL DEFAULT 0,
                rewards_points INTEGER DEFAULT 0,
                uploaded_at TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement_id INTEGER NOT NULL,
                post_date TEXT,
                trans_date TEXT,
                description TEXT,
                amount REAL DEFAULT 0,
                is_credit INTEGER DEFAULT 0,
                category TEXT DEFAULT 'Other',
                foreign_currency TEXT,
                foreign_amount REAL,
                FOREIGN KEY (statement_id) REFERENCES statements(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_txn_statement ON transactions(statement_id);
            CREATE INDEX IF NOT EXISTS idx_txn_post_date ON transactions(post_date);
            CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category);
        ''')
        conn.commit()
    finally:
        conn.close()
