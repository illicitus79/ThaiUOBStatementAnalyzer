import os
import hashlib
import logging
from datetime import datetime, date as date_type

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash)
from werkzeug.utils import secure_filename

from database import get_db, init_db
from pdf_parser import parse_statement
from categorizer import categorize, CATEGORY_COLORS, CATEGORY_ICONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'uob-analyzer-2026-secret-key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
init_db()


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _date_clause(params, date_from, date_to, col='t.post_date'):
    clause = ''
    if date_from:
        clause += f' AND {col} >= ?'
        params.append(date_from)
    if date_to:
        clause += f' AND {col} <= ?'
        params.append(date_to)
    return clause


def _stmt_clause(params, statement_id):
    if statement_id and statement_id != 'all':
        params.append(int(statement_id))
        return ' AND t.statement_id = ?'
    return ''


def _account_base(account_num, params):
    """Base JOIN + WHERE filtering to a single account."""
    params.append(account_num)
    return (
        'FROM transactions t '
        'JOIN statements s ON t.statement_id = s.id '
        'WHERE s.account_number = ?'
    )


# ──────────────────────────────────────────────
#  Pages
# ──────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    try:
        # One row per unique account (latest statement's metadata + aggregate counts)
        accounts = db.execute('''
            SELECT s.*,
                   g.statement_count,
                   g.total_txn_count
            FROM statements s
            JOIN (
                SELECT account_number, card_number,
                       MAX(id)      AS max_id,
                       COUNT(*)     AS statement_count,
                       (SELECT COUNT(*) FROM transactions t2
                        JOIN statements s2 ON t2.statement_id = s2.id
                        WHERE s2.account_number = statements.account_number
                          AND s2.card_number    = statements.card_number
                          AND t2.is_credit = 0) AS total_txn_count
                FROM statements
                GROUP BY account_number, card_number
            ) g ON s.id = g.max_id
            ORDER BY s.uploaded_at DESC
        ''').fetchall()
        return render_template('index.html', accounts=[dict(a) for a in accounts])
    finally:
        db.close()


@app.route('/account/<account_num>')
def account_dashboard(account_num):
    db = get_db()
    try:
        # All statements for this account, newest first
        statements = db.execute(
            'SELECT * FROM statements WHERE account_number = ? ORDER BY statement_date DESC',
            (account_num,)
        ).fetchall()

        if not statements:
            flash('Account not found.', 'error')
            return redirect(url_for('index'))

        latest = statements[0]

        # Overall date bounds across all statements for this account
        bounds = db.execute('''
            SELECT MIN(t.post_date) as d_min, MAX(t.post_date) as d_max
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.account_number = ? AND t.is_credit = 0
        ''', (account_num,)).fetchone()

        return render_template(
            'dashboard.html',
            account_num=account_num,
            latest=dict(latest),
            statements=[dict(s) for s in statements],
            date_min=bounds['d_min'] or '',
            date_max=bounds['d_max'] or '',
            category_colors=CATEGORY_COLORS,
            category_icons=CATEGORY_ICONS,
        )
    finally:
        db.close()


# Backward-compat: old /dashboard/<id> links redirect to account dashboard
@app.route('/dashboard/<int:statement_id>')
def dashboard(statement_id):
    db = get_db()
    try:
        stmt = db.execute('SELECT account_number FROM statements WHERE id = ?',
                          (statement_id,)).fetchone()
        if stmt:
            return redirect(url_for('account_dashboard',
                                    account_num=stmt['account_number']))
    finally:
        db.close()
    flash('Statement not found.', 'error')
    return redirect(url_for('index'))


# ──────────────────────────────────────────────
#  Upload
# ──────────────────────────────────────────────

@app.route('/upload', methods=['POST'])
def upload():
    if 'pdf_file' not in request.files:
        flash('No file part in request.', 'error')
        return redirect(url_for('index'))

    file = request.files['pdf_file']
    if not file.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('index'))

    if not file.filename.lower().endswith('.pdf'):
        flash('Only PDF files are supported.', 'error')
        return redirect(url_for('index'))

    raw = file.read()
    file_hash = hashlib.sha256(raw).hexdigest()

    db = get_db()
    try:
        existing = db.execute(
            'SELECT id, account_number, cardholder_name, statement_date '
            'FROM statements WHERE file_hash = ?',
            (file_hash,)
        ).fetchone()

        if existing:
            flash(
                f'Duplicate detected — statement for '
                f'{existing["statement_date"]} already uploaded.',
                'warning'
            )
            return redirect(url_for('account_dashboard',
                                    account_num=existing['account_number']))

        ts = datetime.now().strftime('%Y%m%d_%H%M%S_')
        safe_name = ts + secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        with open(filepath, 'wb') as f:
            f.write(raw)

        try:
            account_info, transactions = parse_statement(filepath)
        except Exception as exc:
            os.remove(filepath)
            logger.exception("PDF parse error")
            flash(f'Could not parse PDF: {exc}', 'error')
            return redirect(url_for('index'))

        if not transactions:
            os.remove(filepath)
            flash('No transactions found. Is this a UOB credit card statement?', 'warning')
            return redirect(url_for('index'))

        account_num = account_info.get('account_number', '')

        cur = db.execute(
            '''INSERT INTO statements
               (filename, account_number, card_number, card_type, cardholder_name,
                statement_date, payment_due_date, credit_line, total_balance,
                minimum_payment, rewards_points, uploaded_at, file_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (
                safe_name, account_num,
                account_info.get('card_number', ''),
                account_info.get('card_type', 'UOB Credit Card'),
                account_info.get('cardholder_name', 'Account Holder'),
                account_info.get('statement_date', ''),
                account_info.get('payment_due_date', ''),
                account_info.get('credit_line', 0),
                account_info.get('total_balance', 0),
                account_info.get('minimum_payment', 0),
                account_info.get('rewards_points', 0),
                datetime.now().isoformat(timespec='seconds'),
                file_hash,
            )
        )
        stmt_id = cur.lastrowid

        for txn in transactions:
            cat = categorize(txn['description'])
            db.execute(
                '''INSERT INTO transactions
                   (statement_id, post_date, trans_date, description, amount,
                    is_credit, category, foreign_currency, foreign_amount)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (stmt_id, txn['post_date'], txn['trans_date'], txn['description'],
                 txn['amount'], 1 if txn['is_credit'] else 0, cat,
                 txn.get('foreign_currency'), txn.get('foreign_amount'))
            )

        db.commit()
        flash(f'Imported {len(transactions)} transactions successfully!', 'success')
        return redirect(url_for('account_dashboard', account_num=account_num))

    except Exception as exc:
        db.rollback()
        logger.exception("Upload error")
        flash(f'Unexpected error: {exc}', 'error')
        return redirect(url_for('index'))
    finally:
        db.close()


@app.route('/statement/<int:statement_id>/delete', methods=['POST'])
def delete_statement(statement_id):
    db = get_db()
    account_num = None
    try:
        stmt = db.execute('SELECT filename, account_number FROM statements WHERE id = ?',
                          (statement_id,)).fetchone()
        if stmt:
            account_num = stmt['account_number']
            fp = os.path.join(app.config['UPLOAD_FOLDER'], stmt['filename'])
            if os.path.exists(fp):
                os.remove(fp)
            db.execute('DELETE FROM transactions WHERE statement_id = ?', (statement_id,))
            db.execute('DELETE FROM statements WHERE id = ?', (statement_id,))
            db.commit()
            flash('Statement removed.', 'success')
    finally:
        db.close()

    # If account still has other statements, go back to its dashboard
    if account_num:
        db2 = get_db()
        try:
            remaining = db2.execute(
                'SELECT id FROM statements WHERE account_number = ?', (account_num,)
            ).fetchone()
        finally:
            db2.close()
        if remaining:
            return redirect(url_for('account_dashboard', account_num=account_num))

    return redirect(url_for('index'))


# ──────────────────────────────────────────────
#  Account-level API
# ──────────────────────────────────────────────

@app.route('/api/account/<account_num>/statements')
def api_account_statements(account_num):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT * FROM statements WHERE account_number = ? ORDER BY statement_date DESC',
            (account_num,)
        ).fetchall()

        result = []
        for s in rows:
            # Get date bounds for this statement
            b = db.execute(
                'SELECT MIN(post_date) as d_min, MAX(post_date) as d_max '
                'FROM transactions WHERE statement_id = ? AND is_credit = 0',
                (s['id'],)
            ).fetchone()
            result.append({**dict(s),
                           'date_min': b['d_min'] or '',
                           'date_max': b['d_max'] or ''})
        return jsonify(result)
    finally:
        db.close()


@app.route('/api/account/<account_num>/summary')
def api_summary(account_num):
    db = get_db()
    try:
        statement_id = request.args.get('statement_id')
        date_from    = request.args.get('from')
        date_to      = request.args.get('to')

        params = []
        base = _account_base(account_num, params) + ' AND t.is_credit = 0'
        base += _stmt_clause(params, statement_id)
        base += _date_clause(params, date_from, date_to)

        stats = db.execute(f'''
            SELECT COUNT(*) as cnt, SUM(t.amount) as total,
                   AVG(t.amount) as avg_amt, MAX(t.amount) as max_amt,
                   MIN(t.post_date) as d_min, MAX(t.post_date) as d_max
            {base}
        ''', params).fetchone()

        top_params = list(params)
        top_cat = db.execute(f'''
            SELECT t.category, SUM(t.amount) as cat_total
            {base}
            GROUP BY t.category ORDER BY cat_total DESC LIMIT 1
        ''', top_params).fetchone()

        # For credit utilization use the selected or latest statement
        stmt_row = None
        if statement_id and statement_id != 'all':
            stmt_row = db.execute('SELECT * FROM statements WHERE id = ?',
                                  (int(statement_id),)).fetchone()
        if not stmt_row:
            stmt_row = db.execute(
                'SELECT * FROM statements WHERE account_number = ? ORDER BY id DESC LIMIT 1',
                (account_num,)
            ).fetchone()

        d_min, d_max = stats['d_min'], stats['d_max']
        days = 1
        if d_min and d_max:
            days = max(1, (date_type.fromisoformat(d_max) -
                           date_type.fromisoformat(d_min)).days + 1)

        total = stats['total'] or 0
        credit_pct = 0.0
        if stmt_row and stmt_row['credit_line']:
            credit_pct = round(stmt_row['total_balance'] / stmt_row['credit_line'] * 100, 1)

        return jsonify({
            'total_spend':       round(total, 2),
            'transaction_count': stats['cnt'],
            'avg_transaction':   round(stats['avg_amt'] or 0, 2),
            'max_transaction':   round(stats['max_amt'] or 0, 2),
            'avg_daily':         round(total / days, 2),
            'top_category':      top_cat['category'] if top_cat else 'N/A',
            'credit_utilization': credit_pct,
            'rewards_points':    stmt_row['rewards_points'] if stmt_row else 0,
            'days_in_period':    days,
        })
    finally:
        db.close()


@app.route('/api/account/<account_num>/category-breakdown')
def api_category_breakdown(account_num):
    db = get_db()
    try:
        params = []
        base = _account_base(account_num, params) + ' AND t.is_credit = 0'
        base += _stmt_clause(params, request.args.get('statement_id'))
        base += _date_clause(params, request.args.get('from'), request.args.get('to'))

        rows = db.execute(f'''
            SELECT t.category, SUM(t.amount) as total, COUNT(*) as cnt
            {base}
            GROUP BY t.category ORDER BY total DESC
        ''', params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/account/<account_num>/daily-spending')
def api_daily_spending(account_num):
    db = get_db()
    try:
        params = []
        base = _account_base(account_num, params) + ' AND t.is_credit = 0'
        base += _stmt_clause(params, request.args.get('statement_id'))
        base += _date_clause(params, request.args.get('from'), request.args.get('to'))

        rows = db.execute(f'''
            SELECT t.post_date, SUM(t.amount) as total, COUNT(*) as cnt
            {base}
            GROUP BY t.post_date ORDER BY t.post_date
        ''', params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/account/<account_num>/top-merchants')
def api_top_merchants(account_num):
    db = get_db()
    try:
        limit = int(request.args.get('limit', 10))
        params = []
        base = _account_base(account_num, params) + ' AND t.is_credit = 0'
        base += _stmt_clause(params, request.args.get('statement_id'))
        base += _date_clause(params, request.args.get('from'), request.args.get('to'))

        rows = db.execute(f'''
            SELECT t.description, t.category, SUM(t.amount) as total, COUNT(*) as cnt
            {base}
            GROUP BY t.description ORDER BY total DESC LIMIT {limit}
        ''', params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/account/<account_num>/transactions')
def api_transactions(account_num):
    db = get_db()
    try:
        category = request.args.get('category')
        search   = request.args.get('q', '').strip()

        params = []
        base = _account_base(account_num, params)
        base += _stmt_clause(params, request.args.get('statement_id'))
        base += _date_clause(params, request.args.get('from'), request.args.get('to'))
        if category and category != 'all':
            base += ' AND t.category = ?'
            params.append(category)
        if search:
            base += ' AND t.description LIKE ?'
            params.append(f'%{search}%')

        rows = db.execute(f'''
            SELECT t.*, s.statement_date as stmt_date
            {base}
            ORDER BY t.post_date DESC, t.id DESC
        ''', params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8080, use_reloader=True)
