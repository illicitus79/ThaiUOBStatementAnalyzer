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

            CREATE TABLE IF NOT EXISTS category_meta (
                name TEXT PRIMARY KEY NOT NULL,
                color TEXT NOT NULL DEFAULT '#b2bec3',
                icon TEXT NOT NULL DEFAULT '📌',
                sort_order INTEGER DEFAULT 999,
                is_builtin INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS category_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                keyword TEXT NOT NULL,
                category_order INTEGER DEFAULT 999
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_cat_kw_unique ON category_rules(UPPER(keyword));
        ''')
        conn.commit()
        _seed_category_rules(conn)
    finally:
        conn.close()


def _seed_category_rules(conn):
    """Seed category_rules and category_meta from hardcoded defaults if empty."""
    existing = conn.execute('SELECT COUNT(*) FROM category_rules').fetchone()[0]
    if existing > 0:
        return

    from categorizer import CATEGORY_RULES, CATEGORY_COLORS, CATEGORY_ICONS

    for sort_order, (category, keywords) in enumerate(CATEGORY_RULES):
        color = CATEGORY_COLORS.get(category, '#b2bec3')
        icon  = CATEGORY_ICONS.get(category, '📌')
        conn.execute(
            'INSERT OR IGNORE INTO category_meta (name, color, icon, sort_order, is_builtin) VALUES (?,?,?,?,1)',
            (category, color, icon, sort_order)
        )
        for keyword in keywords:
            conn.execute(
                'INSERT OR IGNORE INTO category_rules (category, keyword, category_order) VALUES (?,?,?)',
                (category, keyword, sort_order)
            )

    # Ensure "Other" meta entry exists
    other_color = CATEGORY_COLORS.get('Other', '#b2bec3')
    other_icon  = CATEGORY_ICONS.get('Other', '📌')
    conn.execute(
        'INSERT OR IGNORE INTO category_meta (name, color, icon, sort_order, is_builtin) VALUES (?,?,?,999,1)',
        ('Other', other_color, other_icon)
    )
    conn.commit()
