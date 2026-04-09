# -*- coding: utf-8 -*-
import pdfplumber
import re
import logging

logger = logging.getLogger(__name__)

MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
          'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

_DATE_PAT = r'\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)'
_CURRENCIES = r'USD|EUR|GBP|SGD|JPY|CNY|HKD|AUD|CHF|CAD|MYR|NZD|THB|INR|KRW|VND|IDR|PHP|ZAR|AED|SAR|QAR|OMR|BHD|KWD'

# Main transaction line regex
TRANS_RE = re.compile(
    rf'^({_DATE_PAT})\s+({_DATE_PAT})\s+'   # post_date  trans_date
    rf'(.+?)\s+'                              # description (non-greedy)
    rf'(?:({_CURRENCIES})\s+([\d,]+\.?\d*)\s+)?'  # optional foreign currency + amount
    r'([\d,]+\.\d{2})\s*(CR)?$',             # THB amount + optional CR
    re.IGNORECASE
)

# English-only skip patterns (avoids encoding issues with Thai source)
SKIP_KEYWORDS = [
    'SUB TOTAL', 'TOTAL BALANCE', 'TOTAL FEE', 'TOTAL VAT',
    'PAGE ', 'POST DATE', 'TRANS DATE', 'PREVIOUS BALANCE',
    'PLEASE KEEP', 'BILLER', 'STATEMENT DATE', 'CREDIT LINE',
    'PAYMENT DUE', 'ACCOUNT NUMBER', 'CARD NUMBER',
]


def _should_skip(line: str) -> bool:
    upper = line.upper().strip()
    # Skip very short lines or lines that start with non-ASCII (Thai header/footer)
    if len(upper) < 5:
        return True
    # Skip lines where >40% characters are non-ASCII (Thai text lines)
    non_ascii = sum(1 for c in line if ord(c) > 127)
    if non_ascii > len(line) * 0.4:
        return True
    return any(s in upper for s in SKIP_KEYWORDS)


def _parse_date(date_str: str, stmt_year: int, stmt_month: int):
    """Convert 'DD MMM' to 'YYYY-MM-DD', handling year rollover."""
    parts = date_str.strip().split()
    if len(parts) != 2:
        return None
    try:
        day = int(parts[0])
        month_num = MONTHS.index(parts[1].upper()) + 1
        # If transaction month is after the statement month -> previous year
        year = stmt_year if month_num <= stmt_month else stmt_year - 1
        return f"{year}-{month_num:02d}-{day:02d}"
    except (ValueError, IndexError):
        return None


def _parse_amount(s: str) -> float:
    try:
        return float(s.replace(',', ''))
    except (ValueError, AttributeError):
        return 0.0


def extract_account_info(text: str) -> dict:
    info = {}

    # Account / member number
    m = re.search(r'ACCOUNT NUMBER\s+([\d\-]+)', text, re.IGNORECASE)
    if m:
        info['account_number'] = m.group(1).strip()

    # Cardholder name - multiple attempts for different PDF layouts
    m = re.search(r'^(MR[S]?\.?\s+[A-Z][A-Z\s]{3,})$', text, re.MULTILINE)
    if not m:
        m = re.search(r'(MR[S]?\.?\s+[A-Z]{2,}(?:\s+[A-Z]{2,})+)', text)
    if m:
        info['cardholder_name'] = ' '.join(m.group(1).split())
    else:
        # Fallback: look for partial name like "P. NAGEKAR" near card number
        m = re.search(r'Cardmember Name\s*[.]*\s*([A-Z][A-Z.\s]+?)(?:\s{2,}|$)',
                      text, re.IGNORECASE | re.MULTILINE)
        if m:
            info['cardholder_name'] = m.group(1).strip()

    # Statement date
    m = re.search(r'STATEMENT DATE\s+(\d{2}\s+[A-Z]{3}\s+\d{4})', text, re.IGNORECASE)
    if m:
        info['statement_date'] = m.group(1).strip()

    # Payment due date
    m = re.search(r'PAYMENT DUE DATE\s+(\d{2}\s+[A-Z]{3}\s+\d{4})', text, re.IGNORECASE)
    if m:
        info['payment_due_date'] = m.group(1).strip()

    # Total credit line
    m = re.search(r'TOTAL CREDIT LINE\s+([\d,]+)', text, re.IGNORECASE)
    if m:
        info['credit_line'] = _parse_amount(m.group(1))

    # Total balance and minimum payment from TOTAL row
    m = re.search(r'TOTAL\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', text)
    if m:
        info['total_balance'] = _parse_amount(m.group(1))
        info['minimum_payment'] = _parse_amount(m.group(2))

    # Rewards points outstanding (large number followed by small numbers and a date)
    m = re.search(r'([\d,]{5,})\s+\d+\s+\d{2}\s+[A-Z]{3}\s+\d{2}', text)
    if m:
        try:
            info['rewards_points'] = int(m.group(1).replace(',', ''))
        except ValueError:
            pass

    # Card number (masked like 5404 32XX XXXX 7676)
    m = re.search(r'(\d{4}\s+\d{2}XX\s+XXXX\s+\d{4})', text)
    if m:
        info['card_number'] = m.group(1).strip()

    # Card type (UOB WORLD / UOB VISA / etc.)
    m = re.search(r'UOB\s+(WORLD|VISA|MASTERCARD|PLATINUM|INFINITE|ONE|PREFERRED|LADY)',
                  text, re.IGNORECASE)
    if m:
        info['card_type'] = f"UOB {m.group(1).upper()}"
    else:
        info['card_type'] = 'UOB Credit Card'

    return info


def parse_statement(pdf_path: str):
    """
    Parse a UOB credit card statement PDF.
    Returns (account_info dict, list of transaction dicts).
    """
    full_text = ''
    all_lines = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                full_text += text + '\n'
                all_lines.extend(text.splitlines())

    account_info = extract_account_info(full_text)

    # Derive statement year / month for date parsing
    stmt_year, stmt_month = 2026, 3  # sensible defaults
    stmt_date = account_info.get('statement_date', '')
    if stmt_date:
        parts = stmt_date.split()
        if len(parts) == 3:
            try:
                stmt_month = MONTHS.index(parts[1].upper()) + 1
                stmt_year = int(parts[2])
            except (ValueError, IndexError):
                pass

    transactions = []
    in_transactions = False

    for raw_line in all_lines:
        line = raw_line.strip()

        # Enter transaction section when we hit the column header
        if re.search(r'POST\s*DATE', line, re.IGNORECASE) and \
           re.search(r'TRANS\s*DATE', line, re.IGNORECASE):
            in_transactions = True
            continue

        if not in_transactions:
            continue

        if not line or _should_skip(line):
            continue

        m = TRANS_RE.match(line)
        if not m:
            continue

        post_str, trans_str, description, fx_curr, fx_amt_str, thb_str, cr_flag = m.groups()

        transactions.append({
            'post_date': _parse_date(post_str, stmt_year, stmt_month),
            'trans_date': _parse_date(trans_str, stmt_year, stmt_month),
            'description': description.strip(),
            'amount': _parse_amount(thb_str),
            'is_credit': bool(cr_flag),
            'foreign_currency': fx_curr or None,
            'foreign_amount': _parse_amount(fx_amt_str) if fx_amt_str else None,
        })

    logger.info("Parsed %d transactions from %s", len(transactions), pdf_path)
    return account_info, transactions
