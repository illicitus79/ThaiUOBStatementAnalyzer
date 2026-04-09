# UOB Statement Analyzer

A Flask web application for importing UOB credit card PDF statements, storing them in SQLite, and turning them into an account-level spending dashboard with categorization, trend analysis, merchant insights, and recurring-charge detection.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Flask](https://img.shields.io/badge/Flask-3.0-green) ![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey)

---

## What It Does

The app is built around one core workflow:

1. Upload a UOB credit card PDF statement.
2. Parse statement metadata and transactions.
3. Group multiple statements under the same account.
4. Categorize transactions automatically.
5. Explore dashboard views across one statement or a custom date range.

It is designed for account-level analysis rather than a single static monthly report.

---

## Implemented Features

### Import and Parsing

- **PDF Upload** with drag-and-drop support
- **Duplicate Detection** using SHA-256 file hashes
- **UOB Statement Parsing** via `pdfplumber`
- **Account Metadata Extraction** including account number, card number, card type, statement date, due date, credit line, balance, minimum payment, and rewards points
- **Foreign Currency Extraction** when the statement includes original-currency transaction values
- **Multi-Statement Account Grouping** so multiple months for the same account roll up into one dashboard

### Categorization

- **Automatic Transaction Categorization** using keyword rules
- **Database-Backed Rules** with a hardcoded fallback seed
- **Wildcard Matching** using `*`
- **Category Maintenance UI** for adding, editing, and deleting categories and keywords
- **Conflict Detection** to prevent the same keyword from being assigned to multiple categories
- **Recategorization** for one account or all stored transactions after rule changes

### Homepage and Navigation

- **Account Portfolio Home** showing uploaded accounts as interactive credit-card-style tiles
- **Account Summary Cards** with latest balance, credit line, reward points, and utilization
- **Improved Landing Hero** with upload framing, product messaging, and account-level summary stats

### Dashboard Filters and Table

- **Statement Selector** to switch between all statements or one specific statement
- **Quick Date Filters** for all / last 7 / 14 / 30 days
- **Custom Date Range Filtering**
- **Sortable Transaction Table**
- **Search by Merchant**
- **Category Filter**
- **Client-Side Pagination** with 10 / 20 / 50 / 100 / All rows
- **Statement Deletion** from the dashboard when a specific statement is selected

### Dashboard KPIs

- **Total Spend**
- **Transaction Count**
- **Average Daily Spend**
- **Top Category**
- **Largest Transaction**
- **Credit Utilization**
- **Trend Comparisons vs Previous Statement** for key KPIs when prior data exists
- **Tooltip Explainers** on dashboard metrics and chart sections so users can interpret the indicators in context

### Dashboard Financial Analysis Panels

- **Net Spend** after credits and refunds
- **Unique Merchant Count**
- **Active Spending Days**
- **Foreign Spend Share**
- **Payment Pressure Panel**
  - available credit headroom
  - minimum payment as a percentage of balance
  - days until payment due date
  - statement-to-due window length
- **Spend Concentration Panel**
  - top category share
  - top merchant share
  - top 5 merchant share
  - average ticket size
- **Spend Mix Panel**
  - essential vs discretionary share
  - early-cycle vs late-cycle share
  - weekend spend share
- **Recurring Burden Panel**
  - recurring spend in current range
  - estimated monthly recurring total
  - annualized recurring estimate
  - fixed recurring share
  - top recurring categories
- **Statement Comparison Panel**
  - spend delta vs prior statement
  - utilization delta
  - new merchants
  - dormant merchants
  - largest category moves
  - merchant leader changes

### Dashboard Analysis and Charts

- **Category Breakdown Donut**
- **Daily Spending Trend Bar Chart**
- **Cumulative Spending Line Chart**
- **Top Merchants Chart**
- **Burn Rate / Spend Pace Banner**
  - period progress
  - current spend pace
  - projected end-of-period total
  - comparison against previous period
- **Top Spending Days**
- **Credits and Refunds Summary**
- **Foreign Currency Summary**
- **Day-of-Week Spending Analysis**
- **Day-of-Month Spending Pattern**
- **Merchant Frequency vs Ticket Size Bubble Chart**
- **Month-over-Month Category Comparison** across uploaded statements
- **Recurring Merchant Detection**
  - merchants seen across multiple statements
  - fixed vs variable recurring-charge heuristic
  - estimated annualized cost

---

## Project Structure

```text
UOBStatementAnalyzer/
├── app.py              # Flask routes, HTML pages, and JSON APIs
├── pdf_parser.py       # UOB PDF parsing logic
├── categorizer.py      # Category rules and categorization logic
├── database.py         # SQLite schema, seeding, and DB helpers
├── requirements.txt    # Python dependencies
├── static/
│   ├── css/style.css   # Shared UI styling
│   └── js/app.js       # Shared frontend helpers
├── templates/
│   ├── base.html       # Shared layout
│   ├── index.html      # Homepage / account overview
│   ├── dashboard.html  # Account dashboard
│   └── categories.html # Category management screen
├── instance/           # SQLite database location (git-ignored)
└── uploads/            # Uploaded PDFs (git-ignored)
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- A UOB credit card PDF statement

### Installation

```bash
git clone <repo-url>
cd UOBStatementAnalyzer

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Run the App

```bash
python app.py
```

Open `http://127.0.0.1:8080`.

The app is configured to run on port `8080` by default.

---

## Usage

1. Upload a UOB PDF statement from the homepage.
2. Let the app parse and import the statement.
3. Upload more statements for the same account to build history over time.
4. Open an account dashboard from the homepage.
5. Filter by statement or by custom date range.
6. Explore category, merchant, pacing, recurring, and refund insights.
7. Adjust category rules from the `Categories` screen when needed.
8. Re-run recategorization after rule changes.

---

## Category Rules

The app uses rule-based matching on transaction descriptions.

| Pattern | Example | Matches |
|---|---|---|
| Plain substring | `NETFLIX` | `NETFLIX.COM`, `NETFLIX MONTHLY` |
| Wildcard `*` | `GRAB*FOOD` | `GRAB EXPRESS FOOD`, `GRAB_FOOD` |
| Trailing wildcard | `PTT*` | `PTTST`, `PTT STATION`, `PTT ONLINE` |

### Notes

- Matching is case-insensitive.
- Categories are evaluated in order.
- The first matching rule wins.
- Transactions with no match fall back to `Other`.
- Keyword conflicts are blocked in the UI.

### Category Maintenance Actions

| Action | Description |
|---|---|
| Add keyword | Add a keyword rule to a category |
| Remove keyword | Delete a single keyword rule |
| New Category | Create a custom category with name, icon, and color |
| Delete Category | Remove a user-created category and all its keywords |
| Apply & Recategorize | Re-run rules against stored transactions |
| Reset to Defaults | Restore built-in category metadata and rules |

---

## Default Spending Categories

| Category | Examples |
|---|---|
| Food & Dining | Restaurants, cafes, grills |
| Food Delivery | LINE MAN, GrabFood, Foodpanda |
| Groceries & Supermarket | Lotus, Tops, Big C |
| Convenience Store | 7-Eleven |
| Shopping & E-Commerce | Lazada, Shopee, Amazon |
| Transport & Ride-Hailing | Grab, BTS, MRT |
| Tech Subscriptions | OpenAI, GitHub, Midjourney |
| Streaming & Entertainment | Netflix, Spotify |
| Health & Beauty | Clinics, fitness, beauty |
| Telecom & Utilities | AIS, True, utility payments |
| Fuel & Automotive | PTT, Shell, Bangchak |
| Travel & Accommodation | Agoda, Airbnb, hotels |
| Payment / Refund | Payments, reversals, credits |
| Other | Unmatched transactions |

---

## API Endpoints

### Account Pages

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Homepage / account overview |
| `GET` | `/account/<account_num>` | Account dashboard |
| `GET` | `/dashboard/<statement_id>` | Backward-compatible redirect to account dashboard |

### Upload and Statement Actions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload and import a PDF statement |
| `POST` | `/statement/<statement_id>/delete` | Delete a statement and its transactions |

### Account Data APIs

Optional query params: `statement_id`, `from`, `to`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/account/<num>/statements` | List statements for an account with date bounds |
| `GET` | `/api/account/<num>/summary` | KPI summary, previous-period comparisons, credits/refunds, and payment-pressure fields |
| `GET` | `/api/account/<num>/category-breakdown` | Spend grouped by category |
| `GET` | `/api/account/<num>/daily-spending` | Spend grouped by day |
| `GET` | `/api/account/<num>/top-merchants` | Top merchants by spend |
| `GET` | `/api/account/<num>/transactions` | Full transaction list |
| `GET` | `/api/account/<num>/monthly-comparison` | Per-statement category totals for month-over-month charts |
| `GET` | `/api/account/<num>/recurring` | Recurring merchant analysis across statements |
| `POST` | `/api/account/<num>/recategorize` | Recategorize transactions for one account |
| `POST` | `/api/recategorize` | Recategorize all stored transactions |

### Category Management APIs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/categories` | Category maintenance page |
| `GET` | `/api/categories` | List categories and keywords |
| `POST` | `/api/categories` | Create a category |
| `PUT` | `/api/categories/<name>` | Update category metadata |
| `DELETE` | `/api/categories/<name>` | Delete a user-created category |
| `POST` | `/api/categories/<name>/keywords` | Add a keyword |
| `DELETE` | `/api/keywords/<id>` | Delete a keyword |
| `GET` | `/api/keywords/conflicts` | Check duplicate keyword assignments |
| `POST` | `/api/categories/reset-defaults` | Restore seeded defaults |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite via `sqlite3` |
| PDF Parsing | `pdfplumber` |
| Frontend | Jinja templates, vanilla JavaScript, CSS |
| Charts | Chart.js |
| Fonts | Google Fonts (`Space Grotesk`, `Fraunces`) |

---

## Notes and Limitations

- The parser currently targets **UOB Thailand** credit card statements.
- Cardholder name extraction may vary depending on PDF text encoding.
- Foreign currency analysis depends on the original-currency values being present in the statement text.
- Recurring-charge detection currently groups on normalized merchant description text and uses amount variance as a simple fixed-vs-variable heuristic.
- Category rule ordering matters because matching stops on the first rule hit.
