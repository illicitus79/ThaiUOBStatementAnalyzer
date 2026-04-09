# UOB Statement Analyzer

A Flask web application that parses UOB credit card PDF statements, stores transactions in SQLite, and presents spending insights through a glassmorphism dashboard with interactive charts.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-3.0-green) ![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey)

---

## Features

- **PDF Upload** — drag-and-drop or browse to upload UOB credit card statements
- **Auto Parsing** — extracts account info, card details, rewards points, and all transactions using `pdfplumber`
- **Smart Categorization** — 14 spending categories automatically assigned by keyword matching (Food & Dining, Groceries, Tech Subscriptions, etc.)
- **Multi-Statement Accounts** — upload multiple months for the same card; all data is unified under one account
- **Duplicate Detection** — SHA-256 file hash prevents the same statement being imported twice
- **Account Dashboard** — filter by statement period or custom date range; all charts update live
- **Interactive Charts** (Chart.js)
  - Donut chart — spending by category
  - Bar chart — daily spending trend (colour-coded hot days)
  - Line chart — cumulative spending curve
  - Horizontal bar — top 10 merchants
- **Transaction Table** — sortable columns, pagination (10 / 20 / 50 / 100 / All rows), search and category filter
- **Glassmorphism UI** — dark navy/purple gradient background, frosted-glass cards, animated credit card widgets

---

## Project Structure

```
UOBStatementAnalyzer/
├── app.py              # Flask routes and API endpoints
├── pdf_parser.py       # pdfplumber-based UOB statement parser
├── categorizer.py      # Keyword-to-category mapping (14 categories)
├── database.py         # SQLite schema and connection helper
├── requirements.txt    # Python dependencies
├── static/
│   ├── css/style.css   # Glassmorphism theme
│   └── js/app.js       # UI helpers
├── templates/
│   ├── base.html       # Navbar, flash messages, layout
│   ├── index.html      # Home — account cards + upload
│   └── dashboard.html  # Account dashboard with charts and table
├── instance/           # SQLite database (git-ignored)
└── uploads/            # Stored PDF files (git-ignored)
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- A UOB credit card PDF statement

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd UOBStatementAnalyzer

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the App

```bash
python app.py
```

Then open **http://127.0.0.1:8080** in your browser.

> Port 5000 is reserved on Windows — the app runs on **8080** by default.

---

## Usage

1. **Upload a statement** — drag a UOB PDF onto the upload area on the home page and click *Analyze Statement*. The app parses all transactions and redirects to the account dashboard.
2. **Upload more months** — upload additional statements for the same card. They are automatically grouped under the same account.
3. **Filter by statement or date** — use the *Statement* dropdown to focus on a single month, or pick a date range with the period chips or custom date picker.
4. **Explore the table** — click any column header to sort. Use the search box to find a merchant, or filter by category. Choose rows per page at the bottom.
5. **Delete a statement** — select the statement in the dropdown, then click *Delete Statement*.

---

## Spending Categories

| Category | Examples |
|---|---|
| Food & Dining | Restaurants, grills, cafes |
| Food Delivery | LINE MAN, Foodpanda, GrabFood |
| Groceries & Supermarket | Lotus, Tops, Big C |
| Convenience Store | 7-Eleven |
| Shopping & E-Commerce | Lazada, Shopee, Amazon |
| Transport & Ride-Hailing | Grab, BTS, MRT |
| Tech Subscriptions | OpenAI, GitHub, Midjourney |
| Streaming & Entertainment | Netflix, Spotify |
| Health & Beauty | Clinics, fitness centres |
| Telecom & Utilities | AIS, True Move |
| Fuel & Automotive | PTT, Shell, Bangchak |
| Travel & Accommodation | Hotels, Agoda, Airbnb |
| Payment / Refund | Payments, credits, reversals |
| Other | Everything else |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask 3 |
| PDF Parsing | pdfplumber |
| Database | SQLite (via sqlite3) |
| Charts | Chart.js 4 |
| Frontend | Vanilla JS, CSS (glassmorphism) |
| Fonts | Google Fonts — Inter |

---

## API Endpoints

All endpoints are scoped to an account number.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/account/<num>/statements` | List all statements for the account |
| `GET` | `/api/account/<num>/summary` | KPI summary (total spend, avg daily, etc.) |
| `GET` | `/api/account/<num>/category-breakdown` | Spend grouped by category |
| `GET` | `/api/account/<num>/daily-spending` | Spend grouped by day |
| `GET` | `/api/account/<num>/top-merchants` | Top merchants by total spend |
| `GET` | `/api/account/<num>/transactions` | Full transaction list |

All endpoints accept optional query parameters: `statement_id`, `from` (YYYY-MM-DD), `to` (YYYY-MM-DD).

---

## Notes

- Currently supports **UOB Thailand** credit card statements (Thai-English bilingual PDF format)
- Cardholder name may not be extracted on all statement layouts due to PDF encoding — the account number and card number are always parsed correctly
- Foreign currency transactions show both the original currency amount and the THB equivalent
