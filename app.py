import os
import hashlib
import logging
from datetime import datetime, date as date_type

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash)
from werkzeug.utils import secure_filename

from database import get_db, init_db
from pdf_parser import parse_statement
from categorizer import (categorize, CATEGORY_COLORS, CATEGORY_ICONS,
                         invalidate_rules_cache)

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
        account_rows = [dict(a) for a in accounts]
        summary = {
            'account_count': len(account_rows),
            'statement_total': sum((a.get('statement_count') or 0) for a in account_rows),
            'total_balance': sum((a.get('total_balance') or 0) for a in account_rows),
            'total_credit_line': sum((a.get('credit_line') or 0) for a in account_rows),
            'total_rewards': sum((a.get('rewards_points') or 0) for a in account_rows),
        }
        summary['overall_util'] = (
            round(summary['total_balance'] / summary['total_credit_line'] * 100, 1)
            if summary['total_credit_line'] else 0
        )
        return render_template('index.html', accounts=account_rows, summary=summary)
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

        # ── Previous period comparison ──
        all_stmts = db.execute(
            'SELECT id FROM statements WHERE account_number = ? ORDER BY statement_date DESC',
            (account_num,)
        ).fetchall()
        stmt_ids = [s['id'] for s in all_stmts]

        current_idx = 0
        if statement_id and statement_id != 'all':
            sid = int(statement_id)
            if sid in stmt_ids:
                current_idx = stmt_ids.index(sid)

        prev_total, prev_count, prev_avg_daily = 0, 0, 0
        has_prev = current_idx + 1 < len(stmt_ids)
        if has_prev:
            prev_sid = stmt_ids[current_idx + 1]
            prev_stats = db.execute(
                'SELECT COUNT(*) as cnt, SUM(t.amount) as total, '
                'MIN(t.post_date) as d_min, MAX(t.post_date) as d_max '
                'FROM transactions t JOIN statements s ON t.statement_id = s.id '
                'WHERE s.account_number = ? AND t.statement_id = ? AND t.is_credit = 0',
                (account_num, prev_sid)
            ).fetchone()
            if prev_stats and prev_stats['total']:
                p_days = 1
                if prev_stats['d_min'] and prev_stats['d_max']:
                    p_days = max(1, (date_type.fromisoformat(prev_stats['d_max']) -
                                     date_type.fromisoformat(prev_stats['d_min'])).days + 1)
                prev_total      = round(prev_stats['total'] or 0, 2)
                prev_count      = prev_stats['cnt']
                prev_avg_daily  = round(prev_total / p_days, 2)

        # ── Credits / refunds in the same period ──
        cr_params = [account_num]
        cr_clause = ''
        if statement_id and statement_id != 'all':
            cr_clause += ' AND t.statement_id = ?'
            cr_params.append(int(statement_id))
        if date_from:
            cr_clause += ' AND t.post_date >= ?'
            cr_params.append(date_from)
        if date_to:
            cr_clause += ' AND t.post_date <= ?'
            cr_params.append(date_to)

        cr_stats = db.execute(f'''
            SELECT COUNT(*) as cnt,
                   COALESCE(SUM(t.amount), 0) as total,
                   COALESCE(MAX(t.amount), 0) as max_amt
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.account_number = ? AND t.is_credit = 1{cr_clause}
        ''', cr_params).fetchone()

        return jsonify({
            'total_spend':            round(total, 2),
            'transaction_count':      stats['cnt'],
            'avg_transaction':        round(stats['avg_amt'] or 0, 2),
            'max_transaction':        round(stats['max_amt'] or 0, 2),
            'avg_daily':              round(total / days, 2),
            'top_category':           top_cat['category'] if top_cat else 'N/A',
            'credit_utilization':     credit_pct,
            'rewards_points':         stmt_row['rewards_points'] if stmt_row else 0,
            'days_in_period':         days,
            'date_from':              d_min or date_from or '',
            'date_to':                d_max or date_to or '',
            'has_prev':               has_prev,
            'prev_total_spend':       prev_total,
            'prev_transaction_count': prev_count,
            'prev_avg_daily':         prev_avg_daily,
            'total_credits':          round(cr_stats['total'], 2),
            'credit_count':           cr_stats['cnt'],
            'max_credit':             round(cr_stats['max_amt'], 2),
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


# ──────────────────────────────────────────────
#  Month-over-Month comparison
# ──────────────────────────────────────────────

@app.route('/api/account/<account_num>/monthly-comparison')
def api_monthly_comparison(account_num):
    """Per-statement, per-category spend totals — used for the MoM stacked bar chart."""
    db = get_db()
    try:
        rows = db.execute('''
            SELECT s.id AS stmt_id, s.statement_date,
                   t.category, SUM(t.amount) AS total, COUNT(*) AS cnt
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.account_number = ? AND t.is_credit = 0
            GROUP BY s.id, t.category
            ORDER BY s.id ASC, t.category
        ''', (account_num,)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


# ──────────────────────────────────────────────
#  Recurring transaction detection
# ──────────────────────────────────────────────

@app.route('/api/account/<account_num>/recurring')
def api_recurring(account_num):
    """
    Merchants that appear in 2+ distinct statements.
    is_fixed=True when max/min amount variance is <10% of the average (likely a subscription).
    """
    db = get_db()
    try:
        rows = db.execute('''
            SELECT t.description, t.category,
                   COUNT(DISTINCT t.statement_id)            AS stmt_count,
                   COUNT(*)                                  AS txn_count,
                   ROUND(AVG(t.amount), 2)                   AS avg_amount,
                   ROUND(MIN(t.amount), 2)                   AS min_amount,
                   ROUND(MAX(t.amount), 2)                   AS max_amount,
                   ROUND(SUM(t.amount), 2)                   AS total_amount,
                   GROUP_CONCAT(DISTINCT s.statement_date)   AS months
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            WHERE s.account_number = ? AND t.is_credit = 0
            GROUP BY UPPER(t.description)
            HAVING stmt_count >= 2
            ORDER BY stmt_count DESC, total_amount DESC
        ''', (account_num,)).fetchall()

        result = []
        for r in rows:
            avg = r['avg_amount'] or 0
            variance = (r['max_amount'] - r['min_amount']) / avg if avg else 0
            result.append({
                **dict(r),
                'is_fixed': variance < 0.10,
            })
        return jsonify(result)
    finally:
        db.close()


# ──────────────────────────────────────────────
#  Recategorize
# ──────────────────────────────────────────────

def _do_recategorize(db, account_num=None):
    """
    Re-apply current categorizer rules to every transaction.
    If account_num is given, only that account's transactions are updated.
    Returns (total_checked, total_changed).
    """
    if account_num:
        rows = db.execute(
            'SELECT t.id, t.description, t.category '
            'FROM transactions t '
            'JOIN statements s ON t.statement_id = s.id '
            'WHERE s.account_number = ?',
            (account_num,)
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT id, description, category FROM transactions'
        ).fetchall()

    changed = 0
    for row in rows:
        new_cat = categorize(row['description'])
        if new_cat != row['category']:
            db.execute('UPDATE transactions SET category = ? WHERE id = ?',
                       (new_cat, row['id']))
            changed += 1

    db.commit()
    return len(rows), changed


@app.route('/api/account/<account_num>/recategorize', methods=['POST'])
def api_recategorize_account(account_num):
    """Recategorize all transactions for one account."""
    db = get_db()
    try:
        total, changed = _do_recategorize(db, account_num)
        return jsonify({'total': total, 'changed': changed, 'account': account_num})
    finally:
        db.close()


@app.route('/api/recategorize', methods=['POST'])
def api_recategorize_all():
    """Recategorize every transaction across all accounts."""
    db = get_db()
    try:
        total, changed = _do_recategorize(db)
        return jsonify({'total': total, 'changed': changed})
    finally:
        db.close()


# ──────────────────────────────────────────────
#  Category Maintenance
# ──────────────────────────────────────────────

@app.route('/categories')
def categories_page():
    return render_template('categories.html')


@app.route('/api/categories', methods=['GET'])
def api_categories_get():
    """Return all categories with their keywords."""
    db = get_db()
    try:
        metas = db.execute(
            'SELECT * FROM category_meta ORDER BY sort_order, name'
        ).fetchall()
        rules = db.execute(
            'SELECT * FROM category_rules ORDER BY category_order, id'
        ).fetchall()

        kw_by_cat = {}
        for r in rules:
            kw_by_cat.setdefault(r['category'], []).append(dict(r))

        result = []
        for m in metas:
            result.append({
                **dict(m),
                'keywords': kw_by_cat.get(m['name'], [])
            })
        # Include "Other" even if not in category_meta
        names = {r['name'] for r in metas}
        if 'Other' not in names:
            result.append({
                'name': 'Other', 'color': '#b2bec3', 'icon': '📌',
                'sort_order': 999, 'is_builtin': 1, 'keywords': []
            })
        return jsonify(result)
    finally:
        db.close()


@app.route('/api/categories', methods=['POST'])
def api_category_create():
    """Add a new category."""
    data = request.get_json(force=True)
    name  = (data.get('name') or '').strip()
    color = data.get('color', '#b2bec3').strip()
    icon  = data.get('icon', '📌').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if name.upper() == 'OTHER':
        return jsonify({'error': '"Other" is a reserved category name'}), 400
    db = get_db()
    try:
        max_order = db.execute('SELECT MAX(sort_order) FROM category_meta').fetchone()[0] or 0
        db.execute(
            'INSERT INTO category_meta (name, color, icon, sort_order, is_builtin) VALUES (?,?,?,?,0)',
            (name, color, icon, max_order + 1)
        )
        db.commit()
        invalidate_rules_cache()
        return jsonify({'ok': True, 'name': name})
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 400
    finally:
        db.close()


@app.route('/api/categories/<path:cat_name>', methods=['PUT'])
def api_category_update(cat_name):
    """Update category metadata (color, icon)."""
    data  = request.get_json(force=True)
    color = data.get('color', '').strip()
    icon  = data.get('icon', '').strip()
    db = get_db()
    try:
        updates, vals = [], []
        if color:
            updates.append('color = ?'); vals.append(color)
        if icon:
            updates.append('icon = ?');  vals.append(icon)
        if not updates:
            return jsonify({'error': 'nothing to update'}), 400
        vals.append(cat_name)
        db.execute(f'UPDATE category_meta SET {", ".join(updates)} WHERE name = ?', vals)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/categories/<path:cat_name>', methods=['DELETE'])
def api_category_delete(cat_name):
    """Delete a user-defined category (and its keywords). Built-in categories are protected."""
    if cat_name == 'Other':
        return jsonify({'error': '"Other" cannot be deleted'}), 400
    db = get_db()
    try:
        meta = db.execute('SELECT is_builtin FROM category_meta WHERE name = ?',
                          (cat_name,)).fetchone()
        if not meta:
            return jsonify({'error': 'Category not found'}), 404
        if meta['is_builtin']:
            return jsonify({'error': 'Built-in categories cannot be deleted. Remove all their keywords instead.'}), 400
        db.execute('DELETE FROM category_rules WHERE category = ?', (cat_name,))
        db.execute('DELETE FROM category_meta WHERE name = ?', (cat_name,))
        db.commit()
        invalidate_rules_cache()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/categories/<path:cat_name>/keywords', methods=['POST'])
def api_keyword_add(cat_name):
    """Add a keyword to a category."""
    data    = request.get_json(force=True)
    keyword = (data.get('keyword') or '').strip()
    if not keyword:
        return jsonify({'error': 'keyword is required'}), 400

    db = get_db()
    try:
        # Check for conflicts (same keyword already assigned to a different category)
        conflict = db.execute(
            'SELECT category FROM category_rules WHERE UPPER(keyword) = UPPER(?)',
            (keyword,)
        ).fetchone()
        if conflict and conflict['category'] != cat_name:
            return jsonify({
                'error': f'Keyword already assigned to "{conflict["category"]}"',
                'conflict_category': conflict['category']
            }), 409

        cat_order = db.execute(
            'SELECT sort_order FROM category_meta WHERE name = ?', (cat_name,)
        ).fetchone()
        order = cat_order['sort_order'] if cat_order else 999

        db.execute(
            'INSERT OR IGNORE INTO category_rules (category, keyword, category_order) VALUES (?,?,?)',
            (cat_name, keyword, order)
        )
        db.commit()
        row = db.execute(
            'SELECT * FROM category_rules WHERE UPPER(keyword) = UPPER(?)', (keyword,)
        ).fetchone()
        invalidate_rules_cache()
        return jsonify(dict(row))
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 400
    finally:
        db.close()


@app.route('/api/keywords/<int:keyword_id>', methods=['DELETE'])
def api_keyword_delete(keyword_id):
    """Delete a single keyword rule by id."""
    db = get_db()
    try:
        db.execute('DELETE FROM category_rules WHERE id = ?', (keyword_id,))
        db.commit()
        invalidate_rules_cache()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/keywords/conflicts')
def api_keyword_conflicts():
    """Return keywords that appear more than once (shouldn't happen with UNIQUE index, but check anyway)."""
    db = get_db()
    try:
        rows = db.execute('''
            SELECT UPPER(keyword) as kw_upper, GROUP_CONCAT(category, ' | ') as categories, COUNT(*) as cnt
            FROM category_rules
            GROUP BY UPPER(keyword)
            HAVING cnt > 1
        ''').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/categories/reset-defaults', methods=['POST'])
def api_reset_defaults():
    """Wipe all category rules and re-seed from hardcoded defaults."""
    from database import _seed_category_rules
    from categorizer import CATEGORY_RULES, CATEGORY_COLORS, CATEGORY_ICONS
    db = get_db()
    try:
        db.execute('DELETE FROM category_rules')
        db.execute('DELETE FROM category_meta')
        db.commit()
        _seed_category_rules(db)
        invalidate_rules_cache()
        return jsonify({'ok': True})
    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        db.close()


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8080, use_reloader=True)
