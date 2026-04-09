# UOB Statement Analyzer

A Flask web application that parses UOB credit card PDF statements, stores transactions in SQLite, and presents spending insights through a glassmorphism dashboard with interactive charts.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-3.0-green) ![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey)

---

## Features

- **PDF Upload** — drag-and-drop or browse to upload UOB credit card statements
- **Auto Parsing** — extracts account info, card details, rewards points, and all transactions using `pdfplumber`
- **Smart Categorization** — 14 spending categories automatically assigned by keyword matching (Food & Dining, Groceries, Tech Subscriptions, etc.)
- **Wildcard Keywords** — use `*` in keywords for flexible matching (e.g. `GRAB*FOOD` matches "GRAB EXPRESS FOOD")
- **Category Maintenance** — dedicated screen to add, edit, and delete categories and keywords without touching any code
- **Conflict Detection** — prevents the same keyword from being assigned to multiple categories
- **Multi-Statement Accounts** — upload multiple months for the same card; all data is unified under one account
- **Duplicate Detection** — SHA-256 file hash prevents the same statement being imported twice
- **Account Dashboard** — filter by statement period or custom date range; all charts update live
- **Interactive Charts** (Chart.js)
  - Donut chart — spending by category
  - Bar chart — daily spending trend (colour-coded hot days)
  - Line chart — cumulative spending curve
  - Horizontal bar — top 10 merchants
- **Transaction Table** — sortable columns, pagination (10 / 20 / 50 / 100 / All rows), search and category filter
- **Recategorize** — re-apply updated category rules to all existing transactions with one click
- **Glassmorphism UI** — dark navy/purple gradient background, frosted-glass cards, animated credit card widgets

---

## Project Structure

```
UOBStatementAnalyzer/
├── app.py              # Flask routes and API endpoints
├── pdf_parser.py       # pdfplumber-based UOB statement parser
├── categorizer.py      # Keyword-to-category mapping (DB-backed with hardcoded fallback)
├── database.py         # SQLite schema, connection helper, and category seeding
├── requirements.txt    # Python dependencies
├── static/
│   ├── css/style.css   # Glassmorphism theme
│   └── js/app.js       # UI helpers
├── templates/
│   ├── base.html       # Navbar, flash messages, layout
│   ├── index.html      # Home — account cards + upload
│   ├── dashboard.html  # Account dashboard with charts and table
│   └── categories.html # Category maintenance screen
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
6. **Manage categories** — click *Categories* in the navbar to open the category maintenance screen.
7. **Apply rule changes** — after updating keywords, click *Apply & Recategorize* to re-classify all existing transactions.

---

## Category Maintenance

The **Categories** screen (`/categories`) lets you manage spending categories without editing any code.

### Keyword Matching

| Pattern | Example | Matches |
|---|---|---|
| Plain substring | `NETFLIX` | "NETFLIX.COM", "NETFLIX MONTHLY" |
| Wildcard `*` | `GRAB*FOOD` | "GRAB EXPRESS FOOD", "GRAB_FOOD" |
| Trailing wildcard | `PTT*` | "PTTST", "PTT STATION", "PTT ONLINE" |

- Matching is **case-insensitive**.
- Categories are checked **top-to-bottom**; the first match wins. Place more specific keywords above broader ones.
- Transactions that match no keyword are automatically placed in **Other**.
- The same keyword **cannot** be assigned to two categories — the UI warns you on conflict.

### Actions

| Action | Description |
|---|---|
| **＋ Add** (per card) | Add a new keyword to an existing category |
| **× remove** (on tag) | Remove a single keyword |
| **New Category** | Create a custom category with a name, icon, and colour |
| **Delete** (card) | Remove a user-created category and all its keywords |
| **Apply & Recategorize** | Re-run categorization rules against all stored transactions |
| **Reset to Defaults** | Wipe all customizations and restore built-in defaults |

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
| Other | Everything else (automatic fallback) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask 3 |
| PDF Parsing | pdfplumber |
| Database | SQLite (via sqlite3) |
| Charts | Chart.js 4 |
| Frontend | Vanilla JS, CSS (glassmorphism) |
| Fonts | Google Fonts — Space Grotesk, Fraunces |

---

## API Endpoints

### Account Data

All endpoints are scoped to an account number and accept optional query parameters: `statement_id`, `from` (YYYY-MM-DD), `to` (YYYY-MM-DD).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/account/<num>/statements` | List all statements for the account |
| `GET` | `/api/account/<num>/summary` | KPI summary (total spend, avg daily, etc.) |
| `GET` | `/api/account/<num>/category-breakdown` | Spend grouped by category |
| `GET` | `/api/account/<num>/daily-spending` | Spend grouped by day |
| `GET` | `/api/account/<num>/top-merchants` | Top merchants by total spend |
| `GET` | `/api/account/<num>/transactions` | Full transaction list |
| `POST` | `/api/account/<num>/recategorize` | Recategorize transactions for one account |
| `POST` | `/api/recategorize` | Recategorize all transactions |

### Category Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/categories` | List all categories with their keywords |
| `POST` | `/api/categories` | Create a new category |
| `PUT` | `/api/categories/<name>` | Update category colour / icon |
| `DELETE` | `/api/categories/<name>` | Delete a user-created category |
| `POST` | `/api/categories/<name>/keywords` | Add a keyword to a category |
| `DELETE` | `/api/keywords/<id>` | Remove a keyword by ID |
| `GET` | `/api/keywords/conflicts` | List any duplicate keyword assignments |
| `POST` | `/api/categories/reset-defaults` | Restore built-in category defaults |

---

## Notes

- Currently supports **UOB Thailand** credit card statements (Thai-English bilingual PDF format)
- Cardholder name may not be extracted on all statement layouts due to PDF encoding — the account number and card number are always parsed correctly
- Foreign currency transactions show both the original currency amount and the THB equivalent
- Category rules are stored in SQLite (`category_rules` table) and loaded with an in-memory cache; the cache is invalidated automatically whenever rules are changed through the UI
